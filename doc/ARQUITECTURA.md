# Arquitectura implementada del MVP

```text
scanwifi/ (Android) ── POST /api/reading ──┐
                                           ▼
                                    backend/app/api/
                                           │
                          ┌────────────────┴───────────────┐
                          ▼                                ▼
                  prediction.py                    database.py → SQLite
                          │                                │
                          └──────────────┬─────────────────┘
                                         ▼
web-admin/ (navegador) ◄── GET /api/v1/... ┘
```

`backend/` contiene la API FastAPI. `web-admin/` es el cliente web del administrador, servido por el mismo proceso para el MVP. `scanwifi/` conserva su nombre y estructura Gradle porque es el proyecto Android de otro integrante.

El endpoint nuevo `POST /api/v1/scans` recibe un escaneo completo con `scan_id`, `device_id`, `session_id`, `captured_at` y `readings`. La ruta `/api/reading` acepta el formato actual de Android y agrupa lecturas temporalmente como puente. La web consume exclusivamente endpoints `/api/v1`.

La predicción y el acceso a SQLite son módulos separados del HTTP. El fingerprint actual sigue en `procesamiento/datos_entrada/fingerprint.csv`; los scripts y datos de captura originales también permanecen allí para no alterar el flujo de generación existente durante esta migración. El servidor antiguo queda como referencia, y la nueva base se crea en `backend/data/`.

La estructura de ejecución inicial es un proceso FastAPI/Uvicorn en una PC accesible desde los teléfonos de la red local y una base SQLite en esa misma PC. El navegador abre la web servida por FastAPI. Para instalar, ejecutar y probar, véase [backend/README.md](../backend/README.md).

## Responsabilidades entre integrantes

| Componente | Directorio | Contrato compartido |
|---|---|---|
| API | `backend/app/api/`, `backend/app/schemas.py` | JSON y códigos HTTP |
| Base de datos | `backend/app/database.py` | Guardar y consultar escaneos |
| Predicción | `backend/app/prediction.py` | Escaneo → predicción o desconocido |
| Android | `scanwifi/` | Enviar escaneos y mostrar errores |
| Web administrador | `web-admin/` | Consultar dispositivos e historial |
| Integración | `backend/tests/`, documentación | Pruebas de extremo a extremo |

La autenticación y el acceso por roles no están implementados. El identificador de sesión agrupa capturas; no es una credencial.
