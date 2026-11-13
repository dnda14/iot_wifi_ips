# API de escaneos Wi-Fi

Servidor de desarrollo de la persona 1. El contrato propuesto está en `doc/CONTRATO_API_MVP.md`.

## Requisitos e instalación

Se requiere Python 3.10 o posterior. Desde la raíz del repositorio:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r procesamiento/datos_entrada/requirements-api.txt
```

En Windows, activar con `.venv\Scripts\activate`.

## Iniciar el servidor

```bash
python procesamiento/datos_entrada/servidor.py
```

Flask escucha en el puerto `5000` y en todas las interfaces. Desde el mismo equipo se accede a `http://127.0.0.1:5000`; desde Android, usar `http://<IP-LAN-DEL-EQUIPO>:5000` y comprobar que ambos estén en la misma red y que el firewall permita la conexión. `0.0.0.0` es la dirección de escucha, no la URL que debe usar el teléfono.

**Solo desarrollo:** el servidor actual no tiene control de acceso ni TLS, y el servidor de Flask no es apto para producción. Usar únicamente una red de pruebas confiable, sin datos sensibles. Android puede requerir configuración específica para permitir HTTP sin TLS.

## Estado de los endpoints

- `POST /api/v1/scans`: valida el escaneo. Necesita un predictor y un repositorio configurados en `app.config` como `PREDICTOR` y `REPOSITORIO_ESCANEOS`. Sin ellos responde `503`; con ambos llama al procesamiento y devuelve `201` solo si el repositorio confirma el guardado. La idempotencia de reintentos aún no está implementada.
- `GET /api/v1/devices/<device_id>/latest`: consulta la última predicción a través de `REPOSITORIO_ESCANEOS`; sin repositorio responde `503`, sin resultado `404`.
- `POST /api/mediciones`: endpoint anterior de demostración; no guarda ni predice.

Todavía no se incluyen implementaciones reales del predictor ni del repositorio, ni un mecanismo de configuración de producción. Los contratos Python están en `procesamiento_escaneos.py`.

Ejemplo de solicitud estructuralmente válida; sin dependencias configuradas se espera `503`:

```bash
curl -i http://127.0.0.1:5000/api/v1/scans \
  -H 'Content-Type: application/json' \
  -d '{"scan_id":"scan-001","device_id":"device-001","session_id":"session-001","captured_at":"2026-01-15T14:30:00Z","readings":[{"bssid":"70:0b:01:ef:f6:26","rssi_dbm":-61}]}'
```

## Pruebas

Con el entorno virtual activado:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s procesamiento/datos_entrada -p 'test_*.py' -v
```

La prueba concurrente inicia un servidor HTTP local efímero y envía 50 peticiones en paralelo con predictor y repositorio simulados. Informa tiempos y errores, pero **no mide** SQLite, el modelo real, Android, una red real ni capacidad de producción. No usa el servidor que se haya iniciado manualmente.

Resultado de una ejecución local de referencia: 50 solicitudes, 0 errores, duración total 0,030 s, latencia mediana 16,5 ms y máxima 23,9 ms. Es una única ráfaga en bucle local, no una prueba sostenida ni una capacidad garantizada; los resultados varían entre ejecuciones.
