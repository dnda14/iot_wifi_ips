# Contrato mínimo propuesto para la API del MVP

**Estado: propuesta para acordar con el equipo; no está implementada.** Complementa `PLAN_MVP.md`. Los ejemplos son ilustrativos y los BSSID no están validados para el proyecto.

## Objetivo y alcance

Android envía un escaneo completo; la API lo valida, obtiene una predicción, guarda ambos y devuelve el resultado. El dashboard consulta el último resultado. El primer flujo puede usar una predicción simulada identificada como tal; no debe presentarse como una estimación del modelo real.

**Identificación de visita:** Android generará un `session_id` aleatorio al iniciar una visita y lo enviará con cada escaneo. Si pierde ese valor, generará otro y se considerará una visita nueva; no se intenta recuperar una identidad anterior. No identifica a una persona ni sirve como clave de acceso. La generación en Android aún no está implementada; el control de acceso es una decisión independiente.

## Envío de un escaneo

`POST /api/v1/scans`

```http
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
- `device_id` identifica el dispositivo; su generación y duración quedan por acordar.
- `session_id` agrupa los escaneos de una visita. Android generará un UUID al iniciar la visita y lo mantendrá mientras dure, sin necesidad de guardarlo permanentemente. La validación actual solo comprueba que sea una cadena no vacía.
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
| Modelo o servicio no disponible | `503 Service Unavailable`; no inventar una ubicación |

La comparación de contenido, la concurrencia de dos solicitudes con el mismo ID y la recuperación ante una interrupción deben acordarse con la persona de datos. La propuesta es guardar escaneo y predicción en una sola transacción, sin responder `201` hasta confirmar ambos.

## Consulta de la última predicción

`GET /api/v1/devices/{device_id}/latest` es una propuesta; su relación con las visitas y su control de acceso están pendientes de decisión.

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

`last_seen_at` representa la hora de recepción del servidor, no la hora del teléfono. La API responde `404` si el repositorio no tiene predicciones para ese dispositivo y `503` si no está configurado o falla la consulta. Estos códigos se proponen para revisión con dashboard; falta acordar el umbral para marcar resultados como desactualizados. La lista de dispositivos y el historial se definirán con dashboard antes de implementarlos. Sin repositorio real configurado, la consulta responde `503`.

## Decisiones pendientes con el equipo

1. **Android y API:** creación y cierre de sesiones, formato y generación de IDs, límites de lecturas y validación de RSSI/BSSID.
2. **Datos y API:** unicidad de `scan_id`, comparación de reintentos, transacciones y comportamiento ante fallas concurrentes.
3. **Predicción y API:** interfaz de entrada, versión del modelo y condiciones para `unknown`, incluida la cantidad mínima de BSSID coincidentes.
4. **Dashboard y API:** respuesta sin datos, umbral de antigüedad, listado e historial.
5. **Visita:** cuándo se inicia y termina por inactividad, y cómo se relaciona con `device_id`.
6. **Integración y seguridad:** control de acceso independiente de `session_id`, transporte seguro y retención de datos. Las pruebas sin TLS deben limitarse a una red controlada y no usar datos reales.
