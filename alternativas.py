"""
Paso 7: alternativas por principio activo para cada desabastecimiento.

Para cada presentación en desabastecimiento busca en CIMA otros medicamentos con
el MISMO principio activo y, si CIMA da esos datos, la misma dosis y forma
farmacéutica. Después marca cada alternativa como:
  - "Disponible": comercializada y sin problema de suministro activo hoy
  - "También en desabastecimiento": está en la lista de la AEMPS de hoy

Uso:
    python alternativas.py --diagnostico   (prueba 1 principio activo y enseña qué devuelve CIMA)
    python alternativas.py                 (todas; la 1ª vez tarda varios minutos)

Salidas (en datos_limpios/):
    alternativas.csv          -> una fila por (desabastecimiento, alternativa)
    alternativas_resumen.csv  -> una fila por desabastecimiento: nº disponibles / nº en desabastecimiento

Las búsquedas se guardan en datos_cima/cache_busquedas_v2.json y se renuevan cada 7 días.
"""

import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).parent
LIMPIOS = BASE / "datos_limpios"
CACHE = BASE / "datos_cima" / "cache_busquedas_v2.json"  # v2: corrige nosustituible
URL_BUSQUEDA = "https://cima.aemps.es/cima/rest/medicamentos"
CABECERAS = {"User-Agent": "Desabastecimiento-stock/0.1 (uso académico)"}
DIAS_CACHE = 7


# ----------------------------------------------------------------------------- CIMA
def buscar_por_principio(principio):
    """Todas las páginas de /medicamentos?practiv1=<principio>."""
    resultados, pagina = [], 1
    while True:
        r = requests.get(URL_BUSQUEDA, params={"practiv1": principio, "pagina": pagina},
                         headers=CABECERAS, timeout=60)
        if r.status_code == 204 or not r.text.strip():
            break
        r.raise_for_status()
        datos = r.json()
        lote = datos.get("resultados", [])
        resultados.extend(lote)
        if not lote or len(resultados) >= datos.get("totalFilas", 0):
            break
        pagina += 1
        time.sleep(0.2)
    return resultados


def nombre_de(valor):
    """CIMA a veces da {'id':..,'nombre':..} y a veces texto: devuelve siempre texto."""
    if isinstance(valor, dict):
        return valor.get("nombre")
    if isinstance(valor, list):
        return " + ".join(filter(None, (nombre_de(v) for v in valor))) or None
    return valor


UNIDADES = {  # todo a una unidad base por magnitud
    "g": ("mg", 1000), "gramo": ("mg", 1000), "gramos": ("mg", 1000),
    "mg": ("mg", 1), "miligramo": ("mg", 1), "miligramos": ("mg", 1),
    "µg": ("mg", 0.001), "ug": ("mg", 0.001), "mcg": ("mg", 0.001),
    "microgramo": ("mg", 0.001), "microgramos": ("mg", 0.001), "ng": ("mg", 0.000001),
    "ml": ("ml", 1), "mililitro": ("ml", 1), "mililitros": ("ml", 1), "l": ("ml", 1000),
    "ui": ("ui", 1), "u.i.": ("ui", 1), "u": ("ui", 1), "unidad": ("ui", 1),
    "unidades": ("ui", 1), "ph.eur.u": ("ui", 1), "meq": ("meq", 1), "%": ("%", 1),
}
MULTIPLICADORES = {"millones": 1e6, "millón": 1e6, "millon": 1e6, "kilo": 1e3, "mil": 1e3}

UNIDAD = (r"(ph\. ?eur\. ?u|u\.i\.|unidades|unidad|microgramos?|miligramos?|gramos?|mililitros?"
          r"|mcg|µg|ug|ng|mg|meq|g|ml|l|ui|u|%)")
MULT = r"(?:\s*(millones|millón|millon|kilo|mil))?"
# 35.000 · 2 000 000 · 1.000,5 · 0,25 · 20
NUM = r"(\d{1,3}(?:[. ]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
# Concentraciones: "80 mg/ml", "250 mg/25 ml", "3 mg/g", "35 µg/h", "10 mg/pulsación".
# El denominador nunca es mg/µg, para no confundirlo con combinaciones "40 mg/10 mg".
PATRON_CONC = re.compile(NUM + MULT + r"\s*" + UNIDAD + r"\s*/\s*" + NUM + r"?\s*"
                         r"(mililitros?|ml|gramos?|g|l|dosis|pulsaci[oó]n|horas|h)(?![a-z])")
PATRON_DOSIS = re.compile(NUM + MULT + r"\s*" + UNIDAD + r"(?![a-z])")


def _num(x, mult=""):
    if re.fullmatch(r"\d{1,3}(?:[. ]\d{3})+(?:,\d+)?", x):  # separador de miles
        x = x.replace(".", "").replace(" ", "")
    return float(x.replace(",", ".")) * MULTIPLICADORES.get(mult, 1)


def normalizar_dosis(texto):
    """Pasa una dosis a una forma comparable, o None si no reconoce ninguna cantidad.
    '250 µg' y '0,25 mg' -> '0.25 mg' · '250 mg/25 ml' y '10 mg/ml' -> '10 mg/ml'
    '5 MILLONES UI' y '5.000.000 U.I.' -> '5e+06 ui' · '40 mg/10 mg' -> '10 mg+40 mg'
    '1 %', '10 mg/g' y '10 mg/ml' -> '10 mg/ml' (aproximación: 1 g ≈ 1 ml)"""
    if not texto:
        return None
    t = texto.lower()
    partes = []
    for numero, mult, unidad, den_num, den_unidad in PATRON_CONC.findall(t):
        base, factor = UNIDADES[unidad.replace(" ", "")]
        den_unidad = den_unidad.replace("ó", "o")
        divisor = _num(den_num) if den_num else 1
        if den_unidad in UNIDADES:  # ml, l, g...: se pasa a "por 1 unidad base"
            den_base, den_factor = UNIDADES[den_unidad]
            if den_base == "mg":  # "por gramo": se asimila a "por ml" (1 g ≈ 1 ml)
                den_base, den_factor = "ml", den_factor / 1000
            valor = _num(numero, mult) * factor / (divisor * den_factor)
            partes.append(f"{round(valor, 6):g} {base}/{den_base}")
        else:  # dosis, pulsación, horas
            partes.append(f"{round(_num(numero, mult) * factor / divisor, 6):g} {base}/{den_unidad}")
    resto = PATRON_CONC.sub(" ", t)
    for numero, mult, unidad in PATRON_DOSIS.findall(resto):
        base, factor = UNIDADES[unidad.replace(" ", "")]
        if base == "%":  # 1 % = 10 mg/g ≈ 10 mg/ml
            partes.append(f"{round(_num(numero, mult) * 10, 6):g} mg/ml")
            continue
        partes.append(f"{round(_num(numero, mult) * factor, 6):g} {base}")
    return "+".join(sorted(set(partes))) or None


def familia_forma(forma):
    """Agrupa formas que CIMA nombra distinto pero son equivalentes para buscar alternativas."""
    if not forma:
        return None
    f = forma.replace("perfusión", "").replace("perfusion", "").strip()
    return " ".join(f.split())


def dosis_de(c):
    """La dosis se toma del NOMBRE (más uniforme en CIMA) y, si no tiene, del campo dosis."""
    return normalizar_dosis(c.get("nombre")) or normalizar_dosis(c.get("dosis_texto"))


def es_no_sustituible(valor):
    """CIMA da {'id': 0, 'nombre': 'N/A'} cuando NO hay restricción de sustitución.
    Cualquier otro id indica un motivo de no sustitución."""
    if isinstance(valor, dict):
        return valor.get("id", 0) not in (0, None)
    return bool(valor)


def resumir(m):
    """Campos que usamos para comparar. Cada uno puede faltar (None)."""
    forma = m.get("formaFarmaceuticaSimplificada") or m.get("formaFarmaceutica")
    return {
        "nregistro": str(m.get("nregistro")),
        "nombre": m.get("nombre"),
        "laboratorio": m.get("labtitular"),
        "comercializado": m.get("comerc"),
        "vtm": nombre_de(m.get("vtm")),
        "dosis_texto": m.get("dosis"),
        "dosis": normalizar_dosis(m.get("dosis")),
        "forma": (nombre_de(forma) or "").strip().lower() or None,
        "psum_cima": m.get("psum"),
        "no_sustituible": es_no_sustituible(m.get("nosustituible")),
    }


def cargar_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def busqueda_con_cache(principio, cache):
    entrada = cache.get(principio)
    if entrada:
        antig = (date.today() - datetime.fromisoformat(entrada["fecha"]).date()).days
        if antig < DIAS_CACHE:
            return entrada["resultados"]
    resultados = [resumir(m) for m in buscar_por_principio(principio)]
    cache[principio] = {"fecha": date.today().isoformat(), "resultados": resultados}
    return resultados


# ----------------------------------------------------------------------------- Diagnóstico
def diagnostico(df):
    ejemplo = df.dropna(subset=["principio_activo"]).iloc[0]
    principio = ejemplo["principio_activo"].split(" + ")[0]
    print(f"Principio activo de prueba: {principio}  (de {ejemplo['nombre']})\n")
    r = requests.get(URL_BUSQUEDA, params={"practiv1": principio}, headers=CABECERAS, timeout=60)
    print(f"HTTP {r.status_code}")
    datos = r.json()
    print(f"totalFilas: {datos.get('totalFilas')}")
    if datos.get("resultados"):
        primero = datos["resultados"][0]
        print("\nCampos del primer resultado:", sorted(primero.keys()))
        print("\nLo que usaríamos para comparar:")
        print(json.dumps(resumir(primero), ensure_ascii=False, indent=2))
    print("\nSi 'dosis' o 'forma' salen null, pégame esta salida y lo ajusto.")


# ----------------------------------------------------------------------------- Principal
def main():
    ruta = sorted(LIMPIOS.glob("aemps_enriquecido_*.csv"))[-1]
    df = pd.read_csv(ruta, dtype={"cn": str, "nregistro": str})
    print(f"Leyendo {ruta.name}: {len(df)} desabastecimientos")

    if "--diagnostico" in sys.argv:
        diagnostico(df)
        return

    # nregistro de los medicamentos que hoy tienen algún desabastecimiento
    en_desab = set(df["nregistro"].dropna())

    cache = cargar_cache()
    CACHE.parent.mkdir(exist_ok=True)
    principios = sorted({p.split(" + ")[0] for p in df["principio_activo"].dropna()})
    print(f"Principios activos distintos: {len(principios)}")

    busquedas = {}
    for i, p in enumerate(principios, 1):
        try:
            busquedas[p] = busqueda_con_cache(p, cache)
        except Exception as e:
            print(f"  {p}: error {e}")
            busquedas[p] = []
        if i % 25 == 0 or i == len(principios):
            print(f"  {i}/{len(principios)}")
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    filas = []
    for _, d in df.dropna(subset=["principio_activo"]).iterrows():
        candidatos = busquedas.get(d["principio_activo"].split(" + ")[0], [])
        propio = next((c for c in candidatos if c["nregistro"] == d["nregistro"]), None)
        es_vacuna = str(d.get("atc_codigo") or "").startswith("J07")
        no_sustituible = bool(propio and propio["no_sustituible"])
        for c in candidatos:
            if c["nregistro"] == d["nregistro"] or c["comercializado"] is False:
                continue
            # Misma composición: si CIMA da el VTM se compara; si no, se acepta
            if propio and propio["vtm"] and c["vtm"] and c["vtm"] != propio["vtm"]:
                continue
            # Se normaliza aquí, desde el texto original: así una mejora de
            # normalizar_dosis() no obliga a repetir las búsquedas en CIMA
            dosis_propia = dosis_de(propio) if propio else None
            dosis_cand = dosis_de(c)
            dosis_comparable = bool(dosis_propia and dosis_cand)
            misma_dosis = dosis_comparable and dosis_cand == dosis_propia
            misma_forma = bool(propio and propio["forma"]
                               and familia_forma(c["forma"]) == familia_forma(propio["forma"]))
            filas.append({
                "cn_desabastecido": d["cn"],
                "nombre_desabastecido": d["nombre"],
                "principio_activo": d["principio_activo"],
                "nregistro_alternativa": c["nregistro"],
                "nombre_alternativa": c["nombre"],
                "laboratorio_alternativa": c["laboratorio"],
                "dosis_alternativa": c["dosis_texto"],
                "desabastecido_no_sustituible": no_sustituible,
                "psum_cima": c["psum_cima"],
                "dosis_comparable": dosis_comparable,
                "misma_dosis": misma_dosis,
                "misma_forma": misma_forma,
                # Vacunas (ATC J07): CIMA no distingue bien antígeno/dosis (p. ej. gripe
                # estándar vs dosis alta), así que nunca se proponen como equivalentes
                "es_vacuna": es_vacuna,
                # No sustituibles (p. ej. insulinas, biológicos): cambiar de presentación
                # requiere nueva prescripción, así que tampoco cuentan como equivalentes
                "requiere_prescripcion": misma_dosis and misma_forma and no_sustituible,
                "equivalente": misma_dosis and misma_forma and not es_vacuna and not no_sustituible,
                "estado": "También en desabastecimiento" if c["nregistro"] in en_desab else "Disponible",
            })

    alt = pd.DataFrame(filas)
    LIMPIOS.mkdir(exist_ok=True)
    alt.to_csv(LIMPIOS / "alternativas.csv", index=False, encoding="utf-8-sig")

    if alt.empty:
        print("No se ha encontrado ninguna alternativa: ejecuta con --diagnostico y pégame la salida.")
        return

    equiv = alt[alt["equivalente"]]
    resumen = (equiv.groupby(["cn_desabastecido", "estado"]).size().unstack(fill_value=0)
               .reindex(columns=["Disponible", "También en desabastecimiento"], fill_value=0)
               .rename(columns={"Disponible": "n_disponibles",
                                "También en desabastecimiento": "n_en_desabastecimiento"}))
    resumen = (df[["cn", "nombre"]].rename(columns={"cn": "cn_desabastecido"})
               .merge(resumen.reset_index(), on="cn_desabastecido", how="left").fillna(0))
    resumen[["n_disponibles", "n_en_desabastecimiento"]] = resumen[
        ["n_disponibles", "n_en_desabastecimiento"]].astype(int)
    resumen.to_csv(LIMPIOS / "alternativas_resumen.csv", index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------------ Resumen
    print(f"\nAlternativas encontradas: {len(alt)} (equivalentes en dosis y forma: {len(equiv)})")
    print(f"Candidatas con dosis comparable: {alt['dosis_comparable'].mean():.0%}")
    print(f"Vacunas (sin alternativa automática, 'consultar'): {alt.loc[alt['es_vacuna'], 'cn_desabastecido'].nunique()}")
    no_sust = alt.loc[alt["desabastecido_no_sustituible"], "cn_desabastecido"].nunique()
    print(f"Desabastecimientos de medicamentos NO sustituibles: {no_sust}")
    discrepan = (equiv["estado"].eq("Disponible") & equiv["psum_cima"].eq(True)).sum()
    print(f"Alternativas 'disponibles' que CIMA marca con psum (revisar): {discrepan}")
    sin = (resumen["n_disponibles"] == 0).sum()
    print(f"Desabastecimientos SIN ninguna alternativa equivalente disponible: {sin} de {len(resumen)}")
    print("\nEjemplos:")
    print(resumen.sort_values("n_disponibles", ascending=False).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
