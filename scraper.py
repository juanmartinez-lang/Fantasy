import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from io import StringIO
import os
import re
import unicodedata

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

URL_PUNTOS = "https://www.futbolfantasy.com/laliga/estadisticas-puntos/jugador"
URL_MERCADO = "https://www.futbolfantasy.com/analytics/laliga-fantasy/mercado"
URL_LESIONADOS = "https://www.futbolfantasy.com/laliga/lesionados"

def separar_nombre_repetido(texto):
    """'Antonio SiveraSivera' -> 'Antonio Sivera'"""
    texto = str(texto).strip()
    n = len(texto)
    for L in range(n // 2, 0, -1):
        if texto[n - 2 * L:n - L] == texto[n - L:]:
            return texto[:n - L].strip()
    return texto

def normalizar(nombre):
    """Quita tildes, mayúsculas y espacios extra para que el cruce sea perfecto."""
    texto = str(nombre).strip().lower()
    return unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode("utf-8")

def extraer_num(texto):
    """Saca números limpios de un texto."""
    nums = re.findall(r"\d{1,3}(?:\.\d{3})*", str(texto))
    return int(nums[0].replace(".", "")) if nums else None


def obtener_puntos():
    print("Descargando puntos y jornadas...")
    r = requests.get(URL_PUNTOS, headers=HEADERS, timeout=20)
    tablas = pd.read_html(StringIO(r.text), flavor="lxml")
    df = max(tablas, key=len)
    
    col_jugador = df.columns[0]
    col_puntos = [c for c in df.columns if "Fantasy" in str(c) and "Partido" not in str(c)]
    col_puntos = col_puntos[0] if col_puntos else df.columns[-2]

    df["Jugador"] = df[col_jugador].apply(separar_nombre_repetido)
    df["Puntos"] = pd.to_numeric(df[col_puntos], errors="coerce").fillna(0).astype(int)
    df["clave"] = df["Jugador"].apply(normalizar)

    # Detectar dinámicamente las columnas de cada jornada (ej. "1", "2", "3")
    lista_jornadas = []
    for col in df.columns:
        texto_col = str(col).strip()
        # Busca columnas que sean números exactos (o empiecen por J, por si cambian el formato)
        match = re.match(r'^(?:J\s*)?(\d+)$', texto_col, re.IGNORECASE)
        if match:
            num_jornada = match.group(1)
            nombre_limpio = f"J{num_jornada}"
            # Convierte los guiones o vacíos en 0 puntos
            df[nombre_limpio] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            lista_jornadas.append(nombre_limpio)
            
    # Solo devolvemos lo esencial + las jornadas encontradas
    columnas_devolver = ["Jugador", "Puntos", "clave"] + lista_jornadas
    return df[columnas_devolver], lista_jornadas


def obtener_mercado():
    print("Descargando mercado (Valor actual y anterior)...")
    r = requests.get(URL_MERCADO, headers=HEADERS, timeout=20)
    tablas = pd.read_html(StringIO(r.text), flavor="lxml")
    df = max(tablas, key=len)

    col_jugador = [c for c in df.columns if "Jugador" in str(c)][0]
    cols_valor = [c for c in df.columns if "Valor" in str(c)]
    col_valor_actual = cols_valor[-2] if len(cols_valor) >= 2 else df.columns[6]
    col_valor_anterior = cols_valor[-1] if len(cols_valor) >= 2 else df.columns[7]

    def limpiar_nombre_mercado(texto):
        partes = re.split(r'\s{2,}', str(texto).strip())
        return separar_nombre_repetido(partes[0])

    df["Jugador_limpio"] = df[col_jugador].apply(limpiar_nombre_mercado)
    df["Valor"] = df[col_valor_actual].apply(extraer_num)
    df["Valor_Anterior"] = df[col_valor_anterior].apply(extraer_num)
    
    df["clave"] = df["Jugador_limpio"].apply(normalizar)
    return df[["clave", "Valor", "Valor_Anterior"]].dropna(subset=["Valor"])


def obtener_lesionados():
    print("Descargando estado de lesiones...")
    r = requests.get(URL_LESIONADOS, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "lxml")
    filas = []

    for enlace in soup.select('a[href*="/jugadores/"]'):
        nombre = enlace.get_text(strip=True)
        if not nombre: continue
            
        estado = "Lesionado"
        img = enlace.find_parent().find_previous("img", src=re.compile(r"(lesionado|duda|disponible)_box"))
        if img and img.get("src"):
            if "duda" in img["src"]: estado = "Duda"
            elif "disponible" in img["src"]: estado = "Disponible"
                
        filas.append({"Jugador_limpio": nombre, "Estado": estado})

    df = pd.DataFrame(filas).drop_duplicates(subset=["Jugador_limpio"])
    if not df.empty:
        df["clave"] = df["Jugador_limpio"].apply(normalizar)
        return df[["clave", "Estado"]]
    return pd.DataFrame(columns=["clave", "Estado"])


if __name__ == "__main__":
    try:
        df_puntos, lista_jornadas = obtener_puntos()
        df_mercado = obtener_mercado()
        df_lesionados = obtener_lesionados()

        # Cruce maestro
        df_hoy = df_puntos.merge(df_mercado, on="clave", how="left")
        df_hoy = df_hoy.merge(df_lesionados, on="clave", how="left")
        
        # Limpieza final
        df_hoy["Estado"] = df_hoy["Estado"].fillna("Disponible")
        df_hoy = df_hoy.dropna(subset=["Valor"])
        df_hoy["Valor"] = df_hoy["Valor"].astype(int)
        df_hoy["Valor_Anterior"] = df_hoy["Valor_Anterior"].fillna(0).astype(int)

        # Ordenamos las columnas: Básicos + Jornadas + Precios
        columnas_finales = ["Jugador", "Puntos"] + lista_jornadas + ["Valor", "Valor_Anterior", "Estado", "Fecha"]
        
        fecha_hoy = datetime.today().strftime("%Y-%m-%d")
        df_hoy["Fecha"] = fecha_hoy
        df_hoy = df_hoy[columnas_finales]

        archivo_csv = "historico_fantasy.csv"
        
        if os.path.exists(archivo_csv):
            df_existente = pd.read_csv(archivo_csv)
            # Comprobación de seguridad: Si no están las columnas vitales, sobreescribe todo
            if not {"Jugador", "Valor", "Fecha"}.issubset(df_existente.columns):
                print("🔄 Formato de CSV roto detectado. Sobreescribiendo desde cero...")
                df_final = df_hoy
            else:
                df_existente = df_existente[df_existente["Fecha"] != fecha_hoy]
                # Juntamos lo antiguo con lo nuevo. Pandas se encarga solo de emparejar las J1, J2, etc.
                df_final = pd.concat([df_existente, df_hoy], ignore_index=True)
                
                # Para evitar que las jornadas nuevas queden vacías en el registro de días anteriores
                for j in lista_jornadas:
                    if j in df_final.columns:
                        df_final[j] = df_final[j].fillna(0).astype(int)
        else:
            df_final = df_hoy

        # Reordenamos el CSV final para que siempre mantenga la estructura limpia
        columnas_ordenadas = [c for c in columnas_finales if c in df_final.columns]
        df_final = df_final[columnas_ordenadas]

        df_final.to_csv(archivo_csv, index=False, encoding="utf-8-sig")
        print(f"✅ ¡ÉXITO! Se guardaron {len(df_hoy)} jugadores con sus {len(lista_jornadas)} jornadas jugadas.")
        print(df_hoy.head(3))

    except Exception as e:
        print(f"❌ Error: {e}")
        raise e
