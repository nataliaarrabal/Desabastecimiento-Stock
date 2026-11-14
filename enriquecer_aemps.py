"""
Paso 4: enriquecer y limpiar los datos de la AEMPS.

Qué hace:
  1. Lee la última descarga de la AEMPS (datos_raw/aemps_AAAA-MM-DD.json).
  2. Consulta CIMA por cada código nacional (CN) para añadir laboratorio,
     código ATC y principio activo. Guarda las respuestas en una caché, así
     los días siguientes solo consulta los CN nuevos (segundos en vez de minutos).
  3. Convierte las fechas a hora de Madrid y se queda con el día.
  4. Guarda:
       datos_limpios/aemps_enriquecido_AAAA-MM-DD.csv  -> la tabla que leerá el dashboard
       datos_limpios/tipos_problema.csv                -> cada tipoProblemaSuministro con sus textos de observ

Uso:
    python enriquecer_aemps.py
"""

import json
import time
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).parent
RAW = BASE / "datos_raw"
LIMPIOS = BASE / "datos_limpios"
CACHE = BASE / "datos_cima" / "cache_medicamentos.json"

URL_MEDICAMENTO = "https://cima.aemps.es/cima/rest/medicamento"
CABECERAS = {"User-Agent": "TFG-desabastecimiento/0.1 (uso académico)"}
ZONA = "Europe/Madrid"

# Los 14 grupos anatómicos principales del ATC (primer carácter del código)
GRUPOS_ATC = {
    "A": "Tracto alimentario y metabolismo", "B": "Sangre y órganos hematopoyéticos",
    "C": "Sistema cardiovascular", "D": "Dermatológicos",
    "G": "Sistema genitourinario y hormonas sexuales",
    "H": "Preparados hormonales sistémicos (excl. sexuales e insulinas)",
    "J": "Antiinfecciosos para uso sistémico", "L": "Antineoplásicos e inmunomoduladores",
    "M": "Sistema musculoesquelético", "N": "Sistema nervioso",
    "P": "Antiparasitarios, insecticidas y repelentes", "R": "Sistema respiratorio",
    "S": "Órganos de los sentidos", "V": "Varios",
}


# ----------------------------------------------------------------------------- CIMA
def resumir_medicamento(m):
    """Se queda solo con los campos que necesitamos de la respuesta de CIMA."""
    atcs = m.get("atcs") or []
    atc_mas_detallado = max(atcs, key=lambda a: a.get("nivel", 0), default={})
    atc_nivel1 = next((a for a in atcs if a.get("nivel") == 1), {})
    principios = [p.get("nombre", "") for p in (m.get("principiosActivos") or [])]
    return {
        "nregistro": m.get("nregistro"),
        "laboratorio": m.get("labtitular"),
        "atc_codigo": atc_mas_detallado.get("codigo"),
        "atc_nombre": atc_mas_detallado.get("nombre"),
        "grupo_atc_nombre": atc_nivel1.get("nombre"),
        "principio_activo": " + ".join(p for p in principios if p) or None,
        "comercializado": m.get("comerc"),
    }


def consultar_cima(cn):
    r = requests.get(URL_MEDICAMENTO, params={"cn": cn}, headers=CABECERAS, timeout=30)
    if r.status_code == 204 or not r.text.strip():
        return {"no_encontrado": True}
    r.raise_for_status()
    return resumir_medicamento(r.json())


def enriquecer(cns):
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    pendientes = [cn for cn in cns if cn not in cache]
    print(f"CIMA: {len(cns)} CN, {len(cns) - len(pendientes)} ya en caché, {len(pendientes)} por consultar")

    for i, cn in enumerate(pendientes, 1):
        try:
            cache[cn] = consultar_cima(cn)
        except Exception as e:
            print(f"  CN {cn}: error {e} (se reintentará la próxima vez)")
            continue
        if i % 50 == 0 or i == len(pendientes):
            print(f"  {i}/{len(pendientes)}")
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.2)  # no saturar la API

    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


# ----------------------------------------------------------------------------- Limpieza
def ms_a_fecha(serie):
    """Milisegundos UTC -> fecha en Madrid (sin hora)."""
    return (pd.to_datetime(serie, unit="ms", utc=True, errors="coerce")
              .dt.tz_convert(ZONA).dt.date)


def main():
    LIMPIOS.mkdir(exist_ok=True)
    CACHE.parent.mkdir(exist_ok=True)

    ruta = sorted(RAW.glob("aemps_*.json"))[-1]
    fecha_descarga = ruta.stem.replace("aemps_", "")
    print(f"Leyendo {ruta.name}")
    df = pd.DataFrame(json.loads(ruta.read_text(encoding="utf-8"))["resultados"])
    df["cn"] = df["cn"].astype(str)

    cache = enriquecer(df["cn"].tolist())
    extra = pd.DataFrame.from_dict({cn: cache.get(cn, {}) for cn in df["cn"]}, orient="index")
    extra.index.name = "cn"
    df = df.merge(extra.reset_index(), on="cn", how="left")

    df["fecha_inicio"] = ms_a_fecha(df["fini"])
    df["fecha_fin_prevista"] = ms_a_fecha(df["ffin"])
    df["dias_activo"] = (pd.Timestamp(fecha_descarga).date() - df["fecha_inicio"]).apply(lambda d: d.days)
    df["grupo_atc"] = df["atc_codigo"].str[0]
    df["grupo_atc_nombre"] = df["grupo_atc"].map(GRUPOS_ATC)
    df["es_vacuna"] = df["atc_codigo"].fillna("").str.startswith("J07")
    df["fecha_descarga"] = fecha_descarga

    df = df.rename(columns={"tipoProblemaSuministro": "tipo_problema", "observ": "observaciones"})
    columnas = ["fecha_descarga", "cn", "nombre", "principio_activo", "laboratorio",
                "atc_codigo", "atc_nombre", "grupo_atc", "grupo_atc_nombre", "es_vacuna",
                "tipo_problema", "observaciones", "fecha_inicio", "fecha_fin_prevista",
                "dias_activo", "nregistro", "comercializado"]
    df = df[[c for c in columnas if c in df.columns]]

    # utf-8-sig para que Excel muestre bien las tildes
    salida = LIMPIOS / f"aemps_enriquecido_{fecha_descarga}.csv"
    df.to_csv(salida, index=False, encoding="utf-8-sig")

    tipos = (df.groupby(["tipo_problema", "observaciones"]).size()
               .reset_index(name="n").sort_values(["tipo_problema", "n"], ascending=[True, False]))
    tipos.to_csv(LIMPIOS / "tipos_problema.csv", index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------------ Resumen
    print(f"\nGuardado {salida.name} ({len(df)} filas)")
    print(f"Con laboratorio: {df['laboratorio'].notna().mean():.0%}   "
          f"Con ATC: {df['atc_codigo'].notna().mean():.0%}   "
          f"Vacunas: {df['es_vacuna'].sum()}")
    print("\nTop 10 laboratorios:")
    print(df["laboratorio"].value_counts().head(10).to_string())
    print("\nPor grupo ATC:")
    print(df.groupby(["grupo_atc", "grupo_atc_nombre"], dropna=False).size()
            .sort_values(ascending=False).to_string())
    print(f"\nDías activo: mediana {df['dias_activo'].median():.0f}, máximo {df['dias_activo'].max()}")
    print("\nTipos de problema guardados en tipos_problema.csv")


if __name__ == "__main__":
    main()
