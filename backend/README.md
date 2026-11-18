# API y panel de administración

La nueva API usa FastAPI. La app Android actual sigue funcionando con `POST /api/reading`; la ruta nueva `POST /api/v1/scans` recibe escaneos completos. El panel en `web-admin/` consume las rutas `/api/v1/...`.

## Preparación

Desde la raíz del repositorio:

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -e 'backend[test]'
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

En Windows se usan los ejecutables de `backend\\.venv\\Scripts\\`. El panel queda en `http://IP_DEL_SERVIDOR:8000/` y la documentación interactiva en `/docs`. En Android se configura la URL base, sin `/api/reading` al final.

Por defecto se lee `procesamiento/datos_entrada/fingerprint.csv` y se escribe `backend/data/ips.sqlite3`. Se pueden cambiar con `IPS_FINGERPRINT_PATH` e `IPS_DATABASE_PATH`. El archivo SQLite nuevo es independiente de la base de demostración anterior.

## Contrato nuevo

```http
POST /api/v1/scans
Content-Type: application/json
```

```json
{
  "scan_id": "scan-001",
  "device_id": "phone-001",
  "session_id": "8ddac220-2192-4110-b553-2f8945cfeef5",
  "captured_at": "2026-11-18T14:30:00Z",
  "readings": [
    {"bssid": "30:b5:c2:ef:3e:f0", "rssi_dbm": -52},
    {"bssid": "70:0b:01:ef:f6:26", "rssi_dbm": -56}
  ]
}
```

La primera petición devuelve `201`; un reintento idéntico, `200` y el mismo resultado; el mismo `scan_id` con contenido diferente, `409`. JSON inválido devuelve `422`. El resultado contiene `prediction.status` (`estimated` o `unknown`), `room`, `point`, `zone`, `confidence`, `aps` y `model_version`. `confidence` es consenso del k-NN, no probabilidad calibrada. Se guardan también los escaneos sin ubicación.

Consultas del panel:

- `GET /api/v1/meta`: plano, cantidad de referencias y BSSID calibrados.
- `GET /api/v1/diagnostics`: recepción reciente de clientes Android antiguos.
- `GET /api/v1/devices`: último escaneo de cada dispositivo.
- `GET /api/v1/devices/{device_id}/latest`: último escaneo del dispositivo.
- `GET /api/v1/devices/{device_id}/history?limit=50`: historial por dispositivo.
- `GET /api/v1/history?limit=50`: historial general.

Las rutas `/api/reading`, `/api/estado`, `/api/ubicacion` y `/api/historial` siguen disponibles como puente para la app anterior. En el puente, el servidor agrupa lecturas recientes por dispositivo durante 15 segundos; el contrato nuevo evita mezclar capturas distintas.

## Pruebas

```bash
cd backend
.venv/bin/python -m pytest -q
```

## Límites actuales

El panel y el API se sirven desde el mismo proceso y origen. No se ha implementado autenticación ni HTTPS: úsese solo en una red de pruebas controlada, sin identidades reales. La lógica de predicción conserva el k-NN existente; su precisión sigue pendiente de evaluación con sesiones independientes. El estado temporal de `/api/reading` está en memoria y se pierde al reiniciar; los escaneos v1 y las predicciones guardadas permanecen en SQLite.
