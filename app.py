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

import base64
import html
import json
import math
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

BASE = Path(__file__).parent
LIMPIOS = BASE / "datos_limpios"
CONFIG_ALARMAS = BASE / "config_alarmas.json"

# ----------------------------------------------------------------------------- Colores
TINTA, GRIS, GRIS_SUAVE = "#15181C", "#4A525D", "#5A626D"
FONDO, TARJETA, BORDE, LINEA = "#F1F3F6", "#FFFFFF", "#E1E5EA", "#EEF0F3"
ACENTO, ALERTA, NARANJA = "#12505A", "#8C1D18", "#8A4B00"
BARRA, BARRA_SUAVE = "#8FA3B8", "#C9D1DA"
# (fondo, texto) de las etiquetas de color
VERDE_P, ROJO_P, NARANJA_P, GRIS_P = ("#E8F2F0", ACENTO), ("#FBEAEA", ALERTA), ("#FBEFE3", NARANJA), ("#EEF0F3", GRIS)
PILDORA_EVENTO = {"Nuevo": ROJO_P, "Reaparece": ROJO_P, "Fin retrasado": NARANJA_P, "Sin fecha de fin": NARANJA_P,
                  "Resuelto": VERDE_P, "Fin adelantado": VERDE_P, "Fecha de fin añadida": GRIS_P,
                  "Cambio de tipo": GRIS_P}
# Significado de los tipos de problema de la AEMPS, deducido de sus observaciones.
# Se puede corregir o completar con datos_limpios/tipos_significado.csv
SIGNIFICADO_TIPO = {3: "Sin alternativa", 5: "Hay alternativa", 12: "Distribución controlada"}
# El motor de alternativas (alternativas.py) sigue funcionando y generando datos, pero de
# momento no se muestra en el dashboard. Para volver a enseñarlo: True.
MOSTRAR_ALTERNATIVAS = False
POR_PAGINA = 10  # filas por página en todas las tablas
LISTA_POR_DEFECTO = "Mis medicamentos"

st.set_page_config(page_title="Vigilancia de suministro", layout="wide")

CSS = """
<link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
html, body, [class*="st-"], .stMarkdown, button, input, textarea, select {
  font-family: 'Public Sans', system-ui, sans-serif !important; }
/* Los iconos de Streamlit usan su propia fuente: sin esto se ve el nombre del icono ("expand_less") */
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {
  font-family: 'Material Symbols Rounded' !important; }
[data-testid="stApp"], [data-testid="stBottomBlockContainer"] { background: __FONDO__ !important; overflow-x: hidden; }
[data-testid="stHeader"] { display: none; }
.block-container { padding-top: 0 !important; max-width: 1360px; }
[data-testid="stMain"], [data-testid="stAppViewContainer"], [data-testid="stMainBlockContainer"] { padding-top: 0 !important; margin-top: 0 !important; }
[data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"] > div:first-child { margin-top: 0 !important; }
.cabecera { margin-top: -1rem !important; }
a { color: __ACENTO__; text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { font-weight: 600 !important; font-size: 1.5rem !important; padding: 0 !important; margin: 0 !important; }
h2, h3 { font-weight: 600 !important; }

/* Cabecera oscura a todo el ancho */
.cabecera { background: __TINTA__; color: #FFFFFF; margin: 0 calc(50% - 50vw) 1.6rem; }
.cabecera-in { max-width: 1360px; margin: 0 auto; padding: 0 3rem; display: flex; flex-wrap: wrap;
  align-items: stretch; gap: 40px; min-height: 56px; }
.marca-app { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 15px; }
.marca-app img { flex: none; display: block; }
.menu { display: flex; flex-wrap: wrap; gap: 28px; }
.menu a { display: flex; align-items: center; color: #AEB6C0 !important; font-size: 14px; text-decoration: none !important;
  border-bottom: 2px solid transparent; min-height: 44px; }
.menu a:hover { color: #FFFFFF !important; }
.menu a.activa { color: #FFFFFF !important; border-bottom-color: #4FB3A9; }
.fecha-datos { margin-left: auto; display: flex; align-items: center; font-size: 12px; color: #AEB6C0; }

/* Tarjetas: cualquier contenedor con key="tarjeta-..." */
[class*="st-key-tarjeta"] { background: __TARJETA__ !important; border: 1px solid __BORDE__ !important;
  border-radius: 10px !important; padding: 18px 22px !important; }
.tarjeta-html { background: __TARJETA__; border: 1px solid __BORDE__; border-radius: 10px; padding: 18px 20px; }
.titulo-tarjeta { font-size: 15px; font-weight: 600; margin: 0 0 12px; }

/* Indicadores */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; }
.kpi-label { font-size: 13px; color: __GRIS__; font-weight: 500; }
.kpi-num { font-size: 36px; font-weight: 600; margin-top: 6px; line-height: 1.1; font-variant-numeric: tabular-nums; }
.kpi-ctx { font-size: 12px; color: __GRIS_SUAVE__; margin-top: 6px; }
.kpi-alerta { border-top: 3px solid var(--c); border-radius: 0 0 10px 10px; padding-top: 16px; }
.kpi-alerta .kpi-label { color: var(--c); font-weight: 600; }
.kpi-alerta .kpi-num { color: var(--c); }

/* Barras */
.barra-fila { display: grid; grid-template-columns: 210px minmax(0, 1fr) 40px; align-items: center; gap: 12px;
  font-size: 13px; margin-bottom: 8px; }
.barra-fila .nombre { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.barra-fondo { height: 10px; background: __FONDO__; border-radius: 0 3px 3px 0; }
.barra-fondo div { height: 10px; border-radius: 0 3px 3px 0; }
.barra-fila .n { text-align: right; font-variant-numeric: tabular-nums; }
.leyenda { font-size: 12px; color: __GRIS_SUAVE__; }
.leyenda i { display: inline-block; width: 8px; height: 8px; margin-right: 6px; }

/* Etiquetas de color */
.pildora { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  white-space: nowrap; }

/* Tablas */
.tabla { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.tabla th { text-align: left; font-weight: 500; font-size: 12px; color: __GRIS__; background: #F8F9FB;
  padding: 10px 12px; }
.tabla td { padding: 11px 12px; border-top: 1px solid __LINEA__; vertical-align: middle;
  white-space: normal; overflow-wrap: anywhere; }
.tabla .nowrap { white-space: nowrap; overflow-wrap: normal; }
.tabla .num { text-align: right; font-variant-numeric: tabular-nums; }
.tabla td:first-child, .tabla th:first-child { padding-left: 4px; }
.buscador tr.sel td { background: #F2F8F7; }
.buscador tr.sel td:first-child { box-shadow: inset 3px 0 0 __ACENTO__; padding-left: 12px; }
.tabla a.med { color: __TINTA__ !important; font-weight: 500; text-decoration: none !important; }
.tabla a.med:hover { color: __ACENTO__ !important; text-decoration: underline !important; }
.buscador tr.sel a.med { color: __ACENTO__ !important; }
.sub { font-size: 12px; color: __GRIS_SUAVE__; margin-top: 2px; }
.paginas { display: flex; justify-content: center; gap: 10px; align-items: center; padding: 14px 0 4px;
  font-size: 13px; color: __GRIS__; }
.paginas a { display: inline-flex; align-items: center; min-height: 34px; padding: 0 14px;
  border: 1px solid #C9D0D8; border-radius: 6px; color: __TINTA__ !important; text-decoration: none !important;
  font-weight: 500; background: #FFFFFF; }
.paginas a:hover { border-color: __ACENTO__; color: __ACENTO__ !important; background: #E8F2F0; }

[class*="st-key-paginador"] button { min-height: 34px; border-radius: 6px; }
[class*="st-key-paginador"] p { margin: 0; }

/* Botón «Mis listas» y su desplegable */
.st-key-titulo-derecha { display: flex; flex-direction: row !important; justify-content: flex-end;
  align-items: center; gap: 16px !important; }
.st-key-titulo-derecha > div { width: auto !important; }
[data-testid="stPopoverBody"] { min-width: 460px; max-width: 520px; }
[data-testid="stPopover"] button { border-radius: 6px; font-weight: 500; }

/* Panel de alternativas */
.recuentos { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 0 0 12px; }
.recuento { border-radius: 8px; padding: 12px; }
.recuento b { display: block; font-size: 24px; font-weight: 600; }
.recuento span { font-size: 12px; }
.alt-fila { display: flex; justify-content: space-between; gap: 12px; padding: 11px 0; border-top: 1px solid __LINEA__; }
.alt-nombre { font-size: 14px; font-weight: 500; }
.nota { font-size: 12px; color: __GRIS_SUAVE__; }
.aviso { font-size: 13px; color: __ALERTA__; font-weight: 500; background: #FBEAEA; border-radius: 6px;
  padding: 8px 10px; margin: 0 0 12px; }
.seccion { font-size: 12px; font-weight: 600; color: __GRIS__; margin: 14px 0 4px; }

/* Controles con el color de la marca (aunque no se cargue .streamlit/config.toml) */
button[kind="primary"], button[kind="primaryFormSubmit"] { background-color: __ACENTO__ !important;
  border-color: __ACENTO__ !important; color: #FFFFFF !important; }
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover { background-color: #0A3238 !important; }
[data-testid="stButtonGroup"] button[kind*="Active"] { color: __ACENTO__ !important; border-color: __ACENTO__ !important;
  background-color: #E8F2F0 !important; }
[data-testid="stButtonGroup"] button[kind*="Active"] p { color: __ACENTO__ !important; }
[data-baseweb="tag"], [data-tag] { background-color: __ACENTO__ !important; color: #FFFFFF !important; }
input[type="checkbox"] { accent-color: __ACENTO__; }
input, textarea, [data-baseweb="select"] > div { background-color: #F8F9FB !important; }
input:focus, textarea:focus, [data-baseweb="select"] > div:focus-within { border-color: __ACENTO__ !important; }
</style>
"""
for nombre, valor in {"__FONDO__": FONDO, "__TARJETA__": TARJETA, "__BORDE__": BORDE, "__LINEA__": LINEA,
                      "__TINTA__": TINTA, "__GRIS__": GRIS, "__GRIS_SUAVE__": GRIS_SUAVE,
                      "__ACENTO__": ACENTO, "__ALERTA__": ALERTA}.items():
    CSS = CSS.replace(nombre, valor)
st.html(CSS)


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
    significados = dict(SIGNIFICADO_TIPO)
    sig = leer_csv("tipos_significado.csv")
    if sig is not None:
        significados.update(sig.set_index("tipo_problema")["significado"].to_dict())
    df["tipo_texto"] = df["tipo_problema"].map(significados).fillna("Tipo " + df["tipo_problema"].astype(str))
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


# ----------------------------------------------------------------------------- Configuración de alarmas
def leer_config():
    defecto = {"reglas": ["Nuevo", "Fin retrasado"], "grupos_atc": [],
               "laboratorios": [], "medicamentos": {}, "canal": "Email", "destinatarios": ""}
    try:
        cfg = {**defecto, **json.loads(CONFIG_ALARMAS.read_text(encoding="utf-8"))}
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = defecto
    if isinstance(cfg["medicamentos"], list):  # formato antiguo: lista de CN
        cfg["medicamentos"] = {cn: "" for cn in cfg["medicamentos"]}
    # Listas de vigilancia con nombre. Las versiones anteriores tenían una sola lista,
    # "medicamentos": se convierte en la lista "Mis medicamentos".
    if not cfg.get("listas"):
        cfg["listas"] = {LISTA_POR_DEFECTO: dict(cfg["medicamentos"])}
    return cfg


def guardar_config(cfg):
    # "medicamentos" se mantiene como la unión de todas las listas (lo leerá el motor de alarmas)
    cfg["medicamentos"] = {cn: n for meds in cfg["listas"].values() for cn, n in meds.items()}
    CONFIG_ALARMAS.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def vigilados():
    """Todos los medicamentos vigilados, de cualquier lista: {cn: nombre}."""
    return {cn: n for meds in leer_config()["listas"].values() for cn, n in meds.items()}


def listas_con(cn):
    return [nombre for nombre, meds in leer_config()["listas"].items() if cn in meds]


def anadir_a_lista(lista, cn, nombre):
    cfg = leer_config()
    cfg["listas"].setdefault(lista, {})[cn] = nombre
    guardar_config(cfg)


def quitar_de_lista(lista, cn):
    cfg = leer_config()
    cfg["listas"].get(lista, {}).pop(cn, None)
    guardar_config(cfg)


def vigilar(cn, nombre, activar=True):
    """Compatibilidad con el panel de alternativas: usa la primera lista."""
    lista = next(iter(leer_config()["listas"]))
    anadir_a_lista(lista, cn, nombre) if activar else [quitar_de_lista(l, cn) for l in listas_con(cn)]


def crear_lista():
    nombre = st.session_state.get("nueva_lista", "").strip()
    if not nombre:
        return
    cfg = leer_config()
    cfg["listas"].setdefault(nombre, {})
    guardar_config(cfg)
    st.session_state["lista_activa"] = nombre
    st.session_state["nueva_lista"] = ""


def borrar_lista(lista):
    cfg = leer_config()
    cfg["listas"].pop(lista, None)
    if not cfg["listas"]:
        cfg["listas"] = {LISTA_POR_DEFECTO: {}}
    guardar_config(cfg)
    st.session_state["lista_activa"] = next(iter(cfg["listas"]))


def anadir_desde_buscador(lista, clave):
    """Callback del desplegable de «Añadir medicamento»: acepta «CN · nombre» o un código escrito a mano."""
    valor = str(st.session_state.get(clave) or "").strip()
    st.session_state[clave] = None
    if not valor:
        return
    cn = valor.split(" · ")[0].strip()
    if not cn.isdigit():  # texto escrito que no es un medicamento de la lista ni un código
        st.session_state["aviso_listas"] = (f"«{valor}» no es un medicamento en desabastecimiento ni un código "
                                            "nacional. Elige uno de la lista o escribe solo el número.")
        return
    anadir_a_lista(lista, cn, dict(zip(df["cn"], df["nombre"])).get(cn, ""))


def boton_listas():
    """Botón «Mis listas» que despliega la gestión de listas de vigilancia."""
    cfg = leer_config()
    listas = cfg["listas"]
    total = len({cn for meds in listas.values() for cn in meds})
    NUEVA = "+ Nueva lista"
    with st.popover(f"Mis listas · {total}", width="content"):
        st.html('<div class="titulo-tarjeta" style="margin-bottom:2px">Listas de vigilancia</div>'
                '<p class="nota" style="margin:0 0 6px">Recibirás alarmas de estos medicamentos, aunque ahora '
                'no estén en desabastecimiento.</p>')
        if st.session_state.get("lista_activa") not in list(listas) + [NUEVA]:
            st.session_state["lista_activa"] = next(iter(listas))
        activa = st.selectbox("Lista", list(listas) + [NUEVA], key="lista_activa")
        if activa == NUEVA:
            c = st.columns([3, 1], vertical_alignment="bottom")
            c[0].text_input("Nombre de la lista", key="nueva_lista", placeholder="Productos propios")
            c[1].button("Crear", on_click=crear_lista, type="primary", width="stretch")
            return

        meds = listas[activa]
        nombres = dict(zip(df["cn"], df["nombre"]))
        caja = st.container(height=300) if len(meds) > 6 else st.container()
        with caja:
            if not meds:
                st.html('<p class="nota">Esta lista está vacía.</p>')
            for cn, nombre in meds.items():
                f = st.columns([8, 1], vertical_alignment="center")
                nombre = nombres.get(cn) or nombre or "Ahora no está en desabastecimiento"
                en_desab = cn in nombres
                f[0].html(f'<div style="font-size:13px;line-height:1.35">{esc(nombre)}'
                          f'<div class="sub">CN {esc(cn)}'
                          f'{" · <span style=color:" + ALERTA + ">en desabastecimiento</span>" if en_desab else ""}'
                          f'</div></div>')
                f[1].button("✕", key=f"quitar-{activa}-{cn}", type="tertiary", on_click=quitar_de_lista,
                            args=(activa, cn), help="Quitar de la lista")

        if st.session_state.get("aviso_listas"):
            st.html(f'<div class="aviso">{esc(st.session_state.pop("aviso_listas"))}</div>')
        clave = f"anadir-{activa}"
        st.selectbox("Añadir medicamento", [f"{c} · {n}" for c, n in zip(df["cn"], df["nombre"])],
                     index=None, key=clave, accept_new_options=True,
                     placeholder="Busca por nombre o escribe un código nacional",
                     on_change=anadir_desde_buscador, args=(activa, clave))
        if len(listas) > 1:
            st.button(f"Borrar la lista «{activa}»", type="tertiary", on_click=borrar_lista, args=(activa,))


def titulo(texto, derecha_html=""):
    """Título de la página con el botón «Mis listas» a la derecha."""
    t = st.columns([3, 1.4], vertical_alignment="bottom")
    t[0].title(texto)
    with t[1], st.container(key="titulo-derecha"):
        if derecha_html:
            st.html(derecha_html)
        boton_listas()


# ----------------------------------------------------------------------------- Piezas comunes
def esc(v):
    return html.escape(str(v))


def pildora(texto, colores):
    fondo, color = colores
    return f'<span class="pildora" style="background:{fondo};color:{color}">{esc(texto)}</span>'


def pildora_situacion(texto):
    t = texto.lower()
    if "sin alternativa" in t:
        return pildora(texto, ROJO_P)
    if "hay alternativa" in t:
        return pildora(texto, VERDE_P)
    if "controlad" in t or "distribuc" in t:
        return pildora(texto, NARANJA_P)
    return pildora(texto, GRIS_P)


# Logo: cápsula bicolor (versión para fondo oscuro, sin sombra)
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" fill="none">
<defs>
<linearGradient id="logo-t" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6FD0C5"/>
<stop offset=".45" stop-color="#2A8C86"/><stop offset="1" stop-color="#0E3F47"/></linearGradient>
<linearGradient id="logo-w" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/>
<stop offset=".55" stop-color="#E9EDF1"/><stop offset="1" stop-color="#AEB8C3"/></linearGradient>
<linearGradient id="logo-h" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".85"/>
<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
</defs>
<g transform="rotate(-35 32 31)">
<path d="M32 21H19a10 10 0 0 0 0 20h13z" fill="url(#logo-t)"/>
<path d="M32 21h13a10 10 0 0 1 0 20H32z" fill="url(#logo-w)"/>
<rect x="31.4" y="21" width="1.4" height="20" fill="#0E3F47" opacity=".25"/>
<path d="M14 25.5c1.2-1 3-1.6 5-1.6h26c2 0 3.8.6 5 1.6" stroke="url(#logo-h)" stroke-width="2.6" stroke-linecap="round"/>
</g></svg>"""
# st.html elimina los <svg> incrustados, así que el logo va como imagen (data URI)
LOGO_IMG = ('<img src="data:image/svg+xml;base64,' + base64.b64encode(LOGO_SVG.encode()).decode()
            + '" width="30" height="30" alt="">')


def cabecera(activa):
    enlaces = {"Resumen": "./", "Buscador": "./buscador", "Alarmas": "./alarmas"}
    menu = "".join(f'<a href="{url}" target="_self" class="{"activa" if nombre == activa else ""}">{nombre}</a>'
                   for nombre, url in enlaces.items())
    st.html(f"""<div class="cabecera"><div class="cabecera-in">
      <div class="marca-app">{LOGO_IMG}Vigilancia de suministro</div>
      <nav class="menu" aria-label="Secciones">{menu}</nav>
      <div class="fecha-datos">Datos AEMPS · {hoy:%d.%m.%Y}</div></div></div>""")


def barras_html(conteo, resaltar=(), color=BARRA, otros=None):
    """conteo: lista de (etiqueta, n). Las de `resaltar` van en el color de la marca."""
    maximo = max([n for _, n in conteo] + ([otros[1]] if otros else [1]))
    filas = ""
    for nombre, n in conteo + ([otros] if otros else []):
        es_otros = otros is not None and nombre == otros[0]
        c = ACENTO if nombre in resaltar else (BARRA_SUAVE if es_otros else color)
        texto = ACENTO if nombre in resaltar else TINTA
        filas += (f'<div class="barra-fila" title="{esc(nombre)}: {n}"><div class="nombre" style="color:{texto}">'
                  f'{esc(nombre)}</div><div class="barra-fondo"><div style="width:{n / maximo * 100:.1f}%;'
                  f'background:{c}"></div></div><div class="n">{n}</div></div>')
    return filas


def tabla_html(datos, columnas, pildoras=None, ajustar=("nombre",), sub=None, enlace=None):
    """sub: (columna, prefijo) que se escribe en pequeño debajo del nombre, p. ej. ("cn", "CN ").
    enlace: función fila -> url; si se da, el nombre se puede pinchar."""
    cab = "".join(f'<th class="{"" if c in ajustar else "nowrap"}">{t}</th>' for c, t in columnas.items())
    filas = ""
    for _, f in datos.iterrows():
        celdas = ""
        for c in columnas:
            v = f[c]
            if isinstance(v, pd.Timestamp):
                v = v.strftime("%d.%m.%Y")
            elif v is None or (not isinstance(v, str) and pd.isna(v)) or v == "":
                v = "—"
            contenido = pildora(v, pildoras[c][v]) if pildoras and c in pildoras and v in pildoras[c] else esc(v)
            if enlace and c == "nombre":
                contenido = f'<a class="med" href="{esc(enlace(f))}" target="_self">{contenido}</a>'
            if sub and c == "nombre" and pd.notna(f[sub[0]]):
                contenido += f'<div class="sub">{esc(sub[1])}{esc(f[sub[0]])}</div>'
            celdas += f'<td class="{"" if c in ajustar else "nowrap"}">{contenido}</td>'
        filas += f"<tr>{celdas}</tr>"
    st.html(f'<table class="tabla"><thead><tr>{cab}</tr></thead><tbody>{filas}</tbody></table>')


def paginar_url(datos, param, enlace):
    """Como paginar, pero la página va en la URL (?param=n). Devuelve (trozo, html de navegación)."""
    n_paginas = max(1, math.ceil(len(datos) / POR_PAGINA))
    try:
        pagina = min(max(int(st.query_params.get(param, 1)), 1), n_paginas)
    except ValueError:
        pagina = 1
    trozo = datos.iloc[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]
    nav = ""
    if n_paginas > 1:
        ant = f'<a href="{enlace(**{param: pagina - 1})}" target="_self">‹ Anterior</a>' if pagina > 1 else ""
        sig = (f'<a href="{enlace(**{param: pagina + 1})}" target="_self">Siguiente ›</a>'
               if pagina < n_paginas else "")
        nav = f'<div class="paginas">{ant}<span>Página {pagina} de {n_paginas}</span>{sig}</div>'
    return trozo, pagina, nav


def paginar(datos, clave):
    """Devuelve las filas de la página actual y dibuja ‹ Anterior · Página x de n · Siguiente ›."""
    n_paginas = max(1, math.ceil(len(datos) / POR_PAGINA))
    pagina = min(st.session_state.get(clave, 1), n_paginas)
    trozo = datos.iloc[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]

    def mover(paso):
        st.session_state[clave] = pagina + paso

    def controles():
        if n_paginas <= 1:
            return
        with st.container(key=f"paginador-{clave}"):
            c = st.columns([1, 1.5, 1.4, 1.5, 1], vertical_alignment="center")
            c[1].button("‹ Anterior", key=f"{clave}-ant", on_click=mover, args=(-1,),
                        disabled=pagina == 1, width="stretch")
            c[2].html(f'<div style="text-align:center;font-size:13px;color:{GRIS}">Página {pagina} de {n_paginas}</div>')
            c[3].button("Siguiente ›", key=f"{clave}-sig", on_click=mover, args=(1,),
                        disabled=pagina == n_paginas, width="stretch")
    return trozo, controles


# ============================================================================= Resumen
def pagina_resumen():
    cabecera("Resumen")
    abrir_ficha_si_toca()
    ev_hoy = eventos[eventos["fecha"] == hoy]
    ev_7 = eventos[eventos["fecha"] > hoy - timedelta(days=7)]
    n = lambda e, et: int((e["etiqueta"] == et).sum())
    nuevos, resueltos, retrasos = n(ev_hoy, "Nuevo"), n(ev_hoy, "Resuelto"), n(ev_hoy, "Fin retrasado")
    sin_alt = int((df["n_disponibles"] == 0).sum()) if tiene_alternativas else None
    oncologicos = int(df[df["cn"].isin(ev_hoy.loc[ev_hoy["etiqueta"] == "Fin retrasado", "cn"])]
                      ["grupo_atc"].eq("L").sum())

    avisos = nuevos + retrasos
    titulo("Resumen del día",
           f'<a href="./alarmas" target="_self" style="font-size:14px;font-weight:500;color:{ALERTA};'
           f'white-space:nowrap">{avisos} {"alarma" if avisos == 1 else "alarmas"} hoy →</a>' if avisos else "")

    delta = nuevos - resueltos
    hay_historico = not eventos.empty
    ctx_activos = (f"{'+' if delta > 0 else ''}{delta} respecto a ayer" if hay_historico
                   else "presentaciones")
    kpi = lambda label, num, ctx, color=None: (
        f'<div class="tarjeta-html{" kpi-alerta" if color else ""}"{f" style=--c:{color}" if color else ""}>'
        f'<div class="kpi-label">{label}</div><div class="kpi-num">{num}</div><div class="kpi-ctx">{ctx}</div></div>')
    st.html('<div class="kpis">'
            + kpi("Activos", f"{len(df):,}".replace(",", "."), ctx_activos)
            + kpi("Nuevos hoy", nuevos, f"{n(ev_7, 'Nuevo')} en los últimos 7 días")
            + kpi("Resueltos hoy", f'<span style="color:{ACENTO}">{resueltos}</span>',
                  f"{n(ev_7, 'Resuelto')} en los últimos 7 días")
            + kpi("Fin retrasado hoy", retrasos,
                  f"{oncologicos} oncológicos" if oncologicos else f"{n(ev_7, 'Fin retrasado')} en 7 días", NARANJA)
            + (kpi("Sin alternativa", sin_alt if sin_alt is not None else "—",
                   "ninguna presentación equivalente disponible", ALERTA) if MOSTRAR_ALTERNATIVAS else
               kpi("Sin fecha de fin", int(df["fecha_fin_prevista"].isna().sum()),
                   "la AEMPS no indica cuándo se resolverán", ALERTA))
            + "</div>")

    st.write("")
    vigilados = leer_config()["grupos_atc"]
    izq, der = st.columns(2)
    with izq, st.container(key="tarjeta-atc"):
        conteo = list(df["grupo_atc_texto"].value_counts().items())
        # 8 filas, igual que la de laboratorios, para que las dos tarjetas midan lo mismo
        principales, resto = (conteo[:7], conteo[7:]) if len(conteo) > 8 else (conteo, [])
        otros = (f"Otros {len(resto)} grupos", sum(v for _, v in resto)) if resto else None
        leyenda = '<span class="leyenda"><i style="background:#12505A"></i>grupo vigilado</span>' if vigilados else ""
        st.html(f'<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px">'
                f'<div class="titulo-tarjeta">Por grupo terapéutico</div>{leyenda}</div>'
                + barras_html(principales, resaltar=vigilados, otros=otros))
    with der, st.container(key="tarjeta-labs"):
        st.html('<div class="titulo-tarjeta">Laboratorios con más desabastecimientos</div>'
                + barras_html(list(df["laboratorio"].value_counts().head(8).items())))

    with st.container(key="tarjeta-cambios"):
        st.html('<div style="display:flex;justify-content:space-between;align-items:baseline">'
                '<div class="titulo-tarjeta">Cambios de hoy</div>'
                '<a href="./alarmas" target="_self" style="font-size:13px">Ver historial</a></div>')
        if ev_hoy.empty:
            st.html('<p class="nota">Sin cambios registrados hoy.</p>')
        else:
            enlace = lambda **extra: "?" + urlencode({"pc": st.query_params.get("pc", 1), **extra})
            trozo, pagina, nav = paginar_url(ev_hoy, "pc", enlace)
            tabla_html(trozo, {"etiqueta": "Tipo", "nombre": "Medicamento", "detalle": "Fin previsto"},
                       pildoras={"etiqueta": PILDORA_EVENTO}, sub=("cn", "CN "),
                       enlace=lambda f: enlace(pc=pagina, ficha=f["cn"]))
            if nav:
                st.html(nav)


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

    def fila_alt(a, colores, estado):
        return (f'<div class="alt-fila"><div><div class="alt-nombre">{esc(a["nombre_alternativa"])}</div>'
                f'<div class="nota">{esc(a["laboratorio_alternativa"] or "")}</div></div>'
                f'<div style="align-self:center">{pildora(estado, colores)}</div></div>')

    lista = "".join(fila_alt(a, VERDE_P if a["estado"] == "Disponible" else ROJO_P,
                             "Disponible" if a["estado"] == "Disponible" else "Sin suministro")
                    for _, a in equiv.sort_values("estado").iterrows())
    avisos = ""
    if fila["es_vacuna"]:
        avisos = '<div class="aviso">Vacuna: no se proponen alternativas automáticas. Consultar.</div>'
    elif no_sust:
        avisos = ('<div class="aviso">No sustituible según CIMA: cualquier cambio de presentación '
                  'requiere una nueva prescripción médica.</div>')
    if equiv.empty and not fila["es_vacuna"] and not no_sust:
        lista = '<p class="nota">No hay presentaciones equivalentes (mismo principio activo, dosis y forma).</p>'
    if not prescripcion.empty:
        lista += '<div class="seccion">Requieren nueva prescripción</div>' + "".join(
            fila_alt(a, GRIS_P if a["estado"] == "Disponible" else ROJO_P,
                     "Disponible" if a["estado"] == "Disponible" else "Sin suministro")
            for _, a in prescripcion.sort_values("estado").iterrows())

    st.html(f"""
      <div style="font-size:12px;font-weight:600;color:{ACENTO}">Alternativas</div>
      <div style="font-size:18px;font-weight:600;margin:6px 0 2px">{esc(fila['principio_activo'] or fila['nombre'])}</div>
      <div class="nota" style="margin-bottom:14px">{esc(fila['nombre'])}</div>
      {avisos}
      <div class="recuentos">
        <div class="recuento" style="background:{VERDE_P[0]};color:{ACENTO}"><b>{len(disp)}</b><span>disponibles</span></div>
        <div class="recuento" style="background:{ROJO_P[0]};color:{ALERTA}"><b>{len(equiv) - len(disp)}</b>
          <span>también en desabastecimiento</span></div>
      </div>
      {lista}
      <div class="seccion">Otras dosis o formas del mismo principio activo</div>
      <div class="nota" style="color:{TINTA}">{len(otras)} presentaciones comercializadas · consultar con el médico</div>
      <p class="nota" style="margin:14px 0 4px">La sustitución la decide el profesional sanitario.</p>""")
    if cn in vigilados():
        st.button("Dejar de vigilar", key=f"novig-{cn}", on_click=vigilar, args=(cn, fila["nombre"], False),
                  width="stretch")
        st.html('<p class="nota" style="text-align:center">Recibirás alarmas de este medicamento.</p>')
    else:
        st.button("Vigilar este medicamento", key=f"vig-{cn}", type="primary", on_click=vigilar,
                  args=(cn, fila["nombre"]), width="stretch",
                  help="Recibirás una alarma si cambia su situación, aunque no esté en tus laboratorios o grupos ATC")


def controles_lista(cn, nombre):
    """«Vigilar en una lista»: añadir a una lista o quitar de las que ya lo tienen."""
    listas = list(leer_config()["listas"])
    dentro = listas_con(cn)
    st.html('<div class="seccion" style="margin-top:0">Vigilar en una lista</div>')
    fuera = [l for l in listas if l not in dentro]
    if fuera:
        c = st.columns([3, 2], vertical_alignment="bottom")
        destino = c[0].selectbox("Lista", fuera, key=f"destino-{cn}", label_visibility="collapsed")
        c[1].button("Añadir", key=f"vig-{cn}", type="primary", width="stretch",
                    on_click=anadir_a_lista, args=(destino, cn, nombre))
    for l in dentro:
        c = st.columns([3, 2], vertical_alignment="center")
        c[0].html(f'<div style="font-size:13px">En «{esc(l)}»</div>')
        c[1].button("Quitar", key=f"novig-{l}-{cn}", type="tertiary", width="stretch",
                    on_click=quitar_de_lista, args=(l, cn))


@st.dialog("Medicamento", width="medium")
def ventana_ficha(cn):
    fila = df[df["cn"] == cn]
    if not fila.empty:
        ficha_medicamento(fila.iloc[0])
        return
    # Ya no está en la lista de la AEMPS (por ejemplo, un desabastecimiento resuelto)
    ultimo = eventos[eventos["cn"] == cn].sort_values("fecha").tail(1)
    nombre = ultimo["nombre"].iloc[0] if not ultimo.empty else ""
    st.html(f'<div style="font-size:16px;font-weight:600;line-height:1.35">{esc(nombre or "CN " + cn)}</div>'
            f'<div class="sub" style="margin-bottom:10px">CN {esc(cn)}</div>'
            f'<div style="margin-bottom:16px">{pildora("Ya no está en desabastecimiento", VERDE_P)}</div>')
    controles_lista(cn, nombre)


def abrir_ficha_si_toca():
    """Si la URL trae ?ficha=CN (se ha pinchado un medicamento), abre su ventana."""
    cn = st.query_params.get("ficha")
    if cn:
        del st.query_params["ficha"]  # para que no se vuelva a abrir en la siguiente interacción
        ventana_ficha(cn)


def ficha_medicamento(fila):
    def dato(etiqueta, valor):
        return (f'<div style="display:flex;justify-content:space-between;gap:16px;padding:9px 0;'
                f'border-top:1px solid {LINEA};font-size:13px"><span style="color:{GRIS}">{etiqueta}</span>'
                f'<span style="text-align:right">{valor}</span></div>')
    fecha = lambda d: d.strftime("%d.%m.%Y") if pd.notna(d) else "—"
    obs = fila.get("observaciones")
    st.html(f"""
      <div style="font-size:12px;font-weight:600;color:{ACENTO}">Ficha</div>
      <div style="font-size:16px;font-weight:600;margin:6px 0 4px;line-height:1.35">{esc(fila['nombre'])}</div>
      <div style="margin-bottom:12px">{pildora_situacion(fila['tipo_texto'])}</div>
      {dato("Principio activo", esc(fila['principio_activo'] or "—"))}
      {dato("Laboratorio", esc(fila['laboratorio'] if isinstance(fila['laboratorio'], str) else "—"))}
      {dato("Grupo ATC", esc(fila['grupo_atc_texto']))}
      {dato("Código nacional", esc(fila['cn']))}
      {dato("Inicio", fecha(fila['fecha_inicio']))}
      {dato("Fin previsto", fecha(fila['fecha_fin_prevista']))}
      {dato("Días activo", esc(fila['dias_activo']))}
      {f'<div class="seccion">Observaciones de la AEMPS</div><div style="font-size:13px">{esc(obs)}</div>'
       if isinstance(obs, str) and obs.strip() else ""}
      <div style="height:14px"></div>""")
    controles_lista(fila["cn"], fila["nombre"])


def pagina_buscador():
    cabecera("Buscador")
    titulo("Buscador")
    st.write("")

    # Los filtros viven en la URL (?texto=...&lab=...): así, al pinchar en un medicamento
    # (un enlace) la página se recarga con los mismos filtros y el medicamento elegido.
    qp = st.query_params
    lista = lambda k: [v for v in qp.get(k, "").split("|") if v]
    labs_todos = sorted(df["laboratorio"].dropna().unique())
    grupos_todos = sorted(df["grupo_atc_texto"].unique())
    tipos_todos = sorted(df["tipo_texto"].unique())
    iniciales = {"f_texto": qp.get("texto", ""),
                 "f_lab": [x for x in lista("lab") if x in labs_todos],
                 "f_atc": [x for x in lista("atc") if x in grupos_todos],
                 "f_tipo": [x for x in lista("tipo") if x in tipos_todos],
                 "f_sinalt": qp.get("sinalt") == "1", "f_vac": qp.get("vac") == "1",
                 "f_vig": qp.get("vig") == "1"}
    for clave, valor in iniciales.items():
        st.session_state.setdefault(clave, valor)

    with st.container(key="tarjeta-filtros"):
        c = st.columns([2, 1, 1, 1])
        texto = c[0].text_input("Medicamento o principio activo", key="f_texto", placeholder="lenalidomida")
        labs = c[1].multiselect("Laboratorio", labs_todos, key="f_lab", placeholder="Todos")
        grupos = c[2].multiselect("Grupo ATC", grupos_todos, key="f_atc", placeholder="Todos")
        tipos = c[3].multiselect("Situación", tipos_todos, key="f_tipo", placeholder="Todas")
        k = st.columns([1, 1, 1, 3])
        solo_sin_alt = (k[0].checkbox("Solo sin alternativa", key="f_sinalt", disabled=not tiene_alternativas)
                        if MOSTRAR_ALTERNATIVAS else False)
        solo_vacunas = k[1 if MOSTRAR_ALTERNATIVAS else 0].checkbox("Solo vacunas", key="f_vac")
        solo_vigilados = k[2 if MOSTRAR_ALTERNATIVAS else 1].checkbox("Solo vigilados", key="f_vig")

    vigilados_todos = vigilados()
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
    if solo_vigilados:
        f = f[f["cn"].isin(vigilados_todos)]
    f = f.sort_values("fecha_inicio", ascending=False).reset_index(drop=True)

    n_paginas = max(1, math.ceil(len(f) / POR_PAGINA))
    try:
        pagina = min(max(int(qp.get("pag", 1)), 1), n_paginas)
    except ValueError:
        pagina = 1
    seleccion = qp.get("cn")
    filtros = {"texto": texto, "lab": "|".join(labs), "atc": "|".join(grupos), "tipo": "|".join(tipos),
               "sinalt": "1" if solo_sin_alt else "", "vac": "1" if solo_vacunas else "",
               "vig": "1" if solo_vigilados else ""}
    filtros = {k: v for k, v in filtros.items() if v}
    antes = {k: qp.get(k) for k in ("texto", "lab", "atc", "tipo", "sinalt", "vac", "vig") if qp.get(k)}
    if antes != filtros:  # si cambian los filtros se vuelve a la página 1
        pagina = 1
    trozo = f.iloc[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]
    st.query_params.from_dict({**filtros, **({"pag": str(pagina)} if pagina > 1 else {}),
                               **({"cn": seleccion} if seleccion else {})})
    enlace = lambda **extra: "?" + urlencode({**filtros, "pag": pagina, **extra})

    st.write("")
    izq, der = st.columns([2, 1], gap="medium")
    with izq, st.container(key="tarjeta-resultados"):
        cab = st.columns([3, 1], vertical_alignment="center")
        cab[0].html(f'<div style="font-size:14px;font-weight:600">{len(f):,} presentaciones</div>'
                    .replace(",", "."))
        tabla = f[["cn", "nombre", "laboratorio", "tipo_texto", "fecha_fin_prevista"]
                  + (["n_disponibles"] if MOSTRAR_ALTERNATIVAS else [])]
        cab[1].download_button("Descargar CSV", tabla.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"desabastecimientos_{hoy:%Y-%m-%d}.csv", mime="text/csv",
                               width="stretch")
        filas = ""
        for _, fila in trozo.iterrows():
            cn = fila["cn"]
            fin_prev = fila["fecha_fin_prevista"]
            n_alt = fila["n_disponibles"]
            lab = fila["laboratorio"] if isinstance(fila["laboratorio"], str) else "—"
            atc = fila["atc_codigo"] if isinstance(fila["atc_codigo"], str) else "sin ATC"
            alt_txt = f"{int(n_alt)}" if pd.notna(n_alt) else "—"
            alt_color = ALERTA if alt_txt == "0" else TINTA
            celda_alt = (f'<td class="num" style="font-weight:600;color:{alt_color}">{alt_txt}</td>'
                         if MOSTRAR_ALTERNATIVAS else "")
            filas += (
                f'<tr class="{"sel" if cn == seleccion else ""}">'
                f'<td><a class="med" href="{enlace(cn=cn)}" target="_self">{esc(fila["nombre"])}</a>'
                f'<div class="sub">CN {cn} · {esc(atc)}{" · vigilado" if cn in vigilados_todos else ""}</div></td>'
                f'<td>{esc(lab)}</td>'
                f'<td>{pildora_situacion(fila["tipo_texto"])}</td>'
                f'<td class="nowrap">{fin_prev.strftime("%d.%m.%Y") if pd.notna(fin_prev) else "—"}</td>'
                f'{celda_alt}</tr>')
        navegacion = ""
        if n_paginas > 1:
            ant = f'<a href="{enlace(pag=pagina - 1)}" target="_self">‹ Anterior</a>' if pagina > 1 else ""
            sig = f'<a href="{enlace(pag=pagina + 1)}" target="_self">Siguiente ›</a>' if pagina < n_paginas else ""
            navegacion = f'<div class="paginas">{ant}<span>Página {pagina} de {n_paginas}</span>{sig}</div>'
        st.html(f"""<table class="tabla buscador"><thead><tr><th>Medicamento</th><th>Laboratorio</th>
            <th>Situación</th><th class="nowrap">Fin previsto</th>{'<th class="num">Altern.</th>' if MOSTRAR_ALTERNATIVAS else ""}</tr></thead>
            <tbody>{filas}</tbody></table>{navegacion}""")
    with der, st.container(key="tarjeta-panel"):
        elegida = df[df["cn"] == seleccion]
        if not MOSTRAR_ALTERNATIVAS:
            if not elegida.empty:
                ficha_medicamento(elegida.iloc[0])
            else:
                st.html(f'<div style="font-size:12px;font-weight:600;color:{ACENTO}">Ficha</div>'
                        '<p class="nota" style="margin-top:8px">Pincha en el nombre de un medicamento de la lista '
                        'para ver sus datos y vigilarlo.</p>')
        elif not elegida.empty:
            panel_alternativas(elegida.iloc[0])
        elif alternativas is None:
            st.html('<p class="nota">Ejecuta alternativas.py para ver alternativas por principio activo.</p>')
        else:
            st.html(f'<div style="font-size:12px;font-weight:600;color:{ACENTO}">Alternativas</div>'
                    '<p class="nota" style="margin-top:8px">Pincha en el nombre de un medicamento de la lista '
                    'para ver qué presentaciones equivalentes hay disponibles.</p>')


# ============================================================================= Alarmas
def pagina_alarmas():
    cabecera("Alarmas")
    abrir_ficha_si_toca()
    titulo("Alarmas")
    st.write("")
    izq, der = st.columns([2, 1], gap="medium")

    with izq, st.container(key="tarjeta-historial"):
        st.html('<div class="titulo-tarjeta">Historial de cambios</div>')
        # Día, tipo y página van en la URL: al pinchar un medicamento (un enlace) se recarga
        # la página y así se conserva lo que estabas mirando.
        qp = st.query_params
        TODOS_D, TODOS_T = "Todos los días", "Todos los tipos"
        dias = (sorted(eventos["fecha"].dropna().dt.strftime("%Y-%m-%d").unique(), reverse=True)
                if not eventos.empty else [])
        tipos = sorted(eventos["etiqueta"].unique())
        st.session_state.setdefault("a_dia", qp.get("dia") if qp.get("dia") in dias else TODOS_D)
        st.session_state.setdefault("a_tipo", qp.get("tipo") if qp.get("tipo") in tipos else TODOS_T)
        c = st.columns(2)
        dia = c[0].selectbox("Día", [TODOS_D] + dias, key="a_dia",
                             format_func=lambda d: d if d == TODOS_D else pd.Timestamp(d).strftime("%d.%m.%Y"))
        ev_dia = eventos if dia == TODOS_D else eventos[eventos["fecha"] == pd.Timestamp(dia)]
        conteo = ev_dia["etiqueta"].value_counts()
        tipo = c[1].selectbox("Tipo", [TODOS_T] + tipos, key="a_tipo",
                              format_func=lambda t: t if t == TODOS_T else f"{t} ({conteo.get(t, 0)})")
        ev = ev_dia if tipo == TODOS_T else ev_dia[ev_dia["etiqueta"] == tipo]
        filtros = {k: v for k, v in {"dia": "" if dia == TODOS_D else dia,
                                     "tipo": "" if tipo == TODOS_T else tipo}.items() if v}
        if {k: qp.get(k) for k in ("dia", "tipo") if qp.get(k)} != filtros:
            st.query_params.from_dict(filtros)  # filtro nuevo: vuelve a la página 1
        else:
            st.query_params.from_dict({**filtros, **({"pag": qp.get("pag")} if qp.get("pag") else {})})
        st.html(f'<p class="nota" style="margin:0 0 4px">{len(ev)} cambios</p>')
        if ev.empty:
            st.html('<p class="nota">Todavía no hay cambios registrados: hacen falta al menos '
                    'dos días de descargas.</p>')
        else:
            ev = ev.sort_values("fecha", ascending=False)
            enlace = lambda **extra: "?" + urlencode({**filtros, **extra})
            trozo, pagina, nav = paginar_url(ev, "pag", enlace)
            tabla_html(trozo, {"fecha": "Fecha", "etiqueta": "Tipo",
                               "nombre": "Medicamento", "detalle": "Fin previsto"},
                       pildoras={"etiqueta": PILDORA_EVENTO}, sub=("cn", "CN "),
                       enlace=lambda f: enlace(pag=pagina, ficha=f["cn"]))
            if nav:
                st.html(nav)
            st.html('<p class="nota" style="margin-top:8px">Pincha en un medicamento para ver su ficha '
                    'y añadirlo a una lista.</p>')

    with der:
        cfg = leer_config()
        with st.container(key="tarjeta-config"), st.form("config", border=False):
            st.html('<div class="titulo-tarjeta">Qué vigilar</div>')
            opciones = ["Nuevo", "Fin retrasado", "Sin fecha de fin", "Resuelto"] + (
                ["Sin alternativa"] if MOSTRAR_ALTERNATIVAS else [])
            reglas = st.multiselect("Avisar cuando", opciones,
                                    default=[r for r in cfg["reglas"] if r in opciones], placeholder="Ninguna")
            grupos = st.multiselect("Grupos ATC", sorted(df["grupo_atc_texto"].unique()),
                                    default=[g for g in cfg["grupos_atc"] if g in set(df["grupo_atc_texto"])],
                                    placeholder="Todos")
            labs_todos = sorted(df["laboratorio"].dropna().unique())
            labs = st.multiselect("Laboratorios", labs_todos,
                                  default=[l for l in cfg["laboratorios"] if l in labs_todos],
                                  placeholder="Ninguno")
            canal = st.selectbox("Enviar por", ["Email", "Telegram", "Teams"],
                                 index=["Email", "Telegram", "Teams"].index(cfg["canal"]))
            dest = st.text_input("Destinatarios", cfg["destinatarios"], placeholder="equipo@empresa.com")
            if st.form_submit_button("Guardar", type="primary", width="stretch"):
                guardar_config({**leer_config(), "reglas": reglas, "grupos_atc": grupos,
                                "laboratorios": labs, "canal": canal, "destinatarios": dest})
                st.success("Configuración guardada.")

        st.write("")
        with st.container(key="tarjeta-vigilados"):
            listas = leer_config()["listas"]
            filas = "".join(f'<div style="display:flex;justify-content:space-between;padding:8px 0;'
                            f'border-top:1px solid {LINEA};font-size:14px"><span>{esc(n)}</span>'
                            f'<span style="color:{GRIS}">{len(m)} medicamento{"s" if len(m) != 1 else ""}</span></div>'
                            for n, m in listas.items())
            st.html('<div class="titulo-tarjeta">Listas de vigilancia</div>'
                    '<p class="nota" style="margin:-6px 0 8px">Recibes alarmas de los medicamentos de tus listas, '
                    'aunque no sean de los laboratorios o grupos de arriba. Gestiónalas con el botón '
                    '«Mis listas» de arriba a la derecha.</p>' + filas)
        st.html('<p class="nota" style="margin-top:10px">El envío automático se activará con el motor de alarmas.</p>')


# ============================================================================= Navegación
# El menú es la cabecera oscura de cada página; la navegación de Streamlit queda oculta
pag_resumen = st.Page(pagina_resumen, title="Resumen", url_path="resumen", default=True)
pag_buscador = st.Page(pagina_buscador, title="Buscador", url_path="buscador")
pag_alarmas = st.Page(pagina_alarmas, title="Alarmas", url_path="alarmas")
st.navigation([pag_resumen, pag_buscador, pag_alarmas], position="hidden").run()
