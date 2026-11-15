"""
Dashboard de desabastecimientos · Resumen, Buscador (con alternativas) y Alarmas.

Uso:
    streamlit run app.py

Lee de datos_limpios/:
    aemps_enriquecido_*.csv   (enriquecer_aemps.py)
    eventos.csv               (historico.py)
    alternativas.csv          (alternativas.py)
    alternativas_resumen.csv  (alternativas.py)
    tipos_significado.csv     (opcional, a mano: tipo_problema,significado)
"""

import html
import json
import math
from urllib.parse import urlencode
from datetime import timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

BASE = Path(__file__).parent
LIMPIOS = BASE / "datos_limpios"
CONFIG_ALARMAS = BASE / "config_alarmas.json"

TINTA, GRIS, LINEA = "#15181C", "#5A626D", "#D5D8DD"
ACENTO, ALERTA = "#12505A", "#8C1D18"
NARANJA = "#A84300"
COLOR_EVENTO = {  # rojo/naranja = malas noticias, verde = buenas, gris = neutro
    "Nuevo": ALERTA, "Reaparece": ALERTA, "Fin retrasado": NARANJA, "Sin fecha de fin": NARANJA,
    "Resuelto": ACENTO, "Fin adelantado": ACENTO, "Fecha de fin añadida": GRIS, "Cambio de tipo": GRIS,
}

st.set_page_config(page_title="Vigilancia de suministro", layout="wide")

# ----------------------------------------------------------------------------- Estilo
st.html(f"""
<link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
html, body, [class*="st-"], .stMarkdown, button, input, textarea, select {{
  font-family: 'Public Sans', system-ui, sans-serif !important;
}}
.block-container {{ padding-top: 2rem; max-width: 1360px; }}
h1 {{ font-weight: 600 !important; letter-spacing: -0.01em; font-size: 1.65rem !important;
      border-bottom: 1px solid {TINTA}; padding-bottom: .6rem !important; }}
[data-testid="stMetric"] {{ border-right: 1px solid {LINEA}; padding: 0 1.2rem .8rem 0; }}
[data-testid="stMetricLabel"] p {{ text-transform: uppercase; letter-spacing: .06em;
      font-size: .72rem !important; color: {GRIS}; }}
[data-testid="stMetricValue"] {{ font-size: 2.6rem !important; font-weight: 500;
      font-variant-numeric: tabular-nums; }}
.etiqueta {{ text-transform: uppercase; letter-spacing: .06em; font-size: .72rem;
      color: {GRIS}; font-weight: 500; margin: .4rem 0 .6rem; }}
.alerta {{ color: {ALERTA}; font-weight: 500; }}
.panel {{ background: #F6F7F8; border-top: 3px solid {ACENTO}; padding: 1.1rem 1.3rem 1.3rem; }}
.alt-fila {{ display: grid; grid-template-columns: 12px 1fr; gap: 10px;
      padding: .65rem 0; border-bottom: 1px solid #E1E4E8; }}
.alt-marca {{ width: 8px; height: 8px; margin-top: .45rem; }}
.alt-nombre {{ font-size: .9rem; font-weight: 500; }}
.alt-meta {{ font-size: .8rem; color: {GRIS}; }}
.nota {{ font-size: .8rem; color: {GRIS}; }}
.tabla {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
.tabla th {{ text-align: left; font-weight: 500; color: {GRIS}; text-transform: uppercase; font-size: .7rem;
      letter-spacing: .05em; padding: .55rem .6rem .55rem 0; border-top: 1px solid {TINTA};
      border-bottom: 1px solid {TINTA}; }}
.tabla td {{ padding: .6rem .6rem .6rem 0; border-bottom: 1px solid #E6E8EB; vertical-align: top; }}
.tabla {{ table-layout: auto; }}
.tabla td {{ white-space: normal; overflow-wrap: anywhere; }}
.tabla .nowrap {{ white-space: nowrap; overflow-wrap: normal; }}
.marca {{ display: inline-block; width: 7px; height: 7px; margin-right: 7px; vertical-align: 1px; }}
.tabla td.num, .tabla th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.buscador td {{ vertical-align: middle; }}
.buscador tr.sel td {{ background: #EAF2F1; }}
.buscador tr.sel td:first-child {{ box-shadow: inset 3px 0 0 {ACENTO}; padding-left: .6rem; }}
.buscador a.med {{ color: {TINTA}; font-weight: 500; text-decoration: none; }}
.buscador a.med:hover {{ color: {ACENTO}; text-decoration: underline; }}
.buscador tr.sel a.med {{ color: {ACENTO}; }}
/* Color de la marca aunque no se cargue .streamlit/config.toml */
button[kind="primary"], button[kind="primaryFormSubmit"] {{
      background-color: {ACENTO} !important; border-color: {ACENTO} !important; color: #FFFFFF !important; }}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {{
      background-color: #0A3238 !important; border-color: #0A3238 !important; }}
[data-testid="stButtonGroup"] button[kind*="Active"], [data-testid="stButtonGroup"] button[aria-checked="true"] {{
      color: {ACENTO} !important; border-color: {ACENTO} !important; background-color: #EAF2F1 !important; }}
[data-testid="stButtonGroup"] button[kind*="Active"] p {{ color: {ACENTO} !important; }}
[data-baseweb="tag"], [data-tag] {{ background-color: {ACENTO} !important; color: #FFFFFF !important; }}
input[type="checkbox"], input[type="radio"] {{ accent-color: {ACENTO}; }}
[data-testid="stCheckbox"] label span:first-child[style*="background"] {{ background-color: {ACENTO} !important;
      border-color: {ACENTO} !important; }}
input:focus, textarea:focus, [data-baseweb="select"] > div:focus-within {{ border-color: {ACENTO} !important; }}
.paginas {{ display: flex; gap: 1.2rem; align-items: baseline; margin: .8rem 0; font-size: .88rem; }}
</style>
""")


# ----------------------------------------------------------------------------- Datos
@st.cache_data
def leer_csv(nombre, **kw):
    ruta = LIMPIOS / nombre
    return pd.read_csv(ruta, **kw) if ruta.exists() else None


@st.cache_data
def cargar_activos():
    archivos = sorted(LIMPIOS.glob("aemps_enriquecido_*.csv"))
    if not archivos:
        return None, None
    df = pd.read_csv(archivos[-1], dtype={"cn": str, "nregistro": str},
                     parse_dates=["fecha_inicio", "fecha_fin_prevista"])
    df["es_vacuna"] = df["es_vacuna"].astype(bool)
    sig = leer_csv("tipos_significado.csv")
    if sig is not None:
        mapa = sig.set_index("tipo_problema")["significado"]
        df["tipo_texto"] = df["tipo_problema"].map(mapa).fillna("Tipo " + df["tipo_problema"].astype(str))
    else:
        df["tipo_texto"] = "Tipo " + df["tipo_problema"].astype(str)
    df["grupo_atc_texto"] = df["grupo_atc"].fillna("?") + " · " + df["grupo_atc_nombre"].fillna("Sin ATC")

    res = leer_csv("alternativas_resumen.csv", dtype={"cn_desabastecido": str})
    if res is not None:
        df = df.merge(res[["cn_desabastecido", "n_disponibles", "n_en_desabastecimiento"]]
                      .rename(columns={"cn_desabastecido": "cn"}), on="cn", how="left")
    else:
        df["n_disponibles"] = pd.NA
        df["n_en_desabastecimiento"] = pd.NA
    return df, pd.Timestamp(archivos[-1].stem.replace("aemps_enriquecido_", ""))


@st.cache_data
def cargar_eventos():
    ev = leer_csv("eventos.csv", dtype={"cn": str})
    if ev is None or ev.empty:
        return pd.DataFrame(columns=["fecha", "evento", "cn", "nombre", "etiqueta", "detalle"])
    ev["fecha"] = pd.to_datetime(ev["fecha"])
    nueva = pd.to_datetime(ev["fecha_fin_prevista"], errors="coerce")
    anterior = pd.to_datetime(ev["valor_anterior"], errors="coerce")

    def etiqueta(fila, n, a):
        if fila["evento"] == "cambio_fin_prevista":
            if pd.isna(n) and pd.notna(a):
                return "Sin fecha de fin"          # la AEMPS ha quitado la fecha prevista
            if pd.notna(n) and pd.isna(a):
                return "Fecha de fin añadida"
            if pd.notna(n) and pd.notna(a) and n > a:
                return "Fin retrasado"
            return "Fin adelantado"
        return {"nuevo": "Nuevo", "resuelto": "Resuelto", "reaparece": "Reaparece",
                "cambio_tipo": "Cambio de tipo"}.get(fila["evento"], fila["evento"])

    ev["etiqueta"] = [etiqueta(f, n, a) for (_, f), n, a in zip(ev.iterrows(), nueva, anterior)]
    fmt = lambda d: d.strftime("%d.%m.%Y") if pd.notna(d) else "sin fecha"
    ev["detalle"] = [f"{fmt(a)} → {fmt(n)}" if e == "cambio_fin_prevista" else ""
                     for e, n, a in zip(ev["evento"], nueva, anterior)]
    return ev


@st.cache_data
def cargar_alternativas():
    return leer_csv("alternativas.csv", dtype={"cn_desabastecido": str, "nregistro_alternativa": str})


df, hoy = cargar_activos()
if df is None:
    st.error("No hay datos en datos_limpios/. Ejecuta primero enriquecer_aemps.py.")
    st.stop()
eventos = cargar_eventos()
alternativas = cargar_alternativas()
tiene_alternativas = df["n_disponibles"].notna().any()


def etiqueta(texto):
    st.markdown(f'<div class="etiqueta">{texto}</div>', unsafe_allow_html=True)


def tabla_html(datos, columnas, numericas=(), ajustar=("nombre",), colores=None):
    """Tabla con el estilo del diseño: las columnas de `ajustar` parten el texto en
    varias líneas; el resto (fechas, códigos, tipos) se mantiene en una sola."""
    clase = lambda c: " ".join(filter(None, ["num" if c in numericas else "",
                                             "" if c in ajustar else "nowrap"]))
    cab = "".join(f'<th class="{clase(c)}">{t}</th>' for c, t in columnas.items())
    filas = ""
    for _, f in datos.iterrows():
        celdas = ""
        for c in columnas:
            v = f[c]
            if isinstance(v, pd.Timestamp):
                v = v.strftime("%d.%m.%Y")
            elif v is None or (not isinstance(v, str) and pd.isna(v)) or v == "":
                v = "—"
            texto = html.escape(str(v))
            if colores and c in colores and colores[c].get(v):
                color = colores[c][v]
                texto = (f'<span class="marca" style="background:{color}"></span>'
                         f'<span style="color:{color};font-weight:500">{texto}</span>')
            celdas += f'<td class="{clase(c)}">{texto}</td>'
        filas += f"<tr>{celdas}</tr>"
    st.html(f'<table class="tabla"><thead><tr>{cab}</tr></thead><tbody>{filas}</tbody></table>')


def barras(datos, campo, top=None):
    conteo = datos[campo].value_counts().rename_axis(campo).reset_index(name="n")
    if top:
        conteo = conteo.head(top)
    base = alt.Chart(conteo).encode(y=alt.Y(f"{campo}:N", sort="-x", title=None,
                                            axis=alt.Axis(labelLimit=240, labelColor=TINTA)))
    barra = base.mark_bar(color=ACENTO, height=9).encode(
        x=alt.X("n:Q", title=None, axis=None),
        tooltip=[alt.Tooltip(f"{campo}:N", title=" "), alt.Tooltip("n:Q", title="Presentaciones")])
    texto = base.mark_text(align="left", dx=4, color=TINTA, fontSize=12).encode(x="n:Q", text="n:Q")
    return ((barra + texto).properties(height=max(160, 22 * len(conteo)))
            .configure_view(stroke=None).configure_axis(grid=False, domain=False, ticks=False))


# ============================================================================= Resumen
def pagina_resumen():
    st.title(f"Resumen · {hoy:%d.%m.%Y}")

    ev_hoy = eventos[eventos["fecha"] == hoy]
    ev_7 = eventos[eventos["fecha"] > hoy - timedelta(days=7)]
    n = lambda e, et: int((e["etiqueta"] == et).sum())
    sin_alt = int((df["n_disponibles"] == 0).sum()) if tiene_alternativas else None

    avisos = n(ev_hoy, "Nuevo") + n(ev_hoy, "Fin retrasado")
    if avisos:
        st.page_link(pag_alarmas, label=f"{avisos} {'alarma' if avisos == 1 else 'alarmas'} hoy →")

    c = st.columns(5)
    c[0].metric("Activos", f"{len(df):,}".replace(",", "."))
    c[1].metric("Nuevos hoy", n(ev_hoy, "Nuevo"), help=f"{n(ev_7, 'Nuevo')} en 7 días")
    c[2].metric("Resueltos hoy", n(ev_hoy, "Resuelto"), help=f"{n(ev_7, 'Resuelto')} en 7 días")
    c[3].metric("Fin retrasado hoy", n(ev_hoy, "Fin retrasado"), help=f"{n(ev_7, 'Fin retrasado')} en 7 días")
    c[4].metric("Sin alternativa", sin_alt if sin_alt is not None else "—",
                help="Ninguna presentación con mismo principio activo, dosis y forma está disponible")

    st.write("")
    izq, der = st.columns(2, gap="large")
    with izq:
        etiqueta("Por grupo ATC · presentaciones activas")
        st.altair_chart(barras(df, "grupo_atc_texto"), width="stretch")
    with der:
        etiqueta("Top 10 laboratorios · presentaciones activas")
        st.altair_chart(barras(df, "laboratorio", top=10), width="stretch")

    etiqueta("Cambios de hoy")
    if ev_hoy.empty:
        st.markdown('<p class="nota">Sin cambios registrados hoy.</p>', unsafe_allow_html=True)
    else:
        tabla_html(ev_hoy, {"etiqueta": "Tipo", "nombre": "Medicamento", "detalle": "Fin previsto"},
                   colores={"etiqueta": COLOR_EVENTO})


# ============================================================================= Configuración de alarmas
def leer_config():
    defecto = {"reglas": ["Nuevo", "Fin retrasado", "Sin alternativa"], "grupos_atc": [],
               "laboratorios": [], "medicamentos": {}, "canal": "Email", "destinatarios": ""}
    try:
        cfg = {**defecto, **json.loads(CONFIG_ALARMAS.read_text(encoding="utf-8"))}
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = defecto
    if isinstance(cfg["medicamentos"], list):  # formato antiguo: lista de CN
        cfg["medicamentos"] = {cn: "" for cn in cfg["medicamentos"]}
    return cfg


def guardar_config(cfg):
    CONFIG_ALARMAS.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def vigilar(cn, nombre, activar=True):
    cfg = leer_config()
    if activar:
        cfg["medicamentos"][cn] = nombre
    else:
        cfg["medicamentos"].pop(cn, None)
    guardar_config(cfg)


# ============================================================================= Buscador
def panel_alternativas(fila):
    cn = fila["cn"]
    alts = (alternativas[alternativas["cn_desabastecido"] == cn]
            if alternativas is not None else pd.DataFrame())
    no_sust = bool(not alts.empty and alts["desabastecido_no_sustituible"].any())
    equiv = alts[alts["equivalente"]] if not alts.empty else alts
    prescripcion = (alts[alts["requiere_prescripcion"]]
                    if not alts.empty and "requiere_prescripcion" in alts else alts.iloc[0:0])
    otras = alts[~alts["equivalente"] & ~alts.index.isin(prescripcion.index)] if not alts.empty else alts
    disp = equiv[equiv["estado"] == "Disponible"] if not equiv.empty else equiv

    filas_html = ""
    for _, a in equiv.sort_values("estado").iterrows():
        color = ACENTO if a["estado"] == "Disponible" else ALERTA
        filas_html += (f'<div class="alt-fila"><span class="alt-marca" style="background:{color}"></span>'
                       f'<div><div class="alt-nombre">{a["nombre_alternativa"]}</div>'
                       f'<div class="alt-meta">{a["laboratorio_alternativa"] or ""} · '
                       f'<span style="color:{color};font-weight:500">{a["estado"]}</span></div></div></div>')

    avisos = ""
    if fila["es_vacuna"]:
        avisos += '<p class="alerta">Vacuna: no se proponen alternativas automáticas. Consultar.</p>'
    elif no_sust:
        avisos += ('<p class="alerta">No sustituible según CIMA: cualquier cambio de presentación '
                   'requiere una nueva prescripción médica.</p>')
    if equiv.empty and not fila["es_vacuna"] and not no_sust:
        filas_html = '<p class="nota">No hay presentaciones equivalentes (mismo principio activo, dosis y forma).</p>'
    if not prescripcion.empty:
        filas_html += '<div class="etiqueta" style="margin-top:1rem">Requieren nueva prescripción</div>'
        for _, a in prescripcion.sort_values("estado").iterrows():
            color = GRIS if a["estado"] == "Disponible" else ALERTA
            filas_html += (f'<div class="alt-fila"><span class="alt-marca" style="background:{color}"></span>'
                           f'<div><div class="alt-nombre">{a["nombre_alternativa"]}</div>'
                           f'<div class="alt-meta">{a["laboratorio_alternativa"] or ""} · {a["estado"]}</div></div></div>')

    st.html(f"""
    <div class="panel">
      <div class="etiqueta" style="margin-top:0">Alternativas</div>
      <div style="font-size:1.05rem;font-weight:600;line-height:1.3">{fila['principio_activo'] or fila['nombre']}</div>
      <div class="nota" style="margin:.2rem 0 1rem">{fila['nombre']}</div>
      {avisos}
      <div style="display:flex;gap:28px;padding-bottom:.8rem;border-bottom:1px solid {LINEA}">
        <div><div style="font-size:1.7rem;font-weight:500;color:{ACENTO}">{len(disp)}</div>
             <div class="nota">disponibles</div></div>
        <div><div style="font-size:1.7rem;font-weight:500;color:{ALERTA}">{len(equiv) - len(disp)}</div>
             <div class="nota">también en desabastecimiento</div></div>
      </div>
      {filas_html}
      <div class="etiqueta" style="margin-top:1rem">Otras dosis o formas del mismo principio activo</div>
      <div class="nota" style="color:{TINTA}">{len(otras)} presentaciones comercializadas · consultar con el médico</div>
      <p class="nota" style="margin-top:1rem">La sustitución la decide el profesional sanitario. Esta lista solo
      indica qué presentaciones no tienen un problema de suministro activo.</p>
    </div>""")
    if cn in leer_config()["medicamentos"]:
        st.button("Dejar de vigilar", key=f"novig-{cn}", on_click=vigilar, args=(cn, fila["nombre"], False))
        st.markdown('<p class="nota">Recibirás alarmas de este medicamento.</p>', unsafe_allow_html=True)
    else:
        st.button("Vigilar este medicamento", key=f"vig-{cn}", on_click=vigilar, args=(cn, fila["nombre"]),
                  help="Recibirás una alarma si cambia su situación, aunque no esté en tus laboratorios o grupos ATC")


def pagina_buscador():
    st.title("Buscador")

    # Los filtros viven en la URL (?texto=...&lab=...): así, al pinchar en un medicamento
    # (un enlace) la página se recarga con los mismos filtros y el medicamento elegido.
    qp = st.query_params
    lista = lambda k: [v for v in qp.get(k, "").split("|") if v]
    labs_todos = sorted(df["laboratorio"].dropna().unique())
    grupos_todos = sorted(df["grupo_atc_texto"].unique())
    tipos_todos = sorted(df["tipo_texto"].unique())

    # Valor inicial de cada filtro: el de la URL, solo la primera vez (con clave fija el widget
    # conserva lo que elija la usuaria aunque luego cambie la URL)
    iniciales = {"f_texto": qp.get("texto", ""),
                 "f_lab": [x for x in lista("lab") if x in labs_todos],
                 "f_atc": [x for x in lista("atc") if x in grupos_todos],
                 "f_tipo": [x for x in lista("tipo") if x in tipos_todos],
                 "f_sinalt": qp.get("sinalt") == "1", "f_vac": qp.get("vac") == "1"}
    for clave, valor in iniciales.items():
        st.session_state.setdefault(clave, valor)

    c = st.columns([2, 1, 1, 1])
    texto = c[0].text_input("Medicamento o principio activo", key="f_texto", placeholder="p. ej. lenalidomida")
    labs = c[1].multiselect("Laboratorio", labs_todos, key="f_lab", placeholder="Todos")
    grupos = c[2].multiselect("Grupo ATC", grupos_todos, key="f_atc", placeholder="Todos")
    tipos = c[3].multiselect("Tipo de problema", tipos_todos, key="f_tipo", placeholder="Todos")
    k = st.columns([1, 1, 4])
    solo_sin_alt = k[0].checkbox("Solo sin alternativa", key="f_sinalt", disabled=not tiene_alternativas)
    solo_vacunas = k[1].checkbox("Solo vacunas", key="f_vac")

    f = df
    if texto:
        t = texto.lower()
        f = f[f["nombre"].str.lower().str.contains(t, regex=False)
              | f["principio_activo"].fillna("").str.lower().str.contains(t, regex=False)]
    if labs:
        f = f[f["laboratorio"].isin(labs)]
    if grupos:
        f = f[f["grupo_atc_texto"].isin(grupos)]
    if tipos:
        f = f[f["tipo_texto"].isin(tipos)]
    if solo_sin_alt:
        f = f[f["n_disponibles"] == 0]
    if solo_vacunas:
        f = f[f["es_vacuna"]]
    f = f.sort_values("fecha_inicio", ascending=False).reset_index(drop=True)

    POR_PAGINA = 25
    n_paginas = max(1, math.ceil(len(f) / POR_PAGINA))
    try:
        pagina = min(max(int(qp.get("pag", 1)), 1), n_paginas)
    except ValueError:
        pagina = 1
    seleccion = qp.get("cn")
    trozo = f.iloc[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]

    filtros = {"texto": texto, "lab": "|".join(labs), "atc": "|".join(grupos), "tipo": "|".join(tipos),
               "sinalt": "1" if solo_sin_alt else "", "vac": "1" if solo_vacunas else ""}
    filtros = {k: v for k, v in filtros.items() if v}
    # Si han cambiado los filtros, se vuelve a la página 1
    antes = {k: qp.get(k) for k in ("texto", "lab", "atc", "tipo", "sinalt", "vac") if qp.get(k)}
    if antes != filtros:
        pagina, trozo = 1, f.iloc[:POR_PAGINA]
    st.query_params.from_dict({**filtros, **({"pag": str(pagina)} if pagina > 1 else {}),
                               **({"cn": seleccion} if seleccion else {})})
    enlace = lambda **extra: "?" + urlencode({**filtros, "pag": pagina, **extra})

    izq, der = st.columns([2, 1], gap="large")
    with izq:
        st.markdown(f'<div class="nota">{len(f)} resultados · pincha en un medicamento para ver sus alternativas</div>',
                    unsafe_allow_html=True)
        filas = ""
        for _, fila in trozo.iterrows():
            cn = fila["cn"]
            fin_prev = fila["fecha_fin_prevista"]
            n_alt = fila["n_disponibles"]
            lab = fila["laboratorio"] if isinstance(fila["laboratorio"], str) else "—"
            filas += (
                f'<tr class="{"sel" if cn == seleccion else ""}">'
                f'<td class="nowrap">{cn}</td>'
                f'<td><a class="med" href="{enlace(cn=cn)}" target="_self">{html.escape(fila["nombre"])}</a></td>'
                f'<td>{html.escape(lab)}</td>'
                f'<td>{html.escape(fila["tipo_texto"])}</td>'
                f'<td class="nowrap">{fin_prev.strftime("%d.%m.%Y") if pd.notna(fin_prev) else "—"}</td>'
                f'<td class="num">{int(n_alt) if pd.notna(n_alt) else "—"}</td></tr>')
        st.html(f"""<table class="tabla buscador"><thead><tr>
            <th>CN</th><th>Medicamento</th><th>Laboratorio</th><th>Situación</th>
            <th class="nowrap">Fin previsto</th><th class="num">Altern.</th></tr></thead>
            <tbody>{filas}</tbody></table>""")

        navegacion = []
        if pagina > 1:
            navegacion.append(f'<a href="{enlace(pag=pagina - 1)}" target="_self">← Anterior</a>')
        if n_paginas > 1:
            navegacion.append(f'<span class="nota">Página {pagina} de {n_paginas}</span>')
        if pagina < n_paginas:
            navegacion.append(f'<a href="{enlace(pag=pagina + 1)}" target="_self">Siguiente →</a>')
        if navegacion:
            st.html(f'<div class="paginas">{"".join(navegacion)}</div>')
        tabla = f[["cn", "nombre", "laboratorio", "tipo_texto", "fecha_fin_prevista", "n_disponibles"]]
        st.download_button("Descargar CSV", tabla.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"desabastecimientos_{hoy:%Y-%m-%d}.csv", mime="text/csv")
    with der:
        elegida = df[df["cn"] == seleccion]
        if not elegida.empty:
            panel_alternativas(elegida.iloc[0])
        elif alternativas is None:
            st.info("Ejecuta alternativas.py para ver alternativas por principio activo.")
        else:
            st.markdown('<div class="panel"><div class="etiqueta" style="margin-top:0">Alternativas</div>'
                        '<p class="nota">Pincha en el nombre de un medicamento de la lista.</p></div>',
                        unsafe_allow_html=True)


# ============================================================================= Alarmas
def pagina_alarmas():
    st.title("Alarmas")
    izq, der = st.columns([5, 3], gap="large")

    with izq:
        etiquetas = ["Todas"] + sorted(eventos["etiqueta"].unique())
        conteo = eventos["etiqueta"].value_counts()
        filtro = st.segmented_control(
            "Tipo", etiquetas, default="Todas", label_visibility="collapsed",
            format_func=lambda e: f"{e} {len(eventos) if e == 'Todas' else conteo.get(e, 0)}")
        ev = eventos if filtro in (None, "Todas") else eventos[eventos["etiqueta"] == filtro]
        if ev.empty:
            st.markdown('<p class="nota">Todavía no hay cambios registrados: hacen falta al menos '
                        'dos días de descargas.</p>', unsafe_allow_html=True)
        else:
            ev = ev.sort_values("fecha", ascending=False)
            tabla_html(ev.head(200), {"fecha": "Fecha", "etiqueta": "Tipo", "cn": "CN",
                                      "nombre": "Medicamento", "detalle": "Fin previsto"},
                       colores={"etiqueta": COLOR_EVENTO})
            if len(ev) > 200:
                st.markdown(f'<p class="nota">Mostrando los 200 cambios más recientes de {len(ev)}.</p>',
                            unsafe_allow_html=True)

    with der:
        cfg = leer_config()
        with st.form("config"):
            st.subheader("Qué vigilar")
            reglas = st.multiselect("Avisar cuando", ["Nuevo", "Fin retrasado", "Sin alternativa", "Resuelto"],
                                    default=cfg["reglas"], placeholder="Ninguna")
            grupos = st.multiselect("Grupos ATC", sorted(df["grupo_atc_texto"].unique()),
                                    default=[g for g in cfg["grupos_atc"] if g in set(df["grupo_atc_texto"])],
                                    placeholder="Todos")
            labs_todos = sorted(df["laboratorio"].dropna().unique())
            labs = st.multiselect("Laboratorios", labs_todos,
                                  default=[l for l in cfg["laboratorios"] if l in labs_todos],
                                  placeholder="Ninguno")
            canal = st.selectbox("Enviar por", ["Email", "Telegram", "Teams"],
                                 index=["Email", "Telegram", "Teams"].index(cfg["canal"]))
            dest = st.text_input("Destinatarios", cfg["destinatarios"])
            if st.form_submit_button("Guardar", type="primary"):
                guardar_config({**leer_config(), "reglas": reglas, "grupos_atc": grupos,
                                "laboratorios": labs, "canal": canal, "destinatarios": dest})
                st.success("Configuración guardada.")

        st.subheader("Medicamentos vigilados")
        st.caption("Recibes alarmas de estos medicamentos aunque no sean de los laboratorios o grupos "
                   "de arriba (por ejemplo, los productos propios). Se añaden desde el Buscador o con su "
                   "código nacional, aunque ahora no estén en desabastecimiento.")
        if not leer_config()["medicamentos"]:
            st.caption("Todavía no vigilas ningún medicamento.")
        nombres = dict(zip(df["cn"], df["nombre"]))
        for cn, nombre in leer_config()["medicamentos"].items():
            m = st.columns([5, 1], vertical_alignment="center")
            nombre = nombres.get(cn) or nombre or "No está en desabastecimiento ahora"
            m[0].markdown(f"**{cn}** · {nombre}")
            m[1].button("Quitar", key=f"quitar-{cn}", type="tertiary", on_click=vigilar, args=(cn, "", False))
        with st.form("anadir", clear_on_submit=True, border=False):
            a = st.columns([3, 1], vertical_alignment="bottom")
            nuevo = a[0].text_input("Añadir por código nacional", placeholder="p. ej. 729828")
            if a[1].form_submit_button("Añadir") and nuevo.strip():
                vigilar(nuevo.strip(), nombres.get(nuevo.strip(), ""))
                st.rerun()
        st.caption("El envío automático se activará con el motor de alarmas.")


# ============================================================================= Navegación
pag_resumen = st.Page(pagina_resumen, title="Resumen", url_path="resumen", default=True)
pag_buscador = st.Page(pagina_buscador, title="Buscador", url_path="buscador")
pag_alarmas = st.Page(pagina_alarmas, title="Alarmas", url_path="alarmas")
st.navigation([pag_resumen, pag_buscador, pag_alarmas], position="top").run()
