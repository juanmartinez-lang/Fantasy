import pandas as pd
from datetime import datetime
import os

def extraer_datos():
    # Usamos pandas para extraer la tabla de mercado directamente
    url = "https://www.comuniate.com/mercado/laliga"
    
    try:
        # Pandas buscará automáticamente las tablas en el HTML de la web
        tablas = pd.read_html(url, flavor='lxml')
        
        # Seleccionamos la tabla principal
        if tablas:
            df = tablas[0]
            
            # Renombramos las columnas si es necesario para adaptarlas a nuestro modelo
            columnas_detectadas = list(df.columns)
            
            # Comuniate suele tener las columnas: Jugador, Equipo, Precio, Variación, etc.
            # Vamos a asegurar que haya al menos las básicas
            if len(columnas_detectadas) >= 3:
                # Estandarizamos los nombres de la tabla extraída (la primera columna suele ser jugador)
                df.columns = ['Jugador', 'Equipo', 'Precio', 'Var_Hoy', 'Puntos', 'Media'] + list(df.columns[6:])
                
                # Seleccionamos solo las que nos importan
                df = df[['Jugador', 'Equipo', 'Precio', 'Puntos']]
                
                # Limpiamos el texto para asegurar que no haya símbolos y convertir a números
                df['Precio'] = df['Precio'].astype(str).str.replace(r'[^\d]', '', regex=True)
                df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0).astype(int)
                
                df['Puntos'] = pd.to_numeric(df['Puntos'], errors='coerce').fillna(0).astype(int)
                
                return df
            else:
                raise Exception("La tabla extraída no tiene suficientes columnas.")
        else:
            raise Exception("No se encontraron tablas en la web.")
    except Exception as e:
        print(f"Intento con read_html fallido: {e}")
        raise e

if __name__ == "__main__":
    try:
        print("Obteniendo datos de mercado...")
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
                
            # No duplicar los del mismo día
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
        
        # Guardar archivo
        df_final.to_csv(archivo_csv, index=False, encoding='utf-8-sig')
        print(f"✅ Proceso completado: {len(df_hoy)} jugadores.")
        
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        raise e
