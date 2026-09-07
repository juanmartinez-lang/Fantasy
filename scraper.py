import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import os
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

URL_PUNTOS = "https://www.futbolfantasy.com/laliga/estadisticas-puntos/jugador"
URL_MERCADO = "https://www.futbolfantasy.com/analytics/laliga-fantasy/mercado"
URL_LESIONADOS = "https://www.futbolfantasy.com/laliga/lesionados"


def obtener_puntos():
    """Devuelve DataFrame con Jugador y Puntos Fantasy."""
    print("Descargando puntos por jugador...")
    r = requests.get(URL_PUNTOS, headers=HEADERS, timeout=20)
    r.raise_for_status()

    tablas = pd.read_html(r.text, flavor="lxml")
    # Buscamos la tabla grande de jugadores (muchas filas y columnas)
    df = max(tablas, key=lambda t: len(t))

    # La primera columna suele traer el nombre del jugador (a veces con
    # texto duplicado tipo "Ali HouaryAli Houary" por el alt de la imagen)
    df = df.rename(columns={df.columns[0]: "Jugador_raw"})

    # Limpiar nombre: si el texto está duplicado, quedarnos con la mitad
    def limpiar_nombre(x):
        x = str(x).strip()
        mitad = len(x) // 2
        if len(x) % 2 == 0 and x[:mitad] == x[mitad:]:
            return x[:mitad]
        return x

    df["Jugador"] = df["Jugador_raw"].apply(limpiar_nombre)

    # La última columna del bloque suele ser "Ptos. Fantasy"; ajusta el
    # nombre exacto si pandas lo trae distinto
    col_puntos = [c for c in df.columns if "Fantasy" in str(c) and "Partido" not in str(c)]
    col_puntos = col_puntos[0] if col_puntos else df.columns[-2]

    out = df[["Jugador", col_puntos]].copy()
    out.columns = ["Jugador", "Puntos"]
    out["Puntos"] = pd.to_numeric(out["Puntos"], errors="coerce").fillna(0).astype(int)
    return out


def obtener_mercado():
    """Devuelve DataFrame con Jugador, Equipo, Precio y Tendencia."""
    print("Descargando mercado (precios)...")
    r = requests.get(URL_MERCADO, headers=HEADERS, timeout=20)
    r.raise_for_status()

    tablas = pd.read_html(r.text, flavor="lxml")
    df = max(tablas, key=lambda t: len(t))

    # --- DIAGNÓSTICO: quitar estas 5 líneas cuando ya funcione ---
    print(f"[DEBUG mercado] tablas encontradas: {len(tablas)}")
    print(f"[DEBUG mercado] forma tabla elegida: {df.shape}")
    print(f"[DEBUG mercado] columnas: {df.columns.tolist()}")
    print("[DEBUG mercado] primeras 5 filas:")
    print(df.head(5).to_string())
    # ---------------------------------------------------------------

    filas = []
    for _, row in df.iterrows():
        celdas = [str(c) for c in row.tolist()]
        # La primera celda suele traer "NombreApodo Equipo" pegados
        primera = celdas[0]

        # Extraer precio actual: el último número grande con puntos de miles
        precios = re.findall(r"\d{1,3}(?:\.\d{3})+", " ".join(celdas))
        precio_actual = int(precios[0].replace(".", "")) if precios else None

        # Extraer tendencia por el signo del primer valor de diferencia
        difs = re.findall(r"[+-]\d[\d.]*", " ".join(celdas))
        if difs:
            tendencia = "Sube" if difs[0].startswith("+") else "Baja" if difs[0].startswith("-") else "Mantiene"
        else:
            tendencia = "Mantiene"

        filas.append({"Jugador_raw": primera, "Precio": precio_actual, "Tendencia": tendencia})

    out = pd.DataFrame(filas).dropna(subset=["Precio"])
    return out


def obtener_lesionados():
    """Devuelve DataFrame con Jugador y Estado (Lesionado/Duda/Disponible)."""
    print("Descargando estado de lesiones...")
    r = requests.get(URL_LESIONADOS, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    filas = []

    # Cada jugador lesionado tiene un enlace a /jugadores/<slug>
    for enlace in soup.select('a[href*="/jugadores/"]'):
        nombre = enlace.get_text(strip=True)
        if not nombre:
            continue
        # Buscamos la imagen de estado más cercana (lesionado/duda/disponible)
        contenedor = enlace.find_parent()
        estado = "Lesionado"
        img_estado = None
        if contenedor:
            img_estado = contenedor.find_previous("img", src=re.compile(r"(lesionado|duda|disponible)_box"))
        if img_estado and img_estado.get("src"):
            if "duda" in img_estado["src"]:
                estado = "Duda"
            elif "disponible" in img_estado["src"]:
                estado = "Disponible"
        filas.append({"Jugador_raw": nombre, "Estado": estado})

    return pd.DataFrame(filas).drop_duplicates(subset=["Jugador_raw"])


def normalizar(nombre):
    """Normaliza nombres para poder cruzar entre las 3 fuentes."""
    return str(nombre).strip().lower()


if __name__ == "__main__":
    try:
        df_puntos = obtener_puntos()
        df_mercado = obtener_mercado()
        df_lesionados = obtener_lesionados()

        df_puntos["clave"] = df_puntos["Jugador"].apply(normalizar)
        df_mercado["clave"] = df_mercado["Jugador_raw"].apply(normalizar)
        df_lesionados["clave"] = df_lesionados["Jugador_raw"].apply(normalizar)

        # --- DIAGNÓSTICO: quitar cuando ya funcione ---
        print(f"[DEBUG] claves puntos ejemplo: {df_puntos['clave'].head(5).tolist()}")
        print(f"[DEBUG] claves mercado ejemplo: {df_mercado['clave'].head(5).tolist()}")
        # -----------------------------------------------

        df_hoy = df_puntos.merge(df_mercado[["clave", "Precio", "Tendencia"]], on="clave", how="left")
        print(f"[DEBUG] filas con precio tras cruzar mercado: {df_hoy['Precio'].notna().sum()} / {len(df_hoy)}")
        df_hoy = df_hoy.merge(df_lesionados[["clave", "Estado"]], on="clave", how="left")
        df_hoy["Estado"] = df_hoy["Estado"].fillna("Disponible")
        df_hoy = df_hoy.drop(columns=["clave"])

        fecha_hoy = datetime.today().strftime("%Y-%m-%d")
        df_hoy["Fecha"] = fecha_hoy

        archivo_csv = "historico_fantasy.csv"
        if os.path.exists(archivo_csv):
            df_existente = pd.read_csv(archivo_csv)
            df_existente = df_existente[df_existente["Fecha"] != fecha_hoy]
            df_final = pd.concat([df_existente, df_hoy], ignore_index=True)
        else:
            df_final = df_hoy

        df_final.to_csv(archivo_csv, index=False, encoding="utf-8-sig")
        print(f"✅ ¡ÉXITO! Se guardaron {len(df_hoy)} jugadores.")
        print(df_hoy.head(10))

    except Exception as e:
        print(f"❌ Error: {e}")
        raise e
