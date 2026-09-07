import pandas as pd
from datetime import datetime
import os
import requests
from io import StringIO

def extraer_datos():
    url = "https://www.comuniate.com/mercado/laliga"
    
    # Cabecera para simular un navegador real y evitar el bloqueo 403
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # 1. Descargamos el HTML con requests usando la cabecera
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            raise Exception(f"Error HTTP {response.status_code} al conectar con Comuniate")
            
        # 2. Leemos la tabla del HTML usando StringIO
        tablas = pd.read_html(StringIO(response.text), flavor='lxml')
        
        if tablas:
            df = tablas[0]
            
            # Renombramos las columnas principales
            if len(df.columns) >= 4:
                df.columns = ['Jugador', 'Equipo', 'Precio', 'Puntos'] + list(df.columns[4:])
                df = df[['Jugador', 'Equipo', 'Precio', 'Puntos']].copy()
                
                # Limpiamos los números
                df['Precio'] = df['Precio'].astype(str).str.replace(r'[^\d]', '', regex=True)
                df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0).astype(int)
                
                df['Puntos'] = pd.to_numeric(df['Puntos'], errors='coerce').fillna(0).astype(int)
                
                # Descartamos filas vacías
                df = df[df['Precio'] > 0]
                
                return df
            else:
                raise Exception("La tabla no tiene la estructura esperada.")
        else:
            raise Exception("No se encontraron tablas en la web.")
    except Exception as e:
        print(f"Error en la extracción: {e}")
        raise e

if __name__ == "__main__":
    try:
        print("Obteniendo datos de mercado de Comuniate...")
        df_hoy = extraer_datos()
        
        fecha_hoy = datetime.today().strftime('%Y-%m-%d')
        df_hoy['Fecha'] = fecha_hoy
        
        archivo_csv = 'historico_fantasy.csv'
        df_existente = None
        
        if os.path.exists(archivo_csv):
            try:
                temp_df = pd.read_csv(archivo_csv)
                if {'Jugador', 'Fecha', 'Precio'}.issubset(temp_df.columns):
                    df_existente = temp_df
            except:
                pass
                
        # Cálculo de variaciones
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
        print(f"✅ Proceso completado: {len(df_hoy)} jugadores procesados.")
        
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        raise e
