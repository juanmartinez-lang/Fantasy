import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import os
import re

def limpiar_precio(val):
    """Convierte un texto como '15.000.000 €' a un número entero 15000000."""
    if pd.isna(val):
        return 0
    # Eliminar cualquier carácter que no sea un número
    numeros = re.sub(r'[^\d]', '', str(val))
    return int(numeros) if numeros else 0

def extraer_datos():
    url = "https://www.futbolfantasy.com/laliga/puntos/laliga-fantasy"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"Error HTTP {resp.status_code}")

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
            
            if nombre and nombre.lower() not in ["jugador", "nombre", "columna1"]:
                jugadores.append({
                    "Jugador": nombre,
                    "Equipo": equipo,
                    "Posicion": posicion,
                    "Puntos": limpiar_precio(puntos),
                    "Precio": limpiar_precio(precio_raw)
                })
                
    df = pd.DataFrame(jugadores)
    if df.empty:
        raise Exception("No se pudieron extraer filas.")
    return df

if __name__ == "__main__":
    try:
        print("Obteniendo datos de Fútbol Fantasy...")
        df_hoy = extraer_datos()
        fecha_hoy = datetime.today().strftime('%Y-%m-%d')
        df_hoy['Fecha'] = fecha_hoy
        
        archivo_csv = 'historico_fantasy.csv'
        
        if os.path.exists(archivo_csv):
            df_existente = pd.read_csv(archivo_csv)
            
            # Obtener el último día registrado en el CSV
            fechas_previas = df_existente['Fecha'].unique()
            if len(fechas_previas) > 0:
                ultima_fecha = max(fechas_previas)
                df_ayer = df_existente[df_existente['Fecha'] == ultima_fecha]
                
                # Unir los precios de ayer para calcular la variación
                precios_ayer = df_ayer.set_index('Jugador')['Precio'].to_dict()
                
                def calc_variacion(row):
                    precio_ayer = precios_ayer.get(row['Jugador'])
                    if precio_ayer is not None and precio_ayer > 0:
                        return row['Precio'] - precio_ayer
                    return 0 # Si es el primer día o jugador nuevo
                
                df_hoy['Variacion_Precio'] = df_hoy.apply(calc_variacion, axis=1)
            else:
                df_hoy['Variacion_Precio'] = 0
                
            # Eliminar datos de hoy si ya se habían guardado antes para no duplicar
            df_existente = df_existente[df_existente['Fecha'] != fecha_hoy]
            df_final = pd.concat([df_existente, df_hoy], ignore_index=True)
        else:
            df_hoy['Variacion_Precio'] = 0
            df_final = df_hoy
            
        # Determinar la tendencia (Sube, Baja, Mantiene)
        def calcular_tendencia(var):
            if var > 0:
                return 'Sube'
            elif var < 0:
                return 'Baja'
            else:
                return 'Mantiene'
                
        df_final['Tendencia'] = df_final['Variacion_Precio'].apply(calcular_tendencia)
        
        df_final.to_csv(archivo_csv, index=False, encoding='utf-8-sig')
        print(f"✅ Se han procesado {len(df_hoy)} jugadores con variaciones calculadas.")
        
    except Exception as e:
        print(f"❌ Error al ejecutar el script: {e}")
        raise e
