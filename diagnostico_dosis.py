"""
Enseña, para uno o varios códigos nacionales, cómo compara alternativas.py:
la dosis y la forma del medicamento en desabastecimiento frente a las de
cada candidata, en texto original y normalizadas (del nombre o, si no, del campo dosis).

Uso:
    python diagnostico_dosis.py 703870 672287 653446 724969
"""

import json
import sys
from pathlib import Path

import pandas as pd

from alternativas import CACHE, dosis_de

LIMPIOS = Path(__file__).parent / "datos_limpios"

df = pd.read_csv(sorted(LIMPIOS.glob("aemps_enriquecido_*.csv"))[-1],
                 dtype={"cn": str, "nregistro": str})
cache = json.loads(CACHE.read_text(encoding="utf-8"))

for cn in sys.argv[1:]:
    fila = df[df["cn"] == cn]
    if fila.empty:
        print(f"\n### CN {cn}: no está en los desabastecimientos de hoy")
        continue
    d = fila.iloc[0]
    principio = str(d["principio_activo"]).split(" + ")[0]
    candidatos = cache.get(principio, {}).get("resultados", [])
    propio = next((c for c in candidatos if c["nregistro"] == d["nregistro"]), None)

    print(f"\n### CN {cn} · {d['nombre']}")
    print(f"principio_activo (enriquecido): {d['principio_activo']!r} -> búsqueda por {principio!r}")
    print(f"nregistro: {d['nregistro']} · candidatas en la búsqueda: {len(candidatos)}")
    if not propio:
        print("  ¡OJO! el propio medicamento NO aparece en su búsqueda: no se puede comparar")
    else:
        print(f"  PROPIO  dosis={propio['dosis_texto']!r} -> {dosis_de(propio)!r}"
              f" · forma={propio['forma']!r} · vtm={propio['vtm']!r}")
    for c in candidatos[:12]:
        if propio and c["nregistro"] == propio["nregistro"]:
            continue
        print(f"  - {c['nombre'][:60]:60} dosis={c['dosis_texto']!r} -> "
              f"{dosis_de(c)!r} · forma={c['forma']!r} · comerc={c['comercializado']}")
