"""
Lista, para cada desabastecimiento del caso E ("equivalentes, pero todas en
desabastecimiento"), sus alternativas equivalentes con el enlace a su ficha en CIMA.

En cada ficha hay que mirar la lista de PRESENTACIONES (envases): si alguna está
comercializada y SIN aviso de problema de suministro, el caso E es un error
(sí había alternativa disponible).

Uso:
    python comprobar_caso_e.py              -> todos los casos E
    python comprobar_caso_e.py 758615       -> solo ese código nacional

Guarda también datos_limpios/comprobar_caso_e.csv con una columna 'revision' para rellenar.
"""

import sys
from pathlib import Path

import pandas as pd

LIMPIOS = Path(__file__).parent / "datos_limpios"
URL_FICHA = "https://cima.aemps.es/cima/publico/detalle.html?nregistro="

resumen = pd.read_csv(LIMPIOS / "alternativas_resumen.csv", dtype={"cn_desabastecido": str})
alt = pd.read_csv(LIMPIOS / "alternativas.csv", dtype={"cn_desabastecido": str, "nregistro_alternativa": str})

# Caso E: ninguna equivalente disponible, pero al menos una equivalente en desabastecimiento
casos_e = resumen[(resumen["n_disponibles"] == 0) & (resumen["n_en_desabastecimiento"] > 0)]
if len(sys.argv) > 1:
    casos_e = casos_e[casos_e["cn_desabastecido"].isin(sys.argv[1:])]

filas = []
for _, caso in casos_e.iterrows():
    equiv = alt[(alt["cn_desabastecido"] == caso["cn_desabastecido"]) & alt["equivalente"]]
    print(f"\n### CN {caso['cn_desabastecido']} · {caso['nombre']}")
    print(f"    {len(equiv)} alternativa(s) equivalente(s), todas marcadas en desabastecimiento:")
    for _, a in equiv.iterrows():
        url = URL_FICHA + a["nregistro_alternativa"]
        print(f"    - {a['nombre_alternativa']}  ({a['laboratorio_alternativa']})")
        print(f"      {url}")
        filas.append({"cn_desabastecido": caso["cn_desabastecido"], "nombre": caso["nombre"],
                      "alternativa": a["nombre_alternativa"], "laboratorio": a["laboratorio_alternativa"],
                      "ficha_cima": url, "revision": ""})

pd.DataFrame(filas).to_csv(LIMPIOS / "comprobar_caso_e.csv", index=False, encoding="utf-8-sig")
print(f"\n{len(casos_e)} casos E · {len(filas)} alternativas a revisar · guardado en comprobar_caso_e.csv")
print("En cada ficha: ¿hay algún envase comercializado SIN aviso de problema de suministro?")
print("  sí -> el caso E es un ERROR (apunta 'error: envase X disponible')")
print("  no -> correcto (apunta 'ok')")
