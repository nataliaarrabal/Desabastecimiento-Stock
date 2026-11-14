"""
Paso 2: primera exploración de las fuentes descargadas.

Contesta a las cuatro preguntas del plan para AEMPS y EMA:
  1. ¿Cuántos registros hay?
  2. ¿Viene el laboratorio?
  3. ¿Vienen fechas de inicio y fin?
  4. ¿Hay histórico o solo lo activo?

Uso:
    python explorar_fuentes.py              (usa los archivos más recientes de datos_raw/)
    python explorar_fuentes.py > exploracion.txt   (para guardar la salida)
"""

import json
from pathlib import Path

import pandas as pd

CARPETA = Path(__file__).parent / "datos_raw"
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)
pd.set_option("display.max_colwidth", 60)


def ultimo(patron):
    archivos = sorted(CARPETA.glob(patron))
    if not archivos:
        raise FileNotFoundError(f"No hay archivos {patron} en {CARPETA}")
    return archivos[-1]


def resumen_columnas(df):
    """Tipo, % vacíos, nº de valores distintos y un ejemplo de cada columna."""
    filas = []
    for c in df.columns:
        no_nulos = df[c].dropna()
        filas.append({
            "columna": c,
            "tipo": str(df[c].dtype),
            "%_vacios": round(df[c].isna().mean() * 100, 1),
            "n_distintos": df[c].astype(str).nunique(),
            "ejemplo": str(no_nulos.iloc[0])[:60] if len(no_nulos) else "",
        })
    return pd.DataFrame(filas)


def buscar_columnas(df, palabras):
    return [c for c in df.columns if any(p in str(c).lower() for p in palabras)]


def convertir_fechas(df, columnas):
    """CIMA suele dar las fechas como milisegundos desde 1970; si no, se intenta como texto."""
    for c in columnas:
        if pd.api.types.is_numeric_dtype(df[c]):
            df[c] = pd.to_datetime(df[c], unit="ms", errors="coerce")
        else:
            df[c] = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
    return df


def informe_fechas(df, columnas):
    for c in columnas:
        s = df[c].dropna()
        if len(s):
            print(f"  {c}: de {s.min():%Y-%m-%d} a {s.max():%Y-%m-%d}  ({df[c].isna().mean()*100:.0f}% vacíos)")


# --------------------------------------------------------------------------- AEMPS
def explorar_aemps():
    ruta = ultimo("aemps_*.json")
    print("=" * 80)
    print(f"AEMPS  ({ruta.name})")
    print("=" * 80)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    df = pd.json_normalize(datos["resultados"])

    print(f"\n1. Registros: {len(df)} filas")
    if "cn" in df.columns:
        print(f"   Códigos nacionales (presentaciones) distintos: {df['cn'].nunique()}")
        print(f"   ¿Hay CN repetidos?: {'sí' if df['cn'].duplicated().any() else 'no'}")

    print("\n   Columnas:")
    print(resumen_columnas(df).to_string(index=False))

    lab = buscar_columnas(df, ["lab", "titular"])
    print(f"\n2. ¿Laboratorio?: {lab if lab else 'NO viene en este endpoint -> habrá que cruzarlo por CN con /presentaciones o el nomenclátor'}")

    fechas = buscar_columnas(df, ["fini", "ffin", "fecha"])
    print(f"\n3. Columnas de fecha: {fechas if fechas else 'ninguna'}")
    df = convertir_fechas(df, fechas)
    informe_fechas(df, fechas)

    print("\n4. ¿Histórico o solo activo?")
    if "activo" in df.columns:
        print(df["activo"].value_counts(dropna=False).to_string())
    else:
        print("   No hay columna 'activo'; revisa si hay fechas de fin pasadas.")

    for c in buscar_columnas(df, ["tipo"]):
        print(f"\n   Valores de {c}:")
        print(df[c].value_counts(dropna=False).head(15).to_string())

    print("\n   Primeras filas:")
    print(df.head(5).to_string(index=False))
    return df


# --------------------------------------------------------------------------- EMA
def leer_excel_ema(ruta):
    """Los Excel de la EMA suelen traer varias filas de título antes de la tabla.
    Busca la primera fila con muchas celdas rellenas y la usa como cabecera."""
    crudo = pd.read_excel(ruta, header=None)
    rellenas = crudo.notna().sum(axis=1)
    fila_cabecera = int((rellenas >= max(3, rellenas.max() * 0.6)).idxmax())
    df = pd.read_excel(ruta, header=fila_cabecera)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    return df, fila_cabecera


def explorar_ema():
    ruta = ultimo("ema_*.xlsx")
    print("\n" + "=" * 80)
    print(f"EMA  ({ruta.name})")
    print("=" * 80)
    hojas = pd.ExcelFile(ruta).sheet_names
    print(f"Hojas del Excel: {hojas}")
    df, fila = leer_excel_ema(ruta)
    print(f"(cabecera detectada en la fila {fila + 1} del Excel)")

    print(f"\n1. Registros: {len(df)} filas")
    print("\n   Columnas:")
    print(resumen_columnas(df).to_string(index=False))

    lab = buscar_columnas(df, ["holder", "mah", "company", "laborat"])
    print(f"\n2. ¿Laboratorio?: {lab if lab else 'no se ha encontrado una columna obvia, revisa la lista de arriba'}")

    fechas = buscar_columnas(df, ["date", "start", "end", "resol", "first published", "updated"])
    print(f"\n3. Columnas de fecha: {fechas if fechas else 'ninguna'}")
    df = convertir_fechas(df, fechas)
    informe_fechas(df, fechas)

    print("\n4. ¿Histórico o solo activo?")
    estado = buscar_columnas(df, ["status", "state", "estado"])
    for c in estado:
        print(f"   Valores de {c}:")
        print(df[c].value_counts(dropna=False).to_string())
    if not estado:
        print("   No hay columna de estado obvia; revisa fechas de resolución.")

    print("\n   Primeras filas:")
    print(df.head(5).to_string(index=False))
    return df


if __name__ == "__main__":
    for funcion in (explorar_aemps, explorar_ema):
        try:
            funcion()
        except Exception as e:
            print(f"\nERROR en {funcion.__name__}: {e}")
