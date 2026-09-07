import pandas as pd
from datetime import datetime
import os
import time

# Librerías de Selenium para navegación web real
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

def extraer_datos_fantasy():
    print("Iniciando navegador invisible...")
    
    # Configurar Chrome para que se ejecute en segundo plano en GitHub
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Instalar y abrir el navegador
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # URL de Fútbol Fantasy para LaLiga Fantasy
    url = "https://www.futbolfantasy.com/laliga/puntos/laliga-fantasy"
    
    try:
        print("Entrando a la página de Fútbol Fantasy...")
        driver.get(url)
        
        # Esperar 5 segundos para asegurar que la tabla carga completamente y sortear bloqueos
        time.sleep(5)
        
        # Extraer el código HTML que ya ha procesado el navegador real
        html = driver.page_source
        
        print("HTML obtenido, buscando la tabla...")
        # Pandas lee el HTML extraído por Selenium
        tablas = pd.read_html(html)
        
        # Buscar la tabla que contenga "Jugador" (suele ser la principal)
        df_objetivo = None
        for tabla in tablas:
            if 'Jugador' in tabla.columns or (len(tabla.columns) >= 4 and 'Jugador' in str(tabla.iloc[0].values).title()):
                df_objetivo = tabla
                break
                
        if df_objetivo is None and len(tablas) > 0:
            df_objetivo = tablas[0] # Si no la encuentra claramente, coge la primera
            
        if df_objetivo is None:
            raise Exception("No se encontró ninguna tabla en el HTML procesado.")
            
        df = df_objetivo
        
        # Estandarizar columnas asumiendo el orden clásico: Jugador, Equipo, Posición, Puntos, Precio
        if len(df.columns) >= 5:
            df.columns = ['Jugador', 'Equipo', 'Posicion', 'Puntos', 'Precio'] + list(df.columns[5:])
            df = df[['Jugador', 'Equipo', 'Posicion', 'Puntos', 'Precio']]
            
            # Limpiar Precio (quitar símbolos de euro y puntos)
            df['Precio'] = df['Precio'].astype(str).str.replace(r'[^\d]', '', regex=True)
            df['Precio'] = pd.to_numeric(df['Precio'], errors='coerce').fillna(0).astype(int)
            
            # Limpiar Puntos
            df['Puntos'] = pd.to_numeric(df['Puntos'], errors='coerce').fillna(0).astype(int)
            
            # Quitar filas que no sean jugadores reales
            df = df[df['Precio'] > 0]
            
            return df
        else:
            raise Exception(f"La tabla no tiene las 5 columnas esperadas. Columnas detectadas: {df.columns}")
            
    except Exception as e:
        print(f"Error en Selenium: {e}")
        raise e
    finally:
        # Cerrar el navegador siempre para liberar recursos
        driver.quit()

if __name__ == "__main__":
    try:
        print("Iniciando extracción de LaLiga Fantasy...")
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
        print(f"✅ ¡ÉXITO! Base de datos de LaLiga Fantasy actualizada con {len(df_hoy)} jugadores.")
        
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        raise e
