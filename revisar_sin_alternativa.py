"""
Clasifica los desabastecimientos SIN alternativa equivalente disponible en:
  A. No hay ninguna otra presentación con ese principio activo
  B. Hay con la misma dosis pero otra forma farmacéutica
  C. Hay con la misma forma pero otra dosis
  D. Hay otras, pero con otra dosis y otra forma
  H. No sustituible: hay presentaciones iguales, pero requieren nueva prescripción
  G. Vacuna: no se proponen alternativas automáticas (consultar)
  F. Hay con la misma forma, pero la dosis no se puede comparar (combinaciones, "-", "N.A.")
  E. Hay equivalentes, pero todas están también en desabastecimiento

Y saca 15 casos al azar a datos_limpios/revision_manual.csv para comprobarlos a mano en CIMA.

Uso:
    python revisar_sin_alternativa.py
"""

from pathlib import Path

import pandas as pd

LIMPIOS = Path(__file__).parent / "datos_limpios"

resumen = pd.read_csv(LIMPIOS / "alternativas_resumen.csv", dtype={"cn_desabastecido": str})
alt = pd.read_csv(LIMPIOS / "alternativas.csv", dtype={"cn_desabastecido": str})

sin = resumen[resumen["n_disponibles"] == 0].copy()


def clasificar(cn):
    a = alt[alt["cn_desabastecido"] == cn]
    if a.empty:
        return "A. Ninguna otra presentación"
    if "es_vacuna" in a and a["es_vacuna"].any():
        return "G. Vacuna (consultar)"
    if "desabastecido_no_sustituible" in a and a["desabastecido_no_sustituible"].any():
        return "H. No sustituible (nueva prescripción)"
    if a["equivalente"].any():
        return "E. Equivalentes, pero todas en desabastecimiento"
    if a["misma_dosis"].any():
        return "B. Misma dosis, otra forma"
    misma_forma = a[a["misma_forma"]]
    if not misma_forma.empty and "dosis_comparable" in a and (~misma_forma["dosis_comparable"]).any():
        return "F. Misma forma, dosis no comparable"
    if not misma_forma.empty:
        return "C. Misma forma, otra dosis"
    return "D. Otra dosis y otra forma"


sin["motivo"] = sin["cn_desabastecido"].apply(clasificar)
sin["n_candidatas"] = sin["cn_desabastecido"].map(alt["cn_desabastecido"].value_counts()).fillna(0).astype(int)

print(f"Desabastecimientos sin alternativa equivalente disponible: {len(sin)}\n")
print(sin["motivo"].value_counts().to_string())

muestra = pd.concat([g.sample(min(len(g), 3), random_state=1) for _, g in sin.groupby("motivo")])
muestra = muestra[["motivo", "cn_desabastecido", "nombre", "n_candidatas"]]
muestra["revision"] = ""  # rellenar a mano: ¿es correcto? sí / no + comentario
muestra.to_csv(LIMPIOS / "revision_manual.csv", index=False, encoding="utf-8-sig")

print("\nMuestra para revisar a mano (guardada en revision_manual.csv):")
print(muestra[["motivo", "cn_desabastecido", "nombre", "n_candidatas"]].to_string(index=False))
