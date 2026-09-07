import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import os

def extraer_datos():
    url = "https://www.futbolfantasy.com/laliga/puntos/laliga-fantasy"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"Error HTTP {resp.status_code}")

    # Método 1: Intentar lectura directa de tablas mediante pandas
    try:
        tablas = pd.read_html(resp.text)
        for t in tablas:
            if len(t) > 5 and len(t.columns) >= 4:
                return t
    except Exception:
        pass

    # Método 2: Extracción manual directa sin depender de 'tbody'
    soup = BeautifulSoup(resp.text, 'html.parser')
    filas = soup.find_all("tr")
    
    jugadores = []
    for fila in filas:
        cols = fila.find_all(["td", "th"])
        if len(cols) >= 4:
            nombre = cols[0].get_text(strip=True)
            equipo = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            posicion = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            puntos = cols[3].get_text(strip=True) if len(cols) > 3 else "0"
            precio = cols[4].get_text(strip=True) if len(cols) > 4 else "0"
            
            # Filtrar filas vacías o cabeceras repetidas
            if nombre and nombre.lower() not in ["jugador", "nombre", "columna1"]:
                jugadores.append({
                    "Jugador": nombre,
                    "Equipo": equipo,
                    "Posicion": posicion,
                    "Puntos": puntos,
                    "Precio": precio
                })
                
    df = pd.DataFrame(jugadores)
    if df.empty:
        raise Exception("No se pudieron extraer las filas de jugadores.")
    return df

if __name__ == "__main__":
    try:
        print("Obteniendo datos de Fútbol Fantasy...")
        df_hoy = extraer_datos()
        
        # Asignar la fecha del día
        df_hoy['Fecha'] = datetime.today().strftime('%Y-%m-%d')
        
        archivo_csv = 'historico_fantasy.csv'
        
        # Si existe el CSV previo pero estaba incompleto (sin columna Jugador), se sobrescribe
        if os.path.exists(archivo_csv):
            df_existente = pd.read_csv(archivo_csv)
            if 'Jugador' not in df_existente.columns:
                df_final = df_hoy
            else:
                df_final = pd.concat([df_existente, df_hoy], ignore_index=True)
        else:
            df_final = df_hoy
            
        df_final.to_csv(archivo_csv, index=False, encoding='utf-8-sig')
        print(f"✅ Se han procesado {len(df_hoy)} filas de jugadores con éxito.")
        
    except Exception as e:
        print(f"❌ Error al ejecutar el scraper: {e}")
        raise e
