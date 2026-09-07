import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import os
import re
from io import StringIO

def extraer_datos_laliga_fantasy():
    url = "https://www.futbolfantasy.com/laliga/puntos/laliga-fantasy"
    print("Iniciando conexión con bypass de Cloudflare...")
    
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
    )
    
    resp = scraper.get(url, timeout=20)
    if resp.status_code != 200:
        raise Exception(f"Error HTTP {resp.status_code} al conectar con Fútbol Fantasy.")
    
    # Intento 1: Lectura directa de tablas HTML con Pandas
    try:
        tablas = pd.read_html(StringIO(resp.text))
        for t in tablas:
            if len(t) > 10 and len(t.columns) >= 4:
                df_temp = t.copy()
                if len(df_temp.columns) >= 5:
                    df_temp.columns = ['Jugador', 'Equipo', 'Posicion', 'Puntos', 'Precio'] + list(df_temp.columns[5:])
                else:
                    df_temp.columns = ['Jugador', 'Equipo', 'Puntos', 'Precio'] + list(df_temp.columns[4:])
                    df_temp['Posicion'] = 'Desconocida'
                
                # Limpiar texto a números
                df_temp['Precio'] = df_temp['Precio'].astype(str).str.replace(r'[^\d]', '', regex=True)
                df_temp['Precio'] = pd.to_numeric(df_temp['Precio'], errors='coerce').fillna(0).astype(int)
                df_temp['Puntos'] = pd.to_numeric(df_temp['Puntos'], errors='coerce').fillna(0).astype(int)
                
                df_temp = df_temp[['Jugador', 'Equipo', 'Posicion', 'Puntos', 'Precio']]
                df_temp = df_temp[df_temp['Precio'] > 0]
                
                if len(df_temp) > 10:
                    print(f"✅ Extraídos {len(df_temp)} jugadores vía read_html.")
                    return df_temp
    except Exception as e:
        print(f"Aviso en Intento 1 (read_html): {e}")

    # Intento 2: Parseo manual de filas tr/td con BeautifulSoup
    soup = BeautifulSoup(resp.text, 'html.parser')
    filas = soup.find_all("tr")
    
    jugadores = []
    for fila in filas:
        cols = fila.find_all(["td", "th"])
        if len(cols) >= 4:
            nombre = cols[0].get_text(strip=True)
            equipo = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            posicion = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            puntos_raw = cols[3].get_text(strip=True) if len(cols) > 3 else "0"
            precio_raw = cols[4].get_text(strip=True) if len(cols) > 4 else "0"
            
            if nombre and nombre.lower() not in ["jugador", "nombre", "columna1", "pos", "pts", "puntos"]:
                num_precio = re.sub(r'[^\d]', '', str(precio_raw))
                num_puntos = re.sub(r'[^\d]', '', str(puntos_raw))
                
                precio = int(num_precio) if num_precio else 0
                puntos = int(num_puntos) if num_puntos else 0
                
                if precio > 0 or puntos > 0:
                    jugadores.append({
                        "Jugador": nombre,
                        "Equipo": equipo,
                        "Posicion": posicion,
                        "Puntos": puntos,
                        "Precio": precio
                    })
                    
    # Definición explícita de columnas para evitar KeyError
    df = pd.DataFrame(jugadores, columns=["Jugador", "Equipo", "Posicion", "Puntos", "Precio"])
    df = df[df['Precio'] > 0]
    
    if df.empty:
        raise Exception("No se pudieron extraer datos de la tabla (DataFrame vacío).")
        
    return df

if __name__ == "__main__":
    try:
        print("Obteniendo datos reales de LaLiga Fantasy...")
        df_hoy = extraer_datos_laliga_fantasy()
        
        fecha_hoy = datetime.today().strftime('%Y-%m-%d')
        df_hoy['Fecha'] = fecha_hoy
        
        archivo_csv = 'historico_fantasy.csv'
        df_existente = None
        
        if os.path.exists(archivo_csv):
            try:
                temp_df = pd.read_csv(archivo_csv)
                if {'Jugador', 'Fecha', 'Precio'}.issubset(temp_df.columns):
                    df_existente = temp_df
            except Exception as e:
                print(f"Aviso al leer CSV previo: {e}")
                
        # Calcular variación respecto al día anterior
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
            
        def calcular_tendencia(var):
            if var > 0: return 'Sube'
            elif var < 0: return 'Baja'
            else: return 'Mantiene'
            
        df_final['Tendencia'] = df_final['Variacion_Precio'].apply(calcular_tendencia)
        
        df_final.to_csv(archivo_csv, index=False, encoding='utf-8-sig')
        print(f"✅ ¡ÉXITO! Base de datos actualizada con {len(df_hoy)} jugadores de LaLiga Fantasy.")
        
    except Exception as e:
        print(f"❌ Error durante el proceso: {e}")
        raise e
