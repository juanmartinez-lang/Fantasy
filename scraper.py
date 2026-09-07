import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import os

def extraer_datos_futbol_fantasy():
    url = "https://www.futbolfantasy.com/laliga/puntos/laliga-fantasy"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    respuesta = requests.get(url, headers=headers)
    if respuesta.status_code != 200:
        raise Exception(f"Error en la petición: Código {respuesta.status_code}")
        
    soup = BeautifulSoup(respuesta.text, 'html.parser')
    filas = soup.select("table tbody tr")
    
    jugadores = []
    for fila in filas:
        cols = fila.find_all("td")
        if len(cols) >= 4:
            nombre = cols[0].get_text(strip=True)
            equipo = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            posicion = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            puntos = cols[3].get_text(strip=True) if len(cols) > 3 else "0"
            precio = cols[4].get_text(strip=True) if len(cols) > 4 else "0"
            
            jugadores.append({
                "Jugador": nombre,
                "Equipo": equipo,
                "Posicion": posicion,
                "Puntos": puntos,
                "Precio": precio
            })
            
    return pd.DataFrame(jugadores)

if __name__ == "__main__":
    try:
        print("Conectando con Fútbol Fantasy...")
        df_hoy = extraer_datos_futbol_fantasy()
        df_hoy['Fecha'] = datetime.today().strftime('%Y-%m-%d')
        
        archivo_csv = 'historico_fantasy.csv'
        
        if os.path.exists(archivo_csv):
            df_existente = pd.read_csv(archivo_csv)
            df_final = pd.concat([df_existente, df_hoy], ignore_index=True)
            df_final.to_csv(archivo_csv, index=False, encoding='utf-8-sig')
        else:
            df_hoy.to_csv(archivo_csv, index=False, encoding='utf-8-sig')
            
        print(f"✅ Se han procesado {len(df_hoy)} jugadores correctamente.")
        
    except Exception as e:
        print(f"❌ Error al ejecutar el script: {e}")
