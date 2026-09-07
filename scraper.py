import undetected_chromedriver as uc
import pandas as pd
from datetime import datetime
import os
import time
from io import StringIO

def extraer_datos_laliga_fantasy():
    url = "https://www.futbolfantasy.com/laliga/puntos/laliga-fantasy"
    print("Iniciando navegador indetectable (Chrome) para ejecutar JavaScript...")
    
    # Configurar Chrome para ejecutarse de forma invisible en GitHub Actions
    options = uc.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = uc.Chrome(options=options)
    
    try:
        driver.get(url)
        print("Página web cargada. Esperando 12 segundos a que el JavaScript dibuje la tabla...")
        time.sleep(12)  # Pausa obligatoria para que aparezcan los datos
        
        html = driver.page_source
        print("Código HTML procesado capturado. Extrayendo tabla...")
        
        try:
            tablas = pd.read_html(StringIO(html))
        except Exception as e:
            raise Exception(f"No se detectaron tablas ni siquiera tras renderizar JS: {e}")
            
        df_objetivo = None
        for t in tablas:
            # Buscamos la tabla que tenga más de 10 filas (jugadores) y 4 columnas
            if len(t) > 10 and len(t.columns) >= 4:
                df_objetivo = t.copy()
                break
                
        if df_objetivo is None:
            raise Exception("Se encontraron tablas, pero ninguna coincide con la lista de jugadores.")
            
        df = df_objetivo
        
        # Estructurar las columnas
        if len(df.columns) >= 5:
            df.columns = ['Jugador', 'Equipo', 'Posicion', 'Puntos', 'Precio'] + list(df.columns[5:])
        else:
            df.columns = ['Jugador', 'Equipo', 'Puntos', 'Precio'] + list(df.columns[4:])
            df['Posicion'] = 'Desconocida'
        
        # Limpiar los textos para extraer solo números enteros
        df['Precio'] = df['Precio'].astype(str).str.replace(r'[^\d]', '', regex=True)
        df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0).astype(int)
        df['Puntos'] = pd.to_numeric(df['Puntos'], errors='coerce').fillna(0).astype(int)
        
        df = df[['Jugador', 'Equipo', 'Posicion', 'Puntos', 'Precio']]
        df = df[df['Precio'] > 0]
        
        return df
        
    finally:
        # Es vital cerrar el navegador al terminar para que el Action no se quede colgado
        driver.quit()

if __name__ == "__main__":
    try:
        print("Obteniendo datos reales de LaLiga Fantasy (Relevo)...")
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
                
        # Calcular variación de precio respecto al último día registrado
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
