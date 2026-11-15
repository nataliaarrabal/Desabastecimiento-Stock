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

st.set_page_config(page_title="Vigilancia de suministro", layout="wide")

CSS = """
<link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
html, body, [class*="st-"], .stMarkdown, button, input, textarea, select {
  font-family: 'Public Sans', system-ui, sans-serif !important; }
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
.marca-app span { width: 10px; height: 10px; background: #4FB3A9; }
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
.buscador a.med { color: __TINTA__ !important; font-weight: 500; text-decoration: none !important; }
.buscador a.med:hover { color: __ACENTO__ !important; text-decoration: underline !important; }
.buscador tr.sel a.med { color: __ACENTO__ !important; }
.sub { font-size: 12px; color: __GRIS_SUAVE__; margin-top: 2px; }
.paginas { display: flex; justify-content: center; gap: 10px; align-items: center; padding: 14px 0 4px;
  font-size: 13px; color: __GRIS__; }
.paginas a { display: inline-flex; align-items: center; min-height: 34px; padding: 0 14px;
  border: 1px solid #C9D0D8; border-radius: 6px; color: __TINTA__ !important; text-decoration: none !important;
  font-weight: 500; background: #FFFFFF; }
.paginas a:hover { border-color: __ACENTO__; color: __ACENTO__ !important; background: #E8F2F0; }

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


def cabecera(activa):
    enlaces = {"Resumen": "./", "Buscador": "./buscador", "Alarmas": "./alarmas"}
    menu = "".join(f'<a href="{url}" target="_self" class="{"activa" if nombre == activa else ""}">{nombre}</a>'
                   for nombre, url in enlaces.items())
    st.html(f"""<div class="cabecera"><div class="cabecera-in">
      <div class="marca-app"><span></span>Vigilancia de suministro</div>
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


def tabla_html(datos, columnas, pildoras=None, ajustar=("nombre",)):
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
            celdas += f'<td class="{"" if c in ajustar else "nowrap"}">{contenido}</td>'
        filas += f"<tr>{celdas}</tr>"
    st.html(f'<table class="tabla"><thead><tr>{cab}</tr></thead><tbody>{filas}</tbody></table>')


# ============================================================================= Resumen
def pagina_resumen():
    cabecera("Resumen")
    ev_hoy = eventos[eventos["fecha"] == hoy]
    ev_7 = eventos[eventos["fecha"] > hoy - timedelta(days=7)]
    n = lambda e, et: int((e["etiqueta"] == et).sum())
    nuevos, resueltos, retrasos = n(ev_hoy, "Nuevo"), n(ev_hoy, "Resuelto"), n(ev_hoy, "Fin retrasado")
    sin_alt = int((df["n_disponibles"] == 0).sum()) if tiene_alternativas else None
    oncologicos = int(df[df["cn"].isin(ev_hoy.loc[ev_hoy["etiqueta"] == "Fin retrasado", "cn"])]
                      ["grupo_atc"].eq("L").sum())

    t = st.columns([3, 1], vertical_alignment="bottom")
    t[0].title("Resumen del día")
    avisos = nuevos + retrasos
    if avisos:
        t[1].html(f'<div style="text-align:right"><a href="./alarmas" target="_self" style="font-size:14px;'
                  f'font-weight:500;color:{ALERTA}">{avisos} {"alarma" if avisos == 1 else "alarmas"} hoy →</a></div>')

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
            + kpi("Sin alternativa", sin_alt if sin_alt is not None else "—",
                  "ninguna presentación equivalente disponible", ALERTA)
            + "</div>")

    st.write("")
    vigilados = leer_config()["grupos_atc"]
    izq, der = st.columns(2)
    with izq, st.container(key="tarjeta-atc"):
        conteo = list(df["grupo_atc_texto"].value_counts().items())
        principales, resto = conteo[:8], conteo[8:]
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
            tabla_html(ev_hoy, {"etiqueta": "Tipo", "nombre": "Medicamento", "detalle": "Fin previsto"},
                       pildoras={"etiqueta": PILDORA_EVENTO})


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
    if cn in leer_config()["medicamentos"]:
        st.button("Dejar de vigilar", key=f"novig-{cn}", on_click=vigilar, args=(cn, fila["nombre"], False),
                  width="stretch")
        st.html('<p class="nota" style="text-align:center">Recibirás alarmas de este medicamento.</p>')
    else:
        st.button("Vigilar este medicamento", key=f"vig-{cn}", type="primary", on_click=vigilar,
                  args=(cn, fila["nombre"]), width="stretch",
                  help="Recibirás una alarma si cambia su situación, aunque no esté en tus laboratorios o grupos ATC")


def pagina_buscador():
    cabecera("Buscador")
    st.title("Buscador")
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
        solo_sin_alt = k[0].checkbox("Solo sin alternativa", key="f_sinalt", disabled=not tiene_alternativas)
        solo_vacunas = k[1].checkbox("Solo vacunas", key="f_vac")
        solo_vigilados = k[2].checkbox("Solo vigilados", key="f_vig")

    vigilados = leer_config()["medicamentos"]
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
        f = f[f["cn"].isin(vigilados)]
    f = f.sort_values("fecha_inicio", ascending=False).reset_index(drop=True)

    POR_PAGINA = 25
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
        tabla = f[["cn", "nombre", "laboratorio", "tipo_texto", "fecha_fin_prevista", "n_disponibles"]]
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
            filas += (
                f'<tr class="{"sel" if cn == seleccion else ""}">'
                f'<td><a class="med" href="{enlace(cn=cn)}" target="_self">{esc(fila["nombre"])}</a>'
                f'<div class="sub">CN {cn} · {esc(atc)}{" · vigilado" if cn in vigilados else ""}</div></td>'
                f'<td>{esc(lab)}</td>'
                f'<td>{pildora_situacion(fila["tipo_texto"])}</td>'
                f'<td class="nowrap">{fin_prev.strftime("%d.%m.%Y") if pd.notna(fin_prev) else "—"}</td>'
                f'<td class="num" style="font-weight:600;color:{alt_color}">{alt_txt}</td></tr>')
        navegacion = ""
        if n_paginas > 1:
            ant = f'<a href="{enlace(pag=pagina - 1)}" target="_self">‹ Anterior</a>' if pagina > 1 else ""
            sig = f'<a href="{enlace(pag=pagina + 1)}" target="_self">Siguiente ›</a>' if pagina < n_paginas else ""
            navegacion = f'<div class="paginas">{ant}<span>Página {pagina} de {n_paginas}</span>{sig}</div>'
        st.html(f"""<table class="tabla buscador"><thead><tr><th>Medicamento</th><th>Laboratorio</th>
            <th>Situación</th><th class="nowrap">Fin previsto</th><th class="num">Altern.</th></tr></thead>
            <tbody>{filas}</tbody></table>{navegacion}""")
    with der, st.container(key="tarjeta-panel"):
        elegida = df[df["cn"] == seleccion]
        if not elegida.empty:
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
    st.title("Alarmas")
    st.write("")
    izq, der = st.columns([5, 3], gap="medium")

    with izq, st.container(key="tarjeta-historial"):
        st.html('<div class="titulo-tarjeta">Historial de cambios</div>')
        etiquetas = ["Todas"] + sorted(eventos["etiqueta"].unique())
        conteo = eventos["etiqueta"].value_counts()
        filtro = st.segmented_control(
            "Tipo", etiquetas, default="Todas", label_visibility="collapsed",
            format_func=lambda e: f"{e} {len(eventos) if e == 'Todas' else conteo.get(e, 0)}")
        ev = eventos if filtro in (None, "Todas") else eventos[eventos["etiqueta"] == filtro]
        if ev.empty:
            st.html('<p class="nota">Todavía no hay cambios registrados: hacen falta al menos '
                    'dos días de descargas.</p>')
        else:
            ev = ev.sort_values("fecha", ascending=False)
            tabla_html(ev.head(200), {"fecha": "Fecha", "etiqueta": "Tipo", "cn": "CN",
                                      "nombre": "Medicamento", "detalle": "Fin previsto"},
                       pildoras={"etiqueta": PILDORA_EVENTO})
            if len(ev) > 200:
                st.html(f'<p class="nota">Mostrando los 200 cambios más recientes de {len(ev)}.</p>')

    with der:
        cfg = leer_config()
        with st.container(key="tarjeta-config"), st.form("config", border=False):
            st.html('<div class="titulo-tarjeta">Qué vigilar</div>')
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
            dest = st.text_input("Destinatarios", cfg["destinatarios"], placeholder="equipo@empresa.com")
            if st.form_submit_button("Guardar", type="primary", width="stretch"):
                guardar_config({**leer_config(), "reglas": reglas, "grupos_atc": grupos,
                                "laboratorios": labs, "canal": canal, "destinatarios": dest})
                st.success("Configuración guardada.")

        st.write("")
        with st.container(key="tarjeta-vigilados"):
            st.html('<div class="titulo-tarjeta">Medicamentos vigilados</div>'
                    '<p class="nota" style="margin:-6px 0 8px">Recibes alarmas de estos medicamentos aunque no sean '
                    'de los laboratorios o grupos de arriba. Se añaden desde el Buscador o con su código nacional, '
                    'aunque ahora no estén en desabastecimiento.</p>')
            nombres = dict(zip(df["cn"], df["nombre"]))
            medicamentos = leer_config()["medicamentos"]
            if not medicamentos:
                st.html('<p class="nota">Todavía no vigilas ningún medicamento.</p>')
            for cn, nombre in medicamentos.items():
                m = st.columns([5, 1], vertical_alignment="center")
                nombre = nombres.get(cn) or nombre or "No está en desabastecimiento ahora"
                m[0].html(f'<div style="font-size:14px"><b>{esc(cn)}</b> · {esc(nombre)}</div>')
                m[1].button("Quitar", key=f"quitar-{cn}", type="tertiary", on_click=vigilar, args=(cn, "", False))
            with st.form("anadir", clear_on_submit=True, border=False):
                a = st.columns([3, 1], vertical_alignment="bottom")
                nuevo = a[0].text_input("Añadir por código nacional", placeholder="729828")
                if a[1].form_submit_button("Añadir", width="stretch") and nuevo.strip():
                    vigilar(nuevo.strip(), nombres.get(nuevo.strip(), ""))
                    st.rerun()
        st.html('<p class="nota" style="margin-top:10px">El envío automático se activará con el motor de alarmas.</p>')


# ============================================================================= Navegación
# El menú es la cabecera oscura de cada página; la navegación de Streamlit queda oculta
pag_resumen = st.Page(pagina_resumen, title="Resumen", url_path="resumen", default=True)
pag_buscador = st.Page(pagina_buscador, title="Buscador", url_path="buscador")
pag_alarmas = st.Page(pagina_alarmas, title="Alarmas", url_path="alarmas")
st.navigation([pag_resumen, pag_buscador, pag_alarmas], position="hidden").run()
