"""
Dashboard mínimo de desabastecimientos (AEMPS).

Uso:
    python -m pip install streamlit altair
    streamlit run app.py

Lee el CSV más reciente de datos_limpios/ (lo genera enriquecer_aemps.py).
Opcional: datos_limpios/tipos_significado.csv con columnas tipo_problema,significado
para mostrar el significado de cada código en vez del número.
"""

from datetime import timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

BASE = Path(__file__).parent
LIMPIOS = BASE / "datos_limpios"
COLOR = "#3B6FD4"  # un solo color: todas las gráficas tienen una sola serie

st.set_page_config(page_title="Desabastecimientos AEMPS", layout="wide")


# ----------------------------------------------------------------------------- Datos
@st.cache_data
def cargar():
    archivos = sorted(LIMPIOS.glob("aemps_enriquecido_*.csv"))
    if not archivos:
        return None, None
    df = pd.read_csv(archivos[-1], dtype={"cn": str, "nregistro": str},
                     parse_dates=["fecha_inicio", "fecha_fin_prevista"])
    df["es_vacuna"] = df["es_vacuna"].astype(bool)

    significado = LIMPIOS / "tipos_significado.csv"
    if significado.exists():
        mapa = pd.read_csv(significado).set_index("tipo_problema")["significado"]
        df["tipo_texto"] = df["tipo_problema"].map(mapa).fillna(df["tipo_problema"].astype(str))
    else:
        df["tipo_texto"] = "Tipo " + df["tipo_problema"].astype(str)
    df["grupo_atc_texto"] = df["grupo_atc"].fillna("?") + " · " + df["grupo_atc_nombre"].fillna("Sin ATC")
    return df, archivos[-1].stem.replace("aemps_enriquecido_", "")


df, fecha = cargar()
if df is None:
    st.error("No hay datos en datos_limpios/. Ejecuta primero enriquecer_aemps.py.")
    st.stop()

hoy = pd.Timestamp(fecha)

st.title("Desabastecimientos de medicamentos")
st.caption(f"Fuente: AEMPS (CIMA) · datos del {hoy:%d/%m/%Y} · solo problemas de suministro activos")

# ----------------------------------------------------------------------------- Filtros
with st.sidebar:
    st.header("Filtros")
    texto = st.text_input("Buscar medicamento o principio activo")
    labs = st.multiselect("Laboratorio", sorted(df["laboratorio"].dropna().unique()))
    grupos = st.multiselect("Grupo ATC", sorted(df["grupo_atc_texto"].unique()))
    tipos = st.multiselect("Tipo de problema", sorted(df["tipo_texto"].unique()))
    solo_vacunas = st.checkbox("Solo vacunas")

f = df
if texto:
    patron = texto.lower()
    f = f[f["nombre"].str.lower().str.contains(patron, regex=False)
          | f["principio_activo"].fillna("").str.lower().str.contains(patron, regex=False)]
if labs:
    f = f[f["laboratorio"].isin(labs)]
if grupos:
    f = f[f["grupo_atc_texto"].isin(grupos)]
if tipos:
    f = f[f["tipo_texto"].isin(tipos)]
if solo_vacunas:
    f = f[f["es_vacuna"]]

# ----------------------------------------------------------------------------- Indicadores
nuevos = f[f["fecha_inicio"] >= hoy - timedelta(days=30)]
fin_proximo = f[f["fecha_fin_prevista"].between(hoy, hoy + timedelta(days=30))]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Presentaciones afectadas", f"{len(f):,}".replace(",", "."))
c2.metric("Iniciados en los últimos 30 días", len(nuevos))
c3.metric("Fin previsto en 30 días", len(fin_proximo))
c4.metric("Laboratorios afectados", f["laboratorio"].nunique())
st.caption("«Resueltos» aparecerá cuando haya varios días de histórico guardado.")

if f.empty:
    st.info("Ningún registro cumple los filtros.")
    st.stop()


# ----------------------------------------------------------------------------- Gráficas
def barras_horizontales(datos, campo, titulo, top=None):
    conteo = datos[campo].value_counts().rename_axis(campo).reset_index(name="n")
    if top:
        conteo = conteo.head(top)
    return (alt.Chart(conteo, title=titulo)
            .mark_bar(color=COLOR, cornerRadiusEnd=4)
            .encode(x=alt.X("n:Q", title="Presentaciones"),
                    y=alt.Y(f"{campo}:N", sort="-x", title=None),
                    tooltip=[alt.Tooltip(f"{campo}:N", title="Categoría"),
                             alt.Tooltip("n:Q", title="Presentaciones")])
            .properties(height=max(200, 26 * len(conteo))))


col_a, col_b = st.columns(2)
col_a.altair_chart(barras_horizontales(f, "grupo_atc_texto", "Por grupo terapéutico (ATC)"),
                   width="stretch")
col_b.altair_chart(barras_horizontales(f, "laboratorio", "Top 10 laboratorios", top=10),
                   width="stretch")

# Inicio por mes (de los que siguen activos hoy), últimos 24 meses
por_mes = (f[f["fecha_inicio"] >= hoy - pd.DateOffset(months=24)]
           .set_index("fecha_inicio").resample("MS").size().reset_index(name="n"))
evolucion = (alt.Chart(por_mes, title="Mes de inicio de los desabastecimientos activos hoy (últimos 24 meses)")
             .mark_bar(color=COLOR, cornerRadiusEnd=4)
             .encode(x=alt.X("fecha_inicio:T", title=None, timeUnit="yearmonth"),
                     y=alt.Y("n:Q", title="Presentaciones"),
                     tooltip=[alt.Tooltip("fecha_inicio:T", title="Mes", format="%m/%Y"),
                              alt.Tooltip("n:Q", title="Presentaciones")])
             .properties(height=260))

# Antigüedad agrupada en tramos
tramos = pd.cut(f["dias_activo"], bins=[-1, 30, 90, 180, 365, 730, 100000],
                labels=["< 1 mes", "1–3 meses", "3–6 meses", "6–12 meses", "1–2 años", "> 2 años"])
antig = tramos.value_counts().sort_index().rename_axis("tramo").reset_index(name="n")
antiguedad = (alt.Chart(antig, title="Cuánto tiempo llevan activos")
              .mark_bar(color=COLOR, cornerRadiusEnd=4)
              .encode(x=alt.X("tramo:N", sort=list(antig["tramo"]), title=None),
                      y=alt.Y("n:Q", title="Presentaciones"),
                      tooltip=[alt.Tooltip("tramo:N", title="Antigüedad"),
                               alt.Tooltip("n:Q", title="Presentaciones")])
              .properties(height=260))

col_c, col_d = st.columns(2)
col_c.altair_chart(evolucion, width="stretch")
col_d.altair_chart(antiguedad, width="stretch")
st.caption("Ojo: la AEMPS solo publica los problemas activos. La gráfica de meses no muestra "
           "todos los desabastecimientos que empezaron cada mes, solo los que siguen abiertos.")

# ----------------------------------------------------------------------------- Tabla
st.subheader(f"Detalle ({len(f)} presentaciones)")
tabla = f[["cn", "nombre", "principio_activo", "laboratorio", "grupo_atc_texto", "tipo_texto",
           "fecha_inicio", "fecha_fin_prevista", "dias_activo", "es_vacuna", "observaciones"]]
st.dataframe(
    tabla.sort_values("fecha_inicio", ascending=False),
    hide_index=True, width="stretch",
    column_config={
        "cn": "CN", "nombre": "Medicamento", "principio_activo": "Principio activo",
        "laboratorio": "Laboratorio", "grupo_atc_texto": "Grupo ATC", "tipo_texto": "Tipo",
        "fecha_inicio": st.column_config.DateColumn("Inicio", format="DD/MM/YYYY"),
        "fecha_fin_prevista": st.column_config.DateColumn("Fin previsto", format="DD/MM/YYYY"),
        "dias_activo": st.column_config.NumberColumn("Días activo"),
        "es_vacuna": st.column_config.CheckboxColumn("Vacuna"),
        "observaciones": "Observaciones",
    },
)
st.download_button("Descargar tabla filtrada (CSV)",
                   tabla.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"desabastecimientos_{fecha}.csv", mime="text/csv")
