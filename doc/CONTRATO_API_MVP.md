# Contrato mínimo propuesto para la API del MVP

**Estado: propuesta para acordar con el equipo; no está implementada.** Complementa `PLAN_MVP.md`. Los ejemplos son ilustrativos y los BSSID no están validados para el proyecto.

## Objetivo y alcance

Android envía un escaneo completo; la API lo valida, obtiene una predicción, guarda ambos y devuelve el resultado. El dashboard consulta el último resultado. El primer flujo puede usar una predicción simulada identificada como tal; no debe presentarse como una estimación del modelo real.

## Envío de un escaneo

`POST /api/v1/scans`

```http
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "scan_id": "scan-001",
  "device_id": "device-001",
  "session_id": "session-001",
  "captured_at": "2026-01-15T14:30:00Z",
  "readings": [
    {"bssid": "70:0b:01:ef:f6:26", "rssi_dbm": -61},
    {"bssid": "70:0b:01:ef:f6:27", "rssi_dbm": -74}
  ]
}
```

- `scan_id` identifica un escaneo y debe mantenerse en los reintentos.
- `device_id` es un identificador seudónimo; `session_id` agrupa capturas y no es un token.
- `captured_at` es la fecha UTC indicada por el teléfono. El servidor registra por separado la recepción.
- `readings` debe contener al menos una lectura con BSSID y RSSI en dBm. El formato y los límites concretos se acordarán antes de implementar la validación.
- Las etiquetas de ubicación real pertenecen al flujo autorizado de recolección, no a este contrato operativo inicial.

### Respuesta de un escaneo nuevo

`201 Created` significa que tanto el escaneo como su resultado fueron guardados:

```json
{
  "scan_id": "scan-001",
  "status": "processed",
  "prediction": {
    "status": "estimated",
    "room": "Lab 3",
    "point": "4",
    "model_version": "knn-v1"
  }
}
```

Si no hay evidencia suficiente, `prediction.status` será `unknown` y `room` y `point` serán `null`. Para una predicción simulada se propone usar `model_version: "mock-v1"` y distinguirla visualmente de una predicción real.

### Reintentos y errores

| Situación | Respuesta propuesta |
|---|---|
| Mismo `scan_id` y mismo contenido ya procesado | `200 OK`, con el resultado guardado; no se crea otro escaneo |
| Mismo `scan_id` y contenido diferente | `409 Conflict` |
| JSON o datos inválidos | `400 Bad Request` |
| Token ausente o inválido | `401 Unauthorized` |
| Token sin permisos | `403 Forbidden` |
| Modelo o servicio no disponible | `503 Service Unavailable`; no inventar una ubicación |

La comparación de contenido, la concurrencia de dos solicitudes con el mismo ID y la recuperación ante una interrupción deben acordarse con la persona de datos. La propuesta es guardar escaneo y predicción en una sola transacción, sin responder `201` hasta confirmar ambos.

## Consulta de la última predicción

`GET /api/v1/devices/{device_id}/latest`, con autenticación.

```json
{
  "device_id": "device-001",
  "last_seen_at": "2026-01-15T14:30:02Z",
  "prediction": {
    "status": "estimated",
    "room": "Lab 3",
    "point": "4",
    "model_version": "knn-v1"
  }
}
```

Se propone que `last_seen_at` sea la hora de recepción del servidor, no la hora del teléfono. Quedan por acordar la respuesta para dispositivos sin datos y el umbral para marcar resultados como desactualizados. La lista de dispositivos y el historial se definirán con dashboard antes de implementarlos.

## Decisiones pendientes con el equipo

1. **Android y API:** creación y cierre de sesiones, formato y generación de IDs, límites de lecturas y validación de RSSI/BSSID.
2. **Datos y API:** unicidad de `scan_id`, comparación de reintentos, transacciones y comportamiento ante fallas concurrentes.
3. **Predicción y API:** interfaz de entrada, versión del modelo y condiciones para `unknown`, incluida la cantidad mínima de BSSID coincidentes.
4. **Dashboard y API:** respuesta sin datos, umbral de antigüedad, listado e historial.
5. **Integración y seguridad:** aprovisionamiento y revocación de tokens, permisos por cliente, transporte seguro y retención de datos. Las pruebas sin TLS deben limitarse a una red controlada y no usar credenciales reales.
