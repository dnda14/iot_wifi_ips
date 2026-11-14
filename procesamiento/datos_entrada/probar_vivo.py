import csv
from construir_fingerprints import predecir_knn, PLANO, BSSID_VALIDOS, RSSI_AUSENTE, leer_archivo
from pathlib import Path

# 1. Cargar el fingerprint ya generado
fingerprint = []
with open("fingerprint.csv", encoding="utf-8-sig", newline="") as f:
    for fila in csv.DictReader(f):
        # Convertir a float los RSSI
        for b in BSSID_VALIDOS:
            fila[b] = float(fila[b])
        for campo in ["x", "y"]:
            fila[campo] = float(fila[campo]) if fila[campo] else None
        fingerprint.append(fila)

# 2. Simular un nuevo usuario (lee un TXT que NO esté en txt_filtrados)
ruta_prueba = Path("prueba_usuario.txt")  # tú renombras cualquier archivo a este
registros = leer_archivo(ruta_prueba)

# 3. Agrupar en escaneos
registros.sort(key=lambda x: x["timestamp"])
grupo = [registros[0]]
for r in registros[1:]:
    if r["timestamp"] - grupo[-1]["timestamp"] > 1000:
        # Ya cerró un escaneo, predecir
        vector = {b: RSSI_AUSENTE for b in BSSID_VALIDOS}
        for g in grupo:
            vector[g["bssid"]] = g["rssi"]
        pred = predecir_knn(vector, sorted(BSSID_VALIDOS), fingerprint, k=3)
        print(f"📍 Predicción: {pred['salon_pred']} (x={pred['x_pred']}, y={pred['y_pred']}, confianza={pred['confianza']})")
        grupo = [r]
    else:
        grupo.append(r)

# Último escaneo
if grupo:
    vector = {b: RSSI_AUSENTE for b in BSSID_VALIDOS}
    for g in grupo:
        vector[g["bssid"]] = g["rssi"]
    pred = predecir_knn(vector, sorted(BSSID_VALIDOS), fingerprint, k=3)
    print(f"📍 Predicción final: {pred}")