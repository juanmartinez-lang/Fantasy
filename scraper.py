import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import os
import re

def limpiar_precio(val):
    """Convierte un texto como '15.000.000 €' en un número entero 15000000."""
    if pd.isna(val):
        return 0
    numeros = re.sub(r'[^\d]', '', str(val))
    return int(numeros) if numeros else 0

def extraer_datos():
    url = "https://www.futbolfantasy.com/laliga/puntos/laliga-fantasy"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/"
    }
    
    session = requests.Session()
    resp = session.get(url, headers=headers, timeout=15)
    
    if resp.status_code != 200:
        raise Exception(f"Error HTTP {resp.status_code} al conectar con la web.")

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
            precio_raw = cols[4].get_text(strip=True) if len(cols) > 4 else "0"
            
            if nombre and nombre.lower() not in ["jugador", "nombre", "columna1", "pos", "pts"]:
                jugadores.append({
                    "Jugador": nombre,
                    "Equipo": equipo,
                    "Posicion": posicion,
                    "Puntos": limpiar_precio(puntos),
                    "Precio": limpiar_precio(precio_raw)
                })
                
    df = pd.DataFrame(jugadores)
    if df.empty:
        raise Exception("No se encontraron datos de jugadores en la página.")
    return df

if __name__ == "__main__":
    try:
        print("Obteniendo datos de Fútbol Fantasy...")
        df_hoy = extraer_datos()
        fecha_hoy = datetime.today().strftime('%Y-%m-%d')
        df_hoy['Fecha'] = fecha_hoy
        
        archivo_csv = 'historico_fantasy.csv'
        df_existente = None
        
        # Validar si el CSV existente tiene la estructura correcta
        if os.path.exists(archivo_csv):
            try:
                temp_df = pd.read_csv(archivo_csv)
                columnas_requeridas = {'Jugador', 'Fecha', 'Precio'}
                if columnas_requeridas.issubset(temp_df.columns):
                    df_existente = temp_df
                else:
                    print("⚠️ CSV previo no compatible. Recreando archivo...")
            except Exception:
                print("⚠️ No se pudo leer el CSV previo. Recreando archivo...")

        # Procesar variaciones de precio
        if df_existente is not None and not df_existente.empty:
            fechas_previas = df_existente['Fecha'].unique()
            if len(fechas_previas) > 0:
                ultima_fecha = max(fechas_previas)
                df_ayer = df_existente[df_existente['Fecha'] == ultima_fecha]
                precios_ayer = df_ayer.set_index('Jugador')['Precio'].to_dict()
                
                def calc_variacion(row):
                    precio_ayer = precios_ayer.get(row['Jugador'])
                    if precio_ayer is not None and precio_ayer > 0:
                        return row['Precio'] - precio_ayer
                    return 0
                
                df_hoy['Variacion_Precio'] = df_hoy.apply(calc_variacion, axis=1)
            else:
                df_hoy['Variacion_Precio'] = 0
            
            df_existente = df_existente[df_existente['Fecha'] != fecha_hoy]
            df_final = pd.concat([df_existente, df_hoy], ignore_index=True)
        else:
            df_hoy['Variacion_Precio'] = 0
            df_final = df_hoy

        # Determinar tendencia
        def calcular_tendencia(var):
            if var > 0:
                return 'Sube'
            elif var < 0:
                return 'Baja'
            else:
                return 'Mantiene'

        df_final['Tendencia'] = df_final['Variacion_Precio'].apply(calcular_tendencia)
        df_final.to_csv(archivo_csv, index=False, encoding='utf-8-sig')
        print(f"✅ Proceso completado exitosamente. {len(df_hoy)} jugadores procesados.")

    except Exception as e:
        print(f"❌ Error durante la ejecución: {e}")
        raise e
