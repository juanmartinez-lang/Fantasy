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
    """Limpia 'Antonio SiveraSivera' -> 'Antonio Sivera'"""
    texto = str(texto).strip()
    n = len(texto)
    for L in range(n // 2, 0, -1):
        if texto[n - 2 * L:n - L] == texto[n - L:]:
            return texto[:n - L].strip()
    return texto

def normalizar(nombre):
    """Homogeneiza textos para el cruce maestro"""
    texto = str(nombre).strip().lower()
    return unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode("utf-8")

def extraer_num(texto):
    """Extrae números enteros obviando puntos y signos"""
    nums = re.findall(r"\d{1,3}(?:\.\d{3})*", str(texto))
    return int(nums[0].replace(".", "")) if nums else None


def obtener_puntos():
    print("Descargando puntos, jornadas y detectando posiciones (HTML)...")
    r = requests.get(URL_PUNTOS, headers=HEADERS, timeout=20)
    
    # 1. Escanear el HTML oculto para sacar la Posición exacta de las clases CSS
    soup = BeautifulSoup(r.text, "lxml")
    posiciones = {}
    for tr in soup.find_all('tr'):
        a = tr.find('a', href=re.compile(r'/jugadores/'))
        if a:
            clave = normalizar(separar_nombre_repetido(a.get_text(strip=True)))
            pos = "Desc"
            
            # Buscamos en todas las etiquetas de la fila (span, i, etc)
            for tag in tr.find_all(True):
                clases = tag.get('class', [])
                clases_str = " ".join(clases).lower() if isinstance(clases, list) else str(clases).lower()
                
                if re.search(r'\b(pt|por|portero)\b', clases_str): pos = "Portero"
                elif re.search(r'\b(df|def|defensa)\b', clases_str): pos = "Defensa"
                elif re.search(r'\b(mc|med|mediocentro)\b', clases_str): pos = "Mediocentro"
                elif re.search(r'\b(dl|del|delantero)\b', clases_str): pos = "Delantero"
                
                if pos != "Desc":
                    break
            
            posiciones[clave] = pos

    # 2. Extraer los puntos y jornadas con Pandas
    tablas = pd.read_html(StringIO(r.text), flavor="lxml")
    df = max(tablas, key=len)
    
    col_jugador = df.columns[0]
    col_puntos = next((c for c in df.columns if ('fantasy' in str(c).lower() or 'pts' in str(c).lower() or 'total' in str(c).lower()) and 'partido' not in str(c).lower()), df.columns[-2])
    
    df["Jugador"] = df[col_jugador].apply(lambda x: separar_nombre_repetido(x[0]) if isinstance(x, tuple) else separar_nombre_repetido(x))
    df["Puntos"] = pd.to_numeric(df[col_puntos], errors="coerce").fillna(0).astype(int)
    df["clave"] = df["Jugador"].apply(normalizar)
    
    # Mapeamos la posición real desde nuestro escáner HTML
    df["Posicion"] = df["clave"].map(posiciones).fillna("Desc")

    # 3. Detectar Jornadas
    lista_jornadas = []
    for col in df.columns:
        col_str = str(col[-1] if isinstance(col, tuple) else col).strip()
        match = re.search(r'^(?:J|Jornada\s*)?(\d+)$', col_str, re.IGNORECASE)
        if match:
            num_j = match.group(1)
            nombre_j = f"J{num_j}"
            df[nombre_j] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            if nombre_j not in lista_jornadas:
                lista_jornadas.append(nombre_j)
                
    cols_devolver = ["clave", "Jugador", "Posicion", "Puntos"] + lista_jornadas
    return df[cols_devolver], lista_jornadas


def obtener_mercado():
    print("Descargando mercado y equipo...")
    r = requests.get(URL_MERCADO, headers=HEADERS, timeout=20)
    tablas = pd.read_html(StringIO(r.text), flavor="lxml")
    df = max(tablas, key=len)

    col_jugador = [c for c in df.columns if "Jugador" in str(c)][0]
    cols_valor = [c for c in df.columns if "Valor" in str(c)]
    col_valor_actual = cols_valor[-2] if len(cols_valor) >= 2 else df.columns[6]
    col_valor_anterior = cols_valor[-1] if len(cols_valor) >= 2 else df.columns[7]

    def extraer_equipo(texto):
        partes = re.split(r'\s{2,}', str(texto).strip())
        return partes[1] if len(partes) > 1 else "Desconocido"

    def extraer_nombre(texto):
        partes = re.split(r'\s{2,}', str(texto).strip())
        return separar_nombre_repetido(partes[0])

    df["Jugador_limpio"] = df[col_jugador].apply(extraer_nombre)
    df["Equipo"] = df[col_jugador].apply(extraer_equipo)
    df["Valor"] = df[col_valor_actual].apply(extraer_num)
    df["Valor_Anterior"] = df[col_valor_anterior].apply(extraer_num)
    
    df["clave"] = df["Jugador_limpio"].apply(normalizar)
    
    if "Valor" in df.columns:
        df = df.dropna(subset=["Valor"])
        
    return df[["clave", "Equipo", "Valor", "Valor_Anterior"]]


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
        
        # Limpieza
        df_hoy["Estado"] = df_hoy["Estado"].fillna("Disponible")
        df_hoy["Equipo"] = df_hoy["Equipo"].fillna("Desconocido")
        
        if "Valor" in df_hoy.columns:
            df_hoy = df_hoy.dropna(subset=["Valor"])
            df_hoy["Valor"] = df_hoy["Valor"].astype(int)
            df_hoy["Valor_Anterior"] = df_hoy["Valor_Anterior"].fillna(0).astype(int)

        # ORDEN PERFECTO
        columnas_finales = ["Jugador", "Equipo", "Posicion", "Puntos"] + lista_jornadas + ["Valor", "Valor_Anterior", "Estado", "Fecha"]
        
        fecha_hoy = datetime.today().strftime("%Y-%m-%d")
        df_hoy["Fecha"] = fecha_hoy
        df_hoy = df_hoy[columnas_finales]

        archivo_csv = "historico_fantasy.csv"
        
        if os.path.exists(archivo_csv):
            df_existente = pd.read_csv(archivo_csv)
            # Recrear el archivo si la posición no se guardó bien antes
            if "Desc" in df_existente["Posicion"].values and "Portero" in df_hoy["Posicion"].values:
                print("🔄 Actualizando CSV antiguo con las Posiciones correctas...")
                df_final = df_hoy
            else:
                df_existente = df_existente[df_existente["Fecha"] != fecha_hoy]
                df_final = pd.concat([df_existente, df_hoy], ignore_index=True)
                for j in lista_jornadas:
                    if j in df_final.columns:
                        df_final[j] = df_final[j].fillna(0).astype(int)
        else:
            df_final = df_hoy

        df_final = df_final[columnas_finales]
        df_final.to_csv(archivo_csv, index=False, encoding="utf-8-sig")
        
        print(f"✅ ¡ÉXITO! Se guardaron {len(df_hoy)} jugadores con sus posiciones reales (Portero, Defensa, etc).")
        print(df_hoy.head(5))

    except Exception as e:
        print(f"❌ Error: {e}")
        raise e
