import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from io import StringIO
import os
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

URL_PUNTOS = "https://www.futbolfantasy.com/laliga/estadisticas-puntos/jugador"
URL_MERCADO = "https://www.futbolfantasy.com/analytics/laliga-fantasy/mercado"
URL_LESIONADOS = "https://www.futbolfantasy.com/laliga/lesionados"


def separar_nombre_repetido(texto):
    texto = str(texto).strip()
    n = len(texto)
    for L in range(n // 2, 0, -1):
        if texto[n - 2 * L:n - L] == texto[n - L:]:
            return texto[:n - L].strip()
    return texto


def extraer_id_de_enlace(enlace):
    if enlace:
        match = re.search(r'/jugadores/([^/]+)', str(enlace))
        if match:
            return match.group(1).lower()
    return None


def obtener_puntos():
    print("Descargando puntos...")
    r = requests.get(URL_PUNTOS, headers=HEADERS, timeout=20)
    r.raise_for_status()

    # extract_links="body" es la clave que funcionó para sacar los IDs
    tablas = pd.read_html(StringIO(r.text), flavor="lxml", extract_links="body")
    df = max(tablas, key=len)
    col_jugador = df.columns[0]
    
    # Extraemos el ID de la URL y el nombre del texto
    df["ID"] = df[col_jugador].apply(lambda x: extraer_id_de_enlace(x[1]) if isinstance(x, tuple) else None)
    df["Jugador"] = df[col_jugador].apply(lambda x: separar_nombre_repetido(x[0]) if isinstance(x, tuple) else x)

    col_puntos = [c for c in df.columns if "Fantasy" in str(c) and "Partido" not in str(c)]
    col_puntos = col_puntos[0] if col_puntos else df.columns[-2]

    df["Puntos"] = df[col_puntos].apply(lambda x: pd.to_numeric(x[0] if isinstance(x, tuple) else x, errors="coerce")).fillna(0).astype(int)
    
    return df[["ID", "Jugador", "Puntos"]].dropna(subset=["ID"])


def obtener_mercado():
    print("Descargando mercado (Valor actual y anterior)...")
    r = requests.get(URL_MERCADO, headers=HEADERS, timeout=20)
    r.raise_for_status()

    tablas = pd.read_html(StringIO(r.text), flavor="lxml", extract_links="body")
    df = max(tablas, key=len)

    col_jugador = [c for c in df.columns if "Jugador" in str(c)][0]
    
    # Localizar automáticamente las columnas "Valor" y "Valor ant.Ant."
    cols_valor = [c for c in df.columns if "Valor" in str(c)]
    col_valor_actual = cols_valor[0] if len(cols_valor) > 0 else df.columns[6]
    col_valor_anterior = cols_valor[1] if len(cols_valor) > 1 else df.columns[7]

    df["ID"] = df[col_jugador].apply(lambda x: extraer_id_de_enlace(x[1]) if isinstance(x, tuple) else None)

    def limpiar_valor(celda):
        texto = str(celda[0]) if isinstance(celda, tuple) else str(celda)
        precios = re.findall(r"\d{1,3}(?:\.\d{3})*", texto)
        return int(precios[0].replace(".", "")) if precios else None

    # Solo cogemos los precios, omitimos tendencias y diferencias
    df["Valor"] = df[col_valor_actual].apply(limpiar_valor)
    df["Valor_Anterior"] = df[col_valor_anterior].apply(limpiar_valor)

    return df[["ID", "Valor", "Valor_Anterior"]].dropna(subset=["ID", "Valor"])


def obtener_lesionados():
    print("Descargando estado de lesiones...")
    r = requests.get(URL_LESIONADOS, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    filas = []

    for enlace in soup.select('a[href*="/jugadores/"]'):
        jugador_id = extraer_id_de_enlace(enlace.get("href"))
        if not jugador_id:
            continue
            
        estado = "Lesionado"
        img = enlace.find_parent().find_previous("img", src=re.compile(r"(lesionado|duda|disponible)_box"))
        if img and img.get("src"):
            if "duda" in img["src"]: estado = "Duda"
            elif "disponible" in img["src"]: estado = "Disponible"
                
        filas.append({"ID": jugador_id, "Estado": estado})

    if not filas:
        return pd.DataFrame(columns=["ID", "Estado"])
    return pd.DataFrame(filas).drop_duplicates(subset=["ID"])


if __name__ == "__main__":
    try:
        df_puntos = obtener_puntos()
        df_mercado = obtener_mercado()
        df_lesionados = obtener_lesionados()

        # CRUCE EXACTO POR ID
        df_hoy = df_puntos.merge(df_mercado, on="ID", how="left")
        df_hoy = df_hoy.merge(df_lesionados, on="ID", how="left")
        
        # Valores por defecto
        df_hoy["Estado"] = df_hoy["Estado"].fillna("Disponible")
        
        # Filtramos para quedarnos EXCLUSIVAMENTE con lo que has pedido
        df_hoy = df_hoy[["ID", "Jugador", "Puntos", "Valor", "Valor_Anterior", "Estado"]]
        
        # Limpiar filas vacías y forzar números enteros (quitando .0 de pandas)
        df_hoy = df_hoy.dropna(subset=["Valor"])
        df_hoy["Valor"] = df_hoy["Valor"].astype(int)
        df_hoy["Valor_Anterior"] = df_hoy["Valor_Anterior"].fillna(0).astype(int)

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
        print(f"✅ ¡ÉXITO! Se guardaron {len(df_hoy)} jugadores con el ID exacto.")
        print(df_hoy.head(10))

    except Exception as e:
        print(f"❌ Error: {e}")
        raise e
