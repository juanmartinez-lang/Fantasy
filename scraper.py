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
    texto = str(nombre).strip().lower()
    return unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode("utf-8")

def extraer_num(texto):
    nums = re.findall(r"\d{1,3}(?:\.\d{3})*", str(texto))
    return int(nums[0].replace(".", "")) if nums else None


def obtener_puntos():
    print("Descargando puntos y jornadas (Pandas)...")
    r = requests.get(URL_PUNTOS, headers=HEADERS, timeout=20)
    tablas = pd.read_html(StringIO(r.text), flavor="lxml")
    df = max(tablas, key=len)
    
    col_jugador = df.columns[0]
    
    # Buscar dinámicamente la columna de Puntos Totales
    col_puntos = None
    for c in df.columns:
        c_str = str(c).lower()
        if ('fantasy' in c_str or 'total' in c_str or 'pts' in c_str) and 'partido' not in c_str:
            col_puntos = c
            break
    if not col_puntos: col_puntos = df.columns[-2]

    df["Jugador"] = df[col_jugador].apply(separar_nombre_repetido)
    df["Puntos"] = pd.to_numeric(df[col_puntos], errors="coerce").fillna(0).astype(int)
    df["clave"] = df["Jugador"].apply(normalizar)

    # Detectar dinámicamente las jornadas (J1, J2, J3...) esquivando sub-cabeceras
    lista_jornadas = []
    for col in df.columns:
        col_name = col[-1] if isinstance(col, tuple) else col
        match = re.match(r'^(?:J\s*)?(\d+)$', str(col_name).strip(), re.IGNORECASE)
        if match:
            num_j = match.group(1)
            nombre_j = f"J{num_j}"
            df[nombre_j] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
            if nombre_j not in lista_jornadas:
                lista_jornadas.append(nombre_j)
                
    cols_finales = ["clave", "Jugador", "Puntos"] + lista_jornadas
    return df[cols_finales], lista_jornadas


def obtener_mercado():
    print("Descargando mercado, posición y equipo (BeautifulSoup)...")
    r = requests.get(URL_MERCADO, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, 'lxml')
    filas = []
    
    for tr in soup.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) < 5: continue
        
        enlace = tr.find('a', href=re.compile(r'/jugadores/'))
        if not enlace: continue
        
        nombre_limpio = separar_nombre_repetido(enlace.get_text(strip=True))
        clave = normalizar(nombre_limpio)
        
        # Extraer Posición y Equipo separando cada etiqueta HTML (sin mezclar textos)
        textos_celda = [t.strip() for t in tds[0].stripped_strings if t.strip()]
        posicion = "Desc"
        equipo = "Desconocido"
        
        for texto in textos_celda:
            t_upper = texto.upper()
            if t_upper in ['PT', 'DF', 'MC', 'DL', 'POR', 'MED', 'DEL']:
                posicion = t_upper
            elif t_upper not in nombre_limpio.upper() and len(texto) > 2:
                equipo = texto

        valor_actual = extraer_num(tds[-2].get_text(strip=True))
        valor_anterior = extraer_num(tds[-1].get_text(strip=True))
        
        filas.append({
            "clave": clave,
            "Equipo": equipo,
            "Posicion": posicion,
            "Valor": valor_actual,
            "Valor_Anterior": valor_anterior
        })
        
    return pd.DataFrame(filas).dropna(subset=["Valor"])


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

        # Cruce maestro exacto
        df_hoy = df_puntos.merge(df_mercado, on="clave", how="left")
        df_hoy = df_hoy.merge(df_lesionados, on="clave", how="left")
        
        # Limpieza de valores vacíos tras el cruce
        df_hoy["Estado"] = df_hoy["Estado"].fillna("Disponible")
        df_hoy["Equipo"] = df_hoy["Equipo"].fillna("Desconocido")
        df_hoy["Posicion"] = df_hoy["Posicion"].fillna("Desc")
        df_hoy = df_hoy.dropna(subset=["Valor"])
        df_hoy["Valor"] = df_hoy["Valor"].astype(int)
        df_hoy["Valor_Anterior"] = df_hoy["Valor_Anterior"].fillna(0).astype(int)

        columnas_finales = ["Jugador", "Equipo", "Posicion", "Puntos"] + lista_jornadas + ["Valor", "Valor_Anterior", "Estado", "Fecha"]
        
        fecha_hoy = datetime.today().strftime("%Y-%m-%d")
        df_hoy["Fecha"] = fecha_hoy
        df_hoy = df_hoy[columnas_finales]

        archivo_csv = "historico_fantasy.csv"
        
        if os.path.exists(archivo_csv):
            df_existente = pd.read_csv(archivo_csv)
            # Recrea el archivo si le faltan las columnas nuevas de Equipo o Posición
            if not {"Equipo", "Posicion"}.issubset(df_existente.columns):
                print("🔄 Formato de CSV antiguo detectado. Regenerando desde cero...")
                df_final = df_hoy
            else:
                df_existente = df_existente[df_existente["Fecha"] != fecha_hoy]
                df_final = pd.concat([df_existente, df_hoy], ignore_index=True)
                
                # Rellena con 0 si en días anteriores no existían las jornadas nuevas
                for j in lista_jornadas:
                    if j in df_final.columns:
                        df_final[j] = df_final[j].fillna(0).astype(int)
        else:
            df_final = df_hoy

        df_final = df_final[columnas_finales]
        df_final.to_csv(archivo_csv, index=False, encoding="utf-8-sig")
        
        print(f"✅ ¡ÉXITO! Se guardaron {len(df_hoy)} jugadores con Equipo, Posición y {len(lista_jornadas)} jornadas.")
        print(df_hoy.head(3))

    except Exception as e:
        print(f"❌ Error: {e}")
        raise e
