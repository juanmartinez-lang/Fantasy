import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import os
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

URL_PUNTOS = "https://www.futbolfantasy.com/laliga/estadisticas-puntos/jugador"
URL_MERCADO = "https://www.futbolfantasy.com/analytics/laliga-fantasy/mercado"
URL_LESIONADOS = "https://www.futbolfantasy.com/laliga/lesionados"

def extraer_id(href):
    """Extrae el ID único del jugador desde su URL (ej: 'antonio-sivera')."""
    if href:
        match = re.search(r'/jugadores/([^/]+)', href)
        if match:
            return match.group(1).lower()
    return None

def extraer_numero(texto):
    """Busca el primer bloque numérico en un texto (ej: '42.294.959' -> 42294959)."""
    nums = re.findall(r"\d{1,3}(?:\.\d{3})*", str(texto))
    return int(nums[0].replace(".", "")) if nums else None


def obtener_puntos():
    print("Descargando puntos e IDs por jugador...")
    r = requests.get(URL_PUNTOS, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    filas = []

    for tr in soup.find_all("tr"):
        enlace = tr.find("a", href=re.compile(r"/jugadores/"))
        if not enlace:
            continue
            
        jugador_id = extraer_id(enlace.get("href"))
        nombre = enlace.get_text(strip=True)
        
        # Los puntos suelen estar en la última columna de la fila
        tds = tr.find_all("td")
        if tds:
            ptos_texto = tds[-1].get_text(strip=True)
            puntos = int(ptos_texto) if ptos_texto.isdigit() else 0
            filas.append({"ID": jugador_id, "Jugador": nombre, "Puntos": puntos})

    return pd.DataFrame(filas).drop_duplicates(subset=["ID"])


def obtener_mercado():
    print("Descargando mercado (Valor actual y anterior)...")
    r = requests.get(URL_MERCADO, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    filas = []

    for tr in soup.find_all("tr"):
        enlace = tr.find("a", href=re.compile(r"/jugadores/"))
        if not enlace:
            continue
            
        jugador_id = extraer_id(enlace.get("href"))
        tds = tr.find_all("td")
        
        if len(tds) >= 8:
            # En Fútbol Fantasy, la penúltima columna es "Valor" y la última es "Valor Ant."
            celda_valor_actual = tds[-2].get_text(strip=True)
            celda_valor_anterior = tds[-1].get_text(strip=True)
            
            valor_actual = extraer_numero(celda_valor_actual)
            valor_anterior = extraer_numero(celda_valor_anterior)
            
            filas.append({
                "ID": jugador_id, 
                "Valor": valor_actual, 
                "Valor_Anterior": valor_anterior
            })

    return pd.DataFrame(filas).drop_duplicates(subset=["ID"])


def obtener_lesionados():
    print("Descargando estado de los jugadores...")
    r = requests.get(URL_LESIONADOS, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    filas = []

    for enlace in soup.select('a[href*="/jugadores/"]'):
        jugador_id = extraer_id(enlace.get("href"))
        if not jugador_id:
            continue
            
        estado = "Lesionado"
        img = enlace.find_parent().find_previous("img", src=re.compile(r"(lesionado|duda|disponible)_box"))
        if img and img.get("src"):
            if "duda" in img["src"]:
                estado = "Duda"
            elif "disponible" in img["src"]:
                estado = "Disponible"
                
        filas.append({"ID": jugador_id, "Estado": estado})

    return pd.DataFrame(filas).drop_duplicates(subset=["ID"])


if __name__ == "__main__":
    try:
        df_puntos = obtener_puntos()
        df_mercado = obtener_mercado()
        df_lesionados = obtener_lesionados()

        # CRUCE ABSOLUTAMENTE PRECISO USANDO EL ID DE LA URL
        df_hoy = df_puntos.merge(df_mercado, on="ID", how="left")
        df_hoy = df_hoy.merge(df_lesionados, on="ID", how="left")
        
        # Rellenamos los que no aparecen en la lista de lesiones como "Disponible"
        df_hoy["Estado"] = df_hoy["Estado"].fillna("Disponible")
        
        # Filtramos para quedarnos solo con las columnas que has pedido
        df_hoy = df_hoy[["ID", "Jugador", "Puntos", "Valor", "Valor_Anterior", "Estado"]]
        
        # Limpieza de filas que no tengan un Valor registrado
        df_hoy = df_hoy.dropna(subset=["Valor"])
        
        # Convertimos los valores a números enteros (quitando decimales residuales de pandas)
        df_hoy["Valor"] = df_hoy["Valor"].astype(int)
        if df_hoy["Valor_Anterior"].notna().any():
            df_hoy["Valor_Anterior"] = df_hoy["Valor_Anterior"].fillna(0).astype(int)

        fecha_hoy = datetime.today().strftime("%Y-%m-%d")
        df_hoy["Fecha"] = fecha_hoy

        # Guardado del CSV
        archivo_csv = "historico_fantasy.csv"
        if os.path.exists(archivo_csv):
            df_existente = pd.read_csv(archivo_csv)
            # Evitar duplicar datos si se ejecuta varias veces el mismo día
            df_existente = df_existente[df_existente["Fecha"] != fecha_hoy]
            df_final = pd.concat([df_existente, df_hoy], ignore_index=True)
        else:
            df_final = df_hoy

        df_final.to_csv(archivo_csv, index=False, encoding="utf-8-sig")
        
        print(f"✅ ¡ÉXITO! Base de datos actualizada y cruzada por ID. Se guardaron {len(df_hoy)} jugadores.")
        print(df_hoy.head(10))

    except Exception as e:
        print(f"❌ Error crítico: {e}")
        raise e
