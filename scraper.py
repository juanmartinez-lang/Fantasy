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
    print("Descargando puntos, equipo, posición y jornadas...")
    r = requests.get(URL_PUNTOS, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, 'lxml')
    
    # Buscamos la tabla principal de estadísticas
    tablas = soup.find_all('table')
    tabla = max(tablas, key=lambda t: len(t.find_all('tr')))
    
    # Extraemos y leemos las cabeceras reales de la web
    cabeceras = []
    thead = tabla.find('thead')
    if thead:
        for th in thead.find_all(['th', 'td']):
            cabeceras.append(th.get_text(strip=True))
    else:
        for th in tabla.find('tr').find_all(['th', 'td']):
            cabeceras.append(th.get_text(strip=True))
            
    # Mapeamos en qué número de columna está cada dato
    idx_jugador = 0
    idx_equipo = -1
    idx_pos = -1
    idx_puntos = -1
    idx_jornadas = {} 
    
    for i, cab in enumerate(cabeceras):
        cab_lower = cab.lower()
        if "equipo" in cab_lower: idx_equipo = i
        elif "pos" in cab_lower: idx_pos = i
        elif "fantasy" in cab_lower or "total" in cab_lower or cab_lower == "pts": idx_puntos = i
        elif cab.isdigit(): idx_jornadas[f"J{cab}"] = i  # Detecta "1", "2", "3"...
        
    if idx_puntos == -1:
        idx_puntos = len(cabeceras) - 2 # Por si cambia el nombre de la columna Total

    filas = []
    cuerpo = tabla.find('tbody')
    filas_html = cuerpo.find_all('tr') if cuerpo else tabla.find_all('tr')[1:]
    
    for tr in filas_html:
        tds = tr.find_all(['td', 'th'])
        if len(tds) < 3: continue
        
        nombre_bruto = tds[idx_jugador].get_text(strip=True)
        if not nombre_bruto or nombre_bruto.lower() == 'jugador': continue
        
        nombre_limpio = separar_nombre_repetido(nombre_bruto)
        clave = normalizar(nombre_limpio)
        
        equipo = tds[idx_equipo].get_text(strip=True) if idx_equipo != -1 and len(tds) > idx_equipo else "Desconocido"
        posicion = tds[idx_pos].get_text(strip=True) if idx_pos != -1 and len(tds) > idx_pos else "Desc"
        
        # Puntos totales
        ptos_texto = tds[idx_puntos].get_text(strip=True) if idx_puntos != -1 and len(tds) > idx_puntos else "0"
        puntos_totales = int(ptos_texto) if re.match(r'^-?\d+$', ptos_texto) else 0
        
        datos_jugador = {
            "clave": clave,
            "Jugador": nombre_limpio,
            "Equipo": equipo,
            "Posicion": posicion,
            "Puntos": puntos_totales
        }
        
        # Puntos por cada jornada (J1, J2, J3...)
        for j_nombre, j_idx in idx_jornadas.items():
            if len(tds) > j_idx:
                p = tds[j_idx].get_text(strip=True)
                datos_jugador[j_nombre] = int(p) if re.match(r'^-?\d+$', p) else 0
            else:
                datos_jugador[j_nombre] = 0
                
        filas.append(datos_jugador)
        
    df = pd.DataFrame(filas)
    lista_jornadas = list(idx_jornadas.keys())
    return df, lista_jornadas


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

        # Cruce maestro de tablas
        df_hoy = df_puntos.merge(df_mercado, on="clave", how="left")
        df_hoy = df_hoy.merge(df_lesionados, on="clave", how="left")
        
        # Configuración final de valores
        df_hoy["Estado"] = df_hoy["Estado"].fillna("Disponible")
        df_hoy = df_hoy.dropna(subset=["Valor"])
        df_hoy["Valor"] = df_hoy["Valor"].astype(int)
        df_hoy["Valor_Anterior"] = df_hoy["Valor_Anterior"].fillna(0).astype(int)

        # ORDEN DE LAS COLUMNAS EXACTO: Jugador, Equipo, Posición, Puntos, J1, J2..., Valor, Valor Ant, Estado, Fecha
        columnas_finales = ["Jugador", "Equipo", "Posicion", "Puntos"] + lista_jornadas + ["Valor", "Valor_Anterior", "Estado", "Fecha"]
        
        fecha_hoy = datetime.today().strftime("%Y-%m-%d")
        df_hoy["Fecha"] = fecha_hoy
        df_hoy = df_hoy[columnas_finales]

        archivo_csv = "historico_fantasy.csv"
        
        if os.path.exists(archivo_csv):
            df_existente = pd.read_csv(archivo_csv)
            # Detecta si el CSV viejo no tiene la columna "Equipo" o "Posicion"
            if not {"Equipo", "Posicion"}.issubset(df_existente.columns):
                print("🔄 Formato de CSV antiguo detectado. Regenerando desde cero con la nueva estructura...")
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

        # Asegurar el orden visual perfecto en el CSV
        df_final = df_final[columnas_finales]

        df_final.to_csv(archivo_csv, index=False, encoding="utf-8-sig")
        print(f"✅ ¡ÉXITO! Se guardaron {len(df_hoy)} jugadores.")
        print(f"ℹ️ Jornadas detectadas: {', '.join(lista_jornadas)}")
        print(df_hoy.head(3))

    except Exception as e:
        print(f"❌ Error: {e}")
        raise e
