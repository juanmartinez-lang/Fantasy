import pandas as pd
from datetime import datetime
import os
import requests

def extraer_datos_fantasy():
    # Usamos la API abierta de Mister Fantasy / alternativas sin Cloudflare
    # que comparten la base de datos de precios oficiales de LaLiga
    url = "https://raw.githubusercontent.com/jmalonsom/biwenger-api/master/data/players.json"
    
    # NOTA: Aunque la URL pone 'biwenger-api', muchos de estos repositorios unifican las IDs 
    # y valores. Para tener los datos de LALIGA FANTASY (RELEVO) exactos sin bloqueos, 
    # la mejor alternativa es descargar un CSV público diario mantenido por la comunidad.
    
    # URL de un repositorio comunitario que actualiza el mercado de LaLiga Fantasy Oficial
    url_csv_comunidad = "https://raw.githubusercontent.com/wito-j/Fantasy-Scraper/main/data/market.csv"
    
    try:
        print("Intentando descargar datos desde fuente comunitaria abierta...")
        # Pandas puede leer directamente un CSV desde una URL de GitHub sin ser bloqueado
        df = pd.read_csv(url_csv_comunidad)
        
        # Adaptar las columnas si el CSV tiene nombres distintos
        # Suelen venir como 'Name', 'Team', 'Points', 'Price'
        if 'Name' in df.columns:
            df = df.rename(columns={'Name': 'Jugador', 'Team': 'Equipo', 'Points': 'Puntos', 'Price': 'Precio'})
            
        # Asegurarnos de que tenemos las columnas mínimas
        if not {'Jugador', 'Precio', 'Puntos'}.issubset(df.columns):
            raise Exception("El formato del archivo comunitario no es el esperado.")
            
        # Si no hay columna de Posición o Equipo, las rellenamos para que Power BI no falle
        if 'Posicion' not in df.columns:
            df['Posicion'] = 'Desconocida'
        if 'Equipo' not in df.columns:
            df['Equipo'] = 'Desconocido'
            
        df = df[['Jugador', 'Equipo', 'Posicion', 'Puntos', 'Precio']]
        
        # Limpieza básica
        df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0).astype(int)
        df['Puntos'] = pd.to_numeric(df['Puntos'], errors='coerce').fillna(0).astype(int)
        
        # Quitar valores a 0
        df = df[df['Precio'] > 0]
        
        return df
        
    except Exception as e:
        print(f"La fuente principal falló: {e}")
        raise e

if __name__ == "__main__":
    try:
        print("Iniciando extracción de datos...")
        df_hoy = extraer_datos_fantasy()
        
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
                print(f"Aviso leyendo CSV: {e}")
                
        # Calcular variaciones
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
        print(f"✅ ¡ÉXITO! Base de datos actualizada con {len(df_hoy)} jugadores.")
        
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        raise e
