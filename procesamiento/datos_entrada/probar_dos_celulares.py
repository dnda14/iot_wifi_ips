"""Simula dos celulares para probar el mapa multipaciente SIN usar Android.

Ejecutar en una segunda ventana de PowerShell:
  python probar_dos_celulares.py
La simulacion envia dos grupos de lecturas una sola vez. No representa
captura real ni una prueba de precision del posicionamiento.
"""
import csv
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SERVER = 'http://127.0.0.1:8000'
FINGERPRINT = Path(__file__).resolve().parent / 'fingerprint.csv'
TEST_POINTS = [('simulado_01', '301', 5), ('simulado_02', 'Lab 3', 7)]


def send_reading(device, bssid, rssi):
    payload = json.dumps({
        'device_id': device, 'router_bssid': bssid, 'rssi': rssi
    }).encode('utf-8')
    request = Request(SERVER + '/api/reading', payload,
                      {'Content-Type': 'application/json'}, method='POST')
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def main():
    if not FINGERPRINT.is_file():
        raise SystemExit('ERROR: falta fingerprint.csv en la misma carpeta.')
    with FINGERPRINT.open(encoding='utf-8-sig', newline='') as file:
        rows = list(csv.DictReader(file))
    for device, room, point in TEST_POINTS:
        reference = next((r for r in rows if r.get('salon') == room and
                          r.get('punto') == str(point)), None)
        if not reference:
            print('No se encontro un punto de referencia:', room, point)
            continue
        response = None
        sent = 0
        for column, value in reference.items():
            if column.count(':') == 5 and value:
                rssi = float(value)
                if rssi > -100:
                    response = send_reading(device, column, rssi)
                    sent += 1
        predicted = (response or {}).get('ubicacion')
        if predicted:
            print(f'{device}: {sent} lecturas -> {predicted["salon"]}, punto {predicted["punto"]}')
        else:
            print(f'{device}: {sent} lecturas -> aun sin ubicacion. Respuesta: {response}')
    print('Abre el mapa en: ' + SERVER)
    print('ATENCION: son mediciones simuladas basadas en fingerprint.csv.')


if __name__ == '__main__':
    try:
        main()
    except (URLError, HTTPError) as exc:
        raise SystemExit(f'No se puede conectar al servidor {SERVER}. Comprueba que este iniciado. {exc}')
