import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

# =====================================================================
# 1. CONFIGURACIÓN
# =====================================================================
CARPETA_ENTRADA = Path("txt_filtrados")
ARCHIVO_ESCANEOS      = Path("escaneos.csv")
ARCHIVO_FINGERPRINT   = Path("fingerprint.csv")
ARCHIVO_PREDICCIONES  = Path("predicciones_knn.csv")

UMBRAL_NUEVO_ESCANEO_MS = 1000
RSSI_AUSENTE = -100
EDAD_MAX_S = 3.0

# BSSID -> (Salón, Red, Banda)
BSSID_VALIDOS = {
    "a4:88:73:40:c8:c0": ("301",   "wifi_compu", "2.4"),
    "30:b5:c2:ef:3e:f0": ("301",   "ACM",        "2.4"),
    "70:0b:01:ef:f6:26": ("301",   "sc-f620",    "2.4"),
    "a4:88:73:40:a4:00": ("Lab 3", "wifi_compu", "2.4"),
    "fc:5a:1d:7e:0e:48": ("Lab 3", "Movistar",   "2.4"),
    "a4:88:73:40:b7:a0": ("Lab 4", "wifi_compu", "5.0"),
    "98:97:d1:93:e6:52": ("Lab 4", "WLAN_E650",  "2.4"),
}

ORDEN_SALONES = ["301", "Lab 3", "Lab 4"]

# =====================================================================
# 2. DEFINICIÓN DE COORDENADAS (X, Y)
# =====================================================================
# Asignamos un sistema cartesiano:
# X = Columna (1, 2, 3) -> Puedes multiplicarlo por 5 si quieres metros
# Y = Fila (10, 11, 12, pasillo=9)
# (Columna, Fila) -> X, Y
PLANO = {
    # Interior (Fila 12 = Y=12, Fila 11 = Y=11, Fila 10 = Y=10)
    1:  {"x": 1, "y": 12, "zona": "interior"},
    2:  {"x": 2, "y": 12, "zona": "interior"},
    3:  {"x": 3, "y": 12, "zona": "interior"},
    4:  {"x": 1, "y": 11, "zona": "interior"},
    5:  {"x": 2, "y": 11, "zona": "interior"},
    6:  {"x": 3, "y": 11, "zona": "interior"},
    7:  {"x": 1, "y": 10, "zona": "interior"},
    8:  {"x": 2, "y": 10, "zona": "interior"},
    9:  {"x": 3, "y": 10, "zona": "interior"},
    
    # Pasillo (al frente del salón, Y=9)
    12: {"x": 1, "y": 9, "zona": "pasillo"},
    11: {"x": 2, "y": 9, "zona": "pasillo"},
    10: {"x": 3, "y": 9, "zona": "pasillo"},
}

# =====================================================================
# 3. UTILIDADES Y LECTURA
# =====================================================================
def separar_ubicacion(texto: str):
    """Convierte '301_6' -> ('301', 6) | 'lab4_5' -> ('lab4', 5)."""
    if "_" not in texto:
        return texto, None
    salon, punto = texto.rsplit("_", 1)
    try:
        punto = int(punto)
    except ValueError:
        punto = None
    return salon, punto

def normalizar_salon(salon: str) -> str:
    """Unifica etiquetas a los nombres de tu lista."""
    if not salon: return salon
    s = salon.strip().lower().replace("_", " ")
    if s in {"301", "302"}: return "301"
    if s in {"lab 3", "lab3"}: return "Lab 3"
    if s in {"lab 4", "lab4"}: return "Lab 4"
    return salon.strip()

def leer_archivo(ruta: Path):
    """Lee un TXT con cabecera CSV, filtra por edad y BSSID válido."""
    registros = []
    try:
        with ruta.open("r", encoding="utf-8-sig", newline="") as f:
            for fila in csv.DictReader(f):
                try:
                    rssi = float(fila["rssi_dbm"])
                    edad = float(fila["edad_s"])
                    ts   = int(fila["timestamp_ms"])
                except (KeyError, ValueError, TypeError):
                    continue
                
                if edad > EDAD_MAX_S:
                    continue
                
                bssid = fila["bssid"].strip().lower()
                if bssid not in BSSID_VALIDOS:
                    continue
                    
                registros.append({
                    "timestamp":   ts,
                    "lugar":       fila["lugar"].strip(),
                    "bssid":       bssid,
                    "rssi":        rssi,
                })
    except Exception as e:
        print(f"Error leyendo {ruta.name}: {e}")
    return registros

def procesar_archivo(ruta: Path):
    registros = leer_archivo(ruta)
    if not registros: return []

    registros.sort(key=lambda x: x["timestamp"])

    grupos, grupo_actual = [], [registros[0]]
    for r in registros[1:]:
        if r["timestamp"] - grupo_actual[-1]["timestamp"] > UMBRAL_NUEVO_ESCANEO_MS:
            grupos.append(grupo_actual)
            grupo_actual = [r]
        else:
            grupo_actual.append(r)
    grupos.append(grupo_actual)

    salida = []
    for numero, grupo in enumerate(grupos, start=1):
        ubicaciones = [g["lugar"] for g in grupo if g["lugar"]]
        ubicacion = ubicaciones[0] if ubicaciones else ruta.stem

        valores_por_bssid = defaultdict(list)
        for g in grupo:
            valores_por_bssid[g["bssid"]].append(g["rssi"])

        salon_raw, punto = separar_ubicacion(ubicacion)
        salon = normalizar_salon(salon_raw)
        
        coord = PLANO.get(punto, {"x": None, "y": None, "zona": "desconocido"})

        fila_salida = {
            "archivo": ruta.name,
            "ubicacion": ubicacion,
            "salon": salon,
            "punto": punto,
            "zona": coord["zona"],
            "x": coord["x"],
            "y": coord["y"],
            "scan_id": numero,
            "timestamp_inicio_ms": min(g["timestamp"] for g in grupo),
        }
        for bssid in sorted(BSSID_VALIDOS):
            vals = valores_por_bssid.get(bssid)
            fila_salida[bssid] = round(median(vals), 2) if vals else RSSI_AUSENTE
            
        salida.append(fila_salida)
    return salida

def escribir_csv(ruta: Path, filas, columnas):
    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)

# =====================================================================
# 4. MÓDULO K-NN CON COORDENADAS
# =====================================================================
def distancia_euclidiana_rssi(vec1, vec2, bssids):
    suma = 0.0
    n = 0
    for b in bssids:
        v1 = vec1.get(b, RSSI_AUSENTE)
        v2 = vec2.get(b, RSSI_AUSENTE)
        if v1 != RSSI_AUSENTE and v2 != RSSI_AUSENTE:
            suma += (v1 - v2) ** 2
            n += 1
    if n == 0: return float('inf')
    return math.sqrt(suma / n)

def predecir_knn(vector_actual, bssids, fingerprint, k=3):
    distancias = []
    for ref in fingerprint:
        d = distancia_euclidiana_rssi(vector_actual, ref, bssids)
        if d != float('inf'):
            distancias.append((d, ref))
            
    distancias.sort(key=lambda x: x[0])
    vecinos = distancias[:k]
    
    if not vecinos:
        return None
        
    # Calculamos la coordenada final como un promedio ponderado de los K vecinos más cercanos
    suma_pesos = 0.0
    x_final = 0.0
    y_final = 0.0
    votos_salon = defaultdict(float)

    for d, ref in vecinos:
        peso = 1.0 / (d + 0.001)
        suma_pesos += peso
        
        # Acumular coordenadas
        if ref["x"] is not None:
            x_final += ref["x"] * peso
        if ref["y"] is not None:
            y_final += ref["y"] * peso
            
        votos_salon[ref["salon"]] += peso

    # Normalizar coordenadas
    if suma_pesos > 0:
        x_final /= suma_pesos
        y_final /= suma_pesos
        
    # Salón ganador por votos
    mejor_salon = max(votos_salon, key=votos_salon.get)
    confianza = votos_salon[mejor_salon] / suma_pesos if suma_pesos > 0 else 0

    return {
        "salon_pred": mejor_salon,
        "x_pred": round(x_final, 2),
        "y_pred": round(y_final, 2),
        "confianza": round(confianza, 3)
    }

# =====================================================================
# 5. PROGRAMA PRINCIPAL
# =====================================================================
def main():
    if not CARPETA_ENTRADA.exists():
        print(f"Error: No encuentro la carpeta {CARPETA_ENTRADA.resolve()}")
        print("Asegúrate de crear una carpeta llamada 'txt_filtrados' junto a este script.")
        return

    archivos = sorted(CARPETA_ENTRADA.glob("*.txt"))
    if not archivos:
        print("No hay archivos .txt dentro de 'txt_filtrados'.")
        return

    print("Iniciando procesamiento de archivos...")
    todas_las_filas = []
    for ruta in archivos:
        filas = procesar_archivo(ruta)
        todas_las_filas.extend(filas)
        print(f"  - {ruta.name}: {len(filas)} escaneos procesados")

    if not todas_las_filas:
        print("No se generaron escaneos. Revisa si las columnas de tus TXT coinciden.")
        return

    columnas = [
        "archivo", "ubicacion", "salon", "punto", "zona", "x", "y",
        "scan_id", "timestamp_inicio_ms"
    ] + sorted(BSSID_VALIDOS)
    escribir_csv(ARCHIVO_ESCANEOS, todas_las_filas, columnas)
    print(f"\n[OK] Archivo generado: {ARCHIVO_ESCANEOS}")

    # Construir Fingerprint
    agrupados = defaultdict(list)
    for f in todas_las_filas:
        if f["punto"] in PLANO: 
            agrupados[(f["salon"], f["punto"])].append(f)

    fingerprint = []
    for (salon, punto), filas in sorted(agrupados.items()):
        coord = PLANO[punto]
        fr = {
            "salon": salon,
            "punto": punto,
            "zona": coord["zona"],
            "x": coord["x"],
            "y": coord["y"],
            "cantidad_escaneos": len(filas),
        }
        # Calcular mediana de RSSI para cada BSSID
        for bssid in sorted(BSSID_VALIDOS):
            fr[bssid] = round(median([float(f[bssid]) for f in filas]), 2)
        fingerprint.append(fr)

    columnas_fp = [
        "salon", "punto", "zona", "x", "y", "cantidad_escaneos"
    ] + sorted(BSSID_VALIDOS)
    escribir_csv(ARCHIVO_FINGERPRINT, fingerprint, columnas_fp)
    print(f"[OK] Archivo generado: {ARCHIVO_FINGERPRINT}")

    # Validación k-NN
    print("\n--- Ejecutando validación k-NN (Calculando coordenadas) ---")
    predicciones = []
    
    for escaneo in todas_las_filas:
        pred = predecir_knn(escaneo, sorted(BSSID_VALIDOS), fingerprint, k=3)
        
        if pred:
            # Calculamos el error de distancia euclidiana en el plano (si es el mismo salón)
            error_dist = ""
            if pred["salon_pred"] == escaneo["salon"] and escaneo["x"] is not None:
                error_dist = round(math.sqrt((pred["x_pred"] - escaneo["x"])**2 + (pred["y_pred"] - escaneo["y"])**2), 2)

            predicciones.append({
                "archivo": escaneo["archivo"],
                "salon_real": escaneo["salon"],
                "x_real": escaneo["x"],
                "y_real": escaneo["y"],
                "salon_pred": pred["salon_pred"],
                "x_pred": pred["x_pred"],
                "y_pred": pred["y_pred"],
                "error_plano": error_dist,
                "confianza": pred["confianza"]
            })

    escribir_csv(ARCHIVO_PREDICCIONES, predicciones, 
                 ["archivo", "salon_real", "x_real", "y_real", 
                  "salon_pred", "x_pred", "y_pred", "error_plano", "confianza"])

    # Precisión de Salón
    aciertos_salon = sum(1 for p in predicciones if p["salon_real"] == p["salon_pred"])
    print(f"Precisión de Salón: {aciertos_salon}/{len(predicciones)} ({(aciertos_salon/len(predicciones))*100:.1f}%)")
    print(f"[OK] Archivo generado: {ARCHIVO_PREDICCIONES}")
    print("\nRevisa 'predicciones_knn.csv' para ver las coordenadas estimadas (x, y).")

if __name__ == "__main__":
    main()