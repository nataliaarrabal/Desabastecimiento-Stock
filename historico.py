"""
Paso 6: construir el histórico comparando las descargas diarias de la AEMPS.

La AEMPS solo publica los problemas de suministro ACTIVOS. Comparando cada día
con el anterior sabemos:
  - qué desabastecimientos son NUEVOS (aparecen),
  - cuáles se han RESUELTO (desaparecen) y en qué fecha,
  - cuáles han CAMBIADO (fecha de fin prevista o tipo de problema).

Un "episodio" es un desabastecimiento concreto: código nacional (cn) + fecha de
inicio (fini). Si un mismo CN se resuelve y vuelve a tener otro problema más
adelante, con otra fecha de inicio, cuenta como un episodio nuevo.

Salidas (en datos_limpios/):
  historico_episodios.csv -> una fila por episodio, con estado, fecha de resolución y duración
  eventos.csv             -> una fila por cambio detectado (nuevo / resuelto / reaparece / cambio)

Uso:
    python historico.py
"""

import json
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent
RAW = BASE / "datos_raw"
LIMPIOS = BASE / "datos_limpios"
ZONA = "Europe/Madrid"


def ms_a_fecha(ms):
    if ms is None or pd.isna(ms):
        return None
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").tz_convert(ZONA).date()


def cargar_descargas():
    """Devuelve [(fecha, {clave: registro}), ...] ordenado por fecha."""
    descargas = []
    for ruta in sorted(RAW.glob("aemps_*.json")):
        fecha = pd.Timestamp(ruta.stem.replace("aemps_", "")).date()
        registros = json.loads(ruta.read_text(encoding="utf-8"))["resultados"]
        por_clave = {}
        for r in registros:
            clave = (str(r["cn"]), r["fini"])
            por_clave[clave] = {
                "cn": str(r["cn"]),
                "nombre": r.get("nombre"),
                "fecha_inicio": ms_a_fecha(r.get("fini")),
                "fecha_fin_prevista": ms_a_fecha(r.get("ffin")),
                "tipo_problema": r.get("tipoProblemaSuministro"),
            }
        descargas.append((fecha, por_clave))
    return descargas


def construir(descargas):
    episodios, eventos = {}, []
    anteriores = set()

    for i, (fecha, hoy) in enumerate(descargas):
        actuales = set(hoy)

        for clave in actuales:
            reg = hoy[clave]
            ep = episodios.get(clave)
            if ep is None:
                episodios[clave] = {**reg, "primera_vez_visto": fecha, "ultima_vez_visto": fecha,
                                    "fecha_resolucion": None, "n_cambios_fin_prevista": 0}
                # El primer día no sabemos qué es nuevo: todo es lo que ya había
                if i > 0:
                    eventos.append({"fecha": fecha, "evento": "nuevo", **reg})
                continue

            if ep["fecha_resolucion"] is not None:  # había desaparecido y vuelve
                eventos.append({"fecha": fecha, "evento": "reaparece", **reg})
                ep["fecha_resolucion"] = None
            if reg["fecha_fin_prevista"] != ep["fecha_fin_prevista"]:
                eventos.append({"fecha": fecha, "evento": "cambio_fin_prevista", **reg,
                                "valor_anterior": ep["fecha_fin_prevista"]})
                ep["n_cambios_fin_prevista"] += 1
            if reg["tipo_problema"] != ep["tipo_problema"]:
                eventos.append({"fecha": fecha, "evento": "cambio_tipo", **reg,
                                "valor_anterior": ep["tipo_problema"]})
            ep.update({k: reg[k] for k in ("nombre", "fecha_fin_prevista", "tipo_problema")})
            ep["ultima_vez_visto"] = fecha

        for clave in anteriores - actuales:
            ep = episodios[clave]
            ep["fecha_resolucion"] = fecha
            eventos.append({"fecha": fecha, "evento": "resuelto",
                            **{k: ep[k] for k in ("cn", "nombre", "fecha_inicio",
                                                  "fecha_fin_prevista", "tipo_problema")}})
        anteriores = actuales

    return episodios, eventos


def main():
    descargas = cargar_descargas()
    if not descargas:
        print("No hay descargas en datos_raw/")
        return
    fechas = [f for f, _ in descargas]
    print(f"{len(descargas)} descargas: de {fechas[0]} a {fechas[-1]}")

    # Avisar de días sin descarga: la fecha de resolución puede estar desplazada
    huecos = [(a, b) for a, b in zip(fechas, fechas[1:]) if (b - a).days > 1]
    for a, b in huecos:
        print(f"  Aviso: no hay descargas entre {a} y {b}")

    episodios, eventos = construir(descargas)
    ultima = fechas[-1]

    ep = pd.DataFrame(episodios.values())
    ep["estado"] = ep["fecha_resolucion"].apply(lambda x: "activo" if x is None else "resuelto")
    fin = ep["fecha_resolucion"].fillna(ultima)
    ep["duracion_dias"] = [(f - i).days if i else None for f, i in zip(fin, ep["fecha_inicio"])]
    # Si el episodio ya existía el primer día de descarga, no vimos su inicio desde aquí
    ep["visto_desde_inicio"] = ep["primera_vez_visto"] > fechas[0]

    LIMPIOS.mkdir(exist_ok=True)
    ep.to_csv(LIMPIOS / "historico_episodios.csv", index=False, encoding="utf-8-sig")
    ev = pd.DataFrame(eventos, columns=["fecha", "evento", "cn", "nombre", "fecha_inicio",
                                        "fecha_fin_prevista", "tipo_problema", "valor_anterior"])
    ev.to_csv(LIMPIOS / "eventos.csv", index=False, encoding="utf-8-sig")

    print(f"\nEpisodios: {len(ep)}  (activos {(ep.estado == 'activo').sum()}, "
          f"resueltos {(ep.estado == 'resuelto').sum()})")
    if not ev.empty:
        print("\nEventos por día:")
        print(ev.pivot_table(index="fecha", columns="evento", values="cn",
                             aggfunc="count", fill_value=0).to_string())
        print(f"\nÚltimos eventos ({ultima}):")
        print(ev[ev.fecha == ultima][["evento", "cn", "nombre"]].to_string(index=False))
    else:
        print("Todavía no hay eventos (hace falta más de una descarga).")


if __name__ == "__main__":
    main()
