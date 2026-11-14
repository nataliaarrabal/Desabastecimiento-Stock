"""
Descarga diaria de datos de desabastecimiento (AEMPS + EMA).

Guarda una copia por día en la carpeta datos_raw/:
    datos_raw/aemps_2026-11-14.json
    datos_raw/ema_2026-11-14.xlsx

Uso:
    pip install requests
    python descarga_diaria.py

Si un día ya está descargado, no lo vuelve a descargar.
"""

import json
import time
from datetime import date
from pathlib import Path

import requests

CARPETA = Path(__file__).parent / "datos_raw"
HOY = date.today().isoformat()

URL_AEMPS = "https://cima.aemps.es/cima/rest/psuministro"
URL_EMA = "https://www.ema.europa.eu/en/documents/report/medicines-output-shortages-report_en.xlsx"

CABECERAS = {"User-Agent": "Desabastecimiento-stck/0.1 (uso académico)"}


def descargar_aemps():
    """Recorre todas las páginas de la API de problemas de suministro de CIMA."""
    destino = CARPETA / f"aemps_{HOY}.json"
    if destino.exists():
        print(f"AEMPS: ya existe {destino.name}, lo salto")
        return

    resultados, pagina = [], 1
    while True:
        r = requests.get(URL_AEMPS, params={"pagina": pagina}, headers=CABECERAS, timeout=60)
        r.raise_for_status()
        datos = r.json()
        lote = datos.get("resultados", [])
        resultados.extend(lote)
        total = datos.get("totalFilas", len(resultados))
        print(f"AEMPS: página {pagina} -> {len(resultados)}/{total}")
        if not lote or len(resultados) >= total:
            break
        pagina += 1
        time.sleep(0.5)  # no saturar la API

    destino.write_text(
        json.dumps({"fecha_descarga": HOY, "total": len(resultados), "resultados": resultados},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"AEMPS: guardados {len(resultados)} registros en {destino.name}")


def descargar_ema():
    """Descarga el Excel de shortages que la EMA regenera cada noche."""
    destino = CARPETA / f"ema_{HOY}.xlsx"
    if destino.exists():
        print(f"EMA: ya existe {destino.name}, lo salto")
        return

    r = requests.get(URL_EMA, headers=CABECERAS, timeout=120)
    r.raise_for_status()
    destino.write_bytes(r.content)
    print(f"EMA: guardado {destino.name} ({len(r.content) / 1024:.0f} KB)")


if __name__ == "__main__":
    CARPETA.mkdir(exist_ok=True)
    # Cada fuente por separado: si una falla, la otra se guarda igual
    for nombre, funcion in [("AEMPS", descargar_aemps), ("EMA", descargar_ema)]:
        try:
            funcion()
        except Exception as e:
            print(f"{nombre}: ERROR -> {e}")
            with open(CARPETA / "errores.log", "a", encoding="utf-8") as f:
                f.write(f"{HOY} {nombre}: {e}\n")
