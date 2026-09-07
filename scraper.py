import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from io import StringIO
import os
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
    """Extrae 'antonio-sivera' de '/jugadores/antonio-sivera' para usarlo como ID."""
    if enlace:
        match = re.search(r'/jugadores/([^/]+)', enlace)
        if match:
            return match.group(1).lower()
    return None


def obtener_puntos():
    print("Descargando puntos por jugador...")
    r = requests.get(URL_PUNTOS, headers=HEADERS, timeout=20)
    r.raise_for_status()

    # extract_links="body" saca el texto y el enlace en una tupla: ('Antonio Sivera', '/jugadores/antonio...')
    tablas = pd.read_html(StringIO(r.text), flavor="lxml", extract_links="body")
    df = max(tablas, key=len)
    
    col_jugador = df.columns[0]
    
    # Extraemos el ID desde el enlace y el Nombre desde el texto
    df["ID"] = df[col_jugador].apply(lambda x: extraer_id_de_enlace(x[1]))
    df["Jugador"] = df[col_jugador].apply(lambda x: separar_nombre_repetido(x[0]))

    col_puntos = [c for c in df.columns if "Fantasy" in str(c) and "Partido" not in str(c)]
    col_puntos = col_puntos[0] if col_puntos else df.columns[-2]

    # Convertimos los puntos (tupla [0] es el texto) a entero
    df["Puntos"] = df[col_puntos].apply(lambda x: pd.to_numeric(x[0], errors="coerce")).fillna(0).astype(int)
    
    return df[["ID", "Jugador", "Puntos"]].dropna(subset=["ID"])


def obtener_mercado():
    print("Descargando mercado (valores)...")
    r = requests.get(URL_MERCADO, headers=HEADERS, timeout=20)
    r.raise_for_status()

    tablas = pd.read_html(StringIO(r.text), flavor="lxml", extract_links="body")
    df = max(tablas, key=len)

    col_jugador = [c for c in df.columns if "Jugador" in str(c)][0]
    col_dif = [c for c in df.columns if "Dif" in str(c)][0]
    cols_valor = [c for c in df.columns if "Valor" in str(c)]
    col_valor = cols_valor[-1] if cols_valor else df.columns[6]

    df["ID"] = df[col_jugador].apply(lambda x: extraer_id_de_enlace(x[1]))

    # El equipo está en el texto de la celda jugador (tupla[0])
    def aislar_equipo(texto):
        partes = re.split(r"\s{2,}", str(texto).strip())
        return partes[1] if len(partes) > 1 else "Desconocido"
        
    df["Equipo"] = df[col_jugador].apply(lambda x: aislar_equipo(x[0]))

    def limpiar_valor(tupla):
        precios = re.findall(r"\d{1,3}(?:\.\d{3})*", str(tupla[0]))
        return int(precios[0].replace(".", "")) if precios else None

    def limpiar_tendencia(tupla):
        texto = str(tupla[0])
        if "+" in texto: return "Sube"
        if "-" in texto: return "Baja"
        return "Mantiene"

    df["Valor"] = df[col_valor].apply(limpiar_valor)
    df["Tendencia"] = df[col_dif].apply(limpiar_tendencia)

    return df[["ID", "Equipo", "Valor", "Tendencia"]].dropna(subset=["ID", "Valor"])


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
            
        contenedor = enlace.find_parent()
        estado = "Lesionado"
        if contenedor:
            img_estado = contenedor.find_previous("img", src=re.compile(r"(lesionado|duda|disponible)_box"))
            if img_estado and img_estado.get("src"):
                if "duda" in img_estado["src"]: estado = "Duda"
                elif "disponible" in img_estado["src"]: estado = "Disponible"
                
        filas.append({"ID": jugador_id, "Estado": estado})

    return pd.DataFrame(filas).drop_duplicates(subset=["ID"])


if __name__ == "__main__":
    try:
        df_puntos = obtener_puntos()
        df_mercado = obtener_mercado()
        df_lesionados = obtener_lesionados()

        # CRUCE 100% PERFECTO BASADO EN ID (URL DEL JUGADOR)
        df_hoy = df_puntos.merge(df_mercado, on="ID", how="left")
        
        print(f"[DEBUG] filas con valor tras cruzar mercado: {df_hoy['Valor'].notna().sum()} / {len(df_hoy)}")
        
        df_hoy = df_hoy.merge(df_lesionados, on="ID", how="left")
        df_hoy["Estado"] = df_hoy["Estado"].fillna("Disponible")
        
        df_hoy = df_hoy[["ID", "Jugador", "Equipo", "Puntos", "Valor", "Tendencia", "Estado"]]

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
