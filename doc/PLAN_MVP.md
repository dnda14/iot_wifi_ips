# Plan de trabajo para el MVP de posicionamiento Wi-Fi

La meta del MVP debería ser demostrar este recorrido completo:

> **Un teléfono Android captura redes Wi-Fi → envía un escaneo al servidor → el servidor estima la ubicación y guarda el resultado → el dashboard muestra la ubicación reciente del dispositivo.**

La prioridad no es tener desde el inicio el modelo más avanzado ni soportar cientos de dispositivos: primero hay que conseguir que el flujo funcione de extremo a extremo, y después medir su precisión y capacidad.

## 1. Estado actual del proyecto

Revisé el análisis existente en `doc/ANALISIS.md` y el servidor de demostración en `procesamiento/datos_entrada/servidor_ips.py`. Los puntos más importantes para planificar son:

- **Android ya captura señales** y tiene una opción de envío, pero utiliza `POST /api/reading`, ruta que no está conectada con ninguno de los servidores actuales.
- El **dashboard actual es una demostración**: reproduce escaneos históricos desde archivos CSV. No recibe datos en vivo de Android.
- Existe un prototipo **k-NN**, pero la evaluación actual utiliza datos que también participaron en la construcción de las referencias. Por eso, el 82 % de acierto documentado **no debe interpretarse como precisión real**.
- El servidor de demostración escucha en `127.0.0.1`, por lo que otro dispositivo de la red no puede acceder a él directamente.
- Hay una diferencia entre los BSSID configurados en dos scripts. Debe resolverse antes de comparar resultados.
- Hay datos de tres ambientes: **301, Lab 3 y Lab 4**. Pueden ser el alcance inicial del MVP.

Esto implica que la primera integración es más importante que crear nuevos componentes desde cero.

---

# 2. Distribución del trabajo entre seis personas

Propongo cinco responsables de componentes y una sexta persona dedicada a **integración, calidad y operación**. Esta última no reemplaza las pruebas de los demás: coordina las pruebas transversales y evita que la integración se deje para el final.

| Persona | Responsabilidad principal | Entregable |
|---|---|---|
| 1 | Servidor y API | API documentada que recibe escaneos y entrega resultados |
| 2 | Base de datos y preparación de datos | Esquema, persistencia y conjunto de datos reproducible |
| 3 | Predicción y evaluación | Modelo integrado, evaluación independiente y estrategia de mejora |
| 4 | Aplicación Android | Captura y envío confiable desde dispositivos Android |
| 5 | Dashboard | Vista de dispositivos y ubicaciones basada en datos reales |
| 6 | Integración, pruebas y despliegue | Entorno reproducible, pruebas de extremo a extremo y carga |

Cada persona puede tener una segunda responsabilidad de apoyo, pero conviene que cada módulo tenga **una persona claramente responsable**.

---

# 3. Tareas por persona

## Persona 1 — Servidor y API

**Objetivo:** recibir escaneos, invocar el modelo, guardar los resultados y exponerlos al dashboard.

### Tareas

1. Elegir y documentar el servidor que evolucionará hacia el MVP, evitando mantener dos implementaciones incompatibles sin necesidad.
2. Definir la API junto con Android, dashboard, base de datos y predicción.
3. Implementar:
   - Recepción y validación de escaneos completos.
   - Registro de sesión o asociación del escaneo con una sesión activa.
   - Invocación del módulo de predicción.
   - Persistencia de escaneo y resultado.
   - Consulta de dispositivos y última predicción.
4. Implementar autenticación mediante tokens:
   - Definir cómo se entrega y revoca el token.
   - Validarlo en endpoints protegidos.
   - No guardar tokens en texto plano en el repositorio.
   - Diferenciar **token de acceso** de **identificador de sesión**: no son lo mismo.
5. Manejar errores: formato incorrecto, token inválido, escaneo vacío, falla de base de datos o modelo no disponible.
6. Manejar reintentos sin duplicar escaneos usando un identificador único por escaneo.
7. Hacer pruebas de concurrencia junto con la persona 6.
8. Documentar cómo ejecutar el servidor y acceder desde la red local.

**Criterio de terminado:** un cliente de prueba autenticado puede enviar un escaneo válido, obtener una respuesta y consultar después el resultado; los errores y los reintentos tienen comportamiento definido.

---

## Persona 2 — Base de datos e ingeniería de datos

**Objetivo:** guardar las mediciones y preparar datos confiables para entrenamiento y evaluación.

### Tareas

1. Revisar los archivos de medición existentes, sus etiquetas y calidad.
2. Confirmar junto con el equipo cuáles BSSID son válidos y mantener una única configuración compartida.
3. Diseñar el esquema inicial:
   - Dispositivos.
   - Sesiones.
   - Escaneos.
   - Lecturas de cada escaneo: BSSID y RSSI.
   - Ubicaciones etiquetadas para entrenamiento.
   - Predicciones, versión de modelo y fecha.
4. Diferenciar claramente:
   - **Ubicación real etiquetada:** ingresada durante una campaña de medición.
   - **Ubicación predicha:** calculada por el modelo.
5. Implementar creación de tablas y migraciones reproducibles.
6. Preparar un proceso de importación y limpieza de mediciones existentes.
7. Generar conjuntos de entrenamiento y prueba separados por sesión, archivo o recorrido, en coordinación con la persona de predicción.
8. Documentar el formato y la procedencia de cada conjunto de datos.
9. Probar respaldo, restauración y consultas habituales.

### ¿SQLite?

**SQLite es una opción razonable para empezar** si el MVP corre en un solo servidor y el volumen de escrituras es moderado. No hay que asumir que soportará cualquier concurrencia: tiene limitaciones para escrituras simultáneas.

Recomiendo:

- Comenzar con SQLite y probar el escenario real.
- Medir tiempos de escritura, bloqueos y errores bajo carga.
- Definir una capa de acceso a datos que facilite migrar a PostgreSQL si las pruebas lo justifican.

**Criterio de terminado:** se puede levantar una base vacía, importar datos de muestra, guardar escaneos y obtener un conjunto de entrenamiento y prueba reproducible.

---

## Persona 3 — Predicción y evaluación

**Objetivo:** convertir el prototipo de predicción en un módulo reutilizable y medir su rendimiento sin fuga de datos.

### Tareas

1. Revisar la implementación existente de k-NN y extraer la lógica a un módulo independiente del servidor y del dashboard.
2. Definir el preprocesamiento:
   - BSSID esperados.
   - Tratamiento de redes faltantes.
   - Rango y formato de RSSI.
   - Agregación de lecturas cuando corresponda.
3. Entrenar una **línea base k-NN** con datos de entrenamiento.
4. Evaluar con sesiones, archivos o recorridos que no hayan participado en el entrenamiento.
5. Comparar k-NN con al menos otra alternativa sencilla **si el tiempo y los datos lo permiten**; por ejemplo, Random Forest.
6. Medir:
   - Exactitud por salón.
   - Exactitud por punto, si las etiquetas de punto son confiables.
   - Matriz de confusión por salón.
   - Resultados por dispositivo y sesión, cuando haya suficientes datos.
   - Error en metros solo si existen coordenadas reales y confiables.
7. Definir cuándo devolver **«ubicación desconocida»** por datos insuficientes o baja similitud. Ajustar el umbral con datos de validación.
8. Versionar el modelo y su configuración.
9. Integrar el modelo como función local del backend para el MVP; no es necesario crear un microservicio separado inicialmente.
10. Proponer mejoras: más mediciones por ambiente, más dispositivos, diferentes horarios y nuevas sesiones.

> La “confianza” actual del prototipo es un peso relativo de votación, no necesariamente una probabilidad calibrada. No debería mostrarse como certeza estadística sin validarla.

**Criterio de terminado:** el servidor puede cargar una versión del modelo y llamar a una función que recibe un escaneo y devuelve una predicción o «desconocido», con un informe de evaluación independiente.

---

## Persona 4 — Aplicación Android

**Objetivo:** capturar y enviar escaneos correctamente desde distintas marcas y versiones de Android.

### Tareas

1. Revisar la captura actual y separar claramente:
   - Modo de recolección etiquetada para entrenamiento.
   - Modo de operación para enviar escaneos y obtener predicciones.
2. Solicitar y verificar los permisos requeridos según la versión de Android.
3. Comprobar los requisitos para escanear Wi-Fi, incluido el estado de ubicación cuando aplique, y documentar las restricciones de frecuencia de escaneo.
4. Agrupar las lecturas correspondientes a un escaneo y enviar el lote definido en el contrato.
5. Configurar la URL del servidor y ofrecer una prueba de conexión.
6. Mostrar estados: permisos pendientes, capturando, enviado, sin conexión y error.
7. Implementar reintentos acotados, conservando el mismo `scan_id` para evitar duplicados.
8. Verificar que Android y servidor intercambian correctamente datos y errores.
9. Construir una matriz de pruebas por dispositivo:

| Marca/modelo | Android | Captura Wi-Fi | Conecta al servidor | Envía datos | Observaciones |
|---|---|---|---|---|---|
| Samsung | Por registrar | Pendiente | Pendiente | Pendiente | |
| Redmi | Por registrar | Pendiente | Pendiente | Pendiente | |
| Otros disponibles | Por registrar | Pendiente | Pendiente | Pendiente | |

10. Investigar el problema de Redmi **antes de atribuirlo a la marca**: permisos, versión de Android, red, URL/IP, HTTP frente a HTTPS, restricciones de batería, DNS y mensajes de error.

**Alcance:** solo Android. iOS queda fuera.

**Criterio de terminado:** al menos los dispositivos Android disponibles acordados por el equipo pueden capturar y enviar escaneos; los fallos restantes quedan registrados con pasos para reproducirlos.

---

## Persona 5 — Dashboard

**Objetivo:** mostrar información real del backend, no solo la reproducción de archivos.

### Tareas

1. Revisar la interfaz actual y conservar o separar el modo demo.
2. Consumir los endpoints acordados, inicialmente mediante consultas periódicas (*polling*).
3. Mostrar:
   - Lista de dispositivos.
   - Última ubicación estimada.
   - Hora de la última actualización.
   - Estado: reciente, desactualizado, sin datos o desconocido.
   - Versión del modelo, si está disponible.
4. Mostrar el plano esquemático existente sin afirmar que está a escala.
5. Incorporar historial básico por dispositivo si queda dentro del alcance acordado.
6. Manejar estados de carga, errores de API y desconexión.
7. Probar con datos simulados desde el inicio y luego con datos reales.
8. Evaluar junto con la persona 6 el comportamiento con muchos dispositivos y actualizaciones concurrentes.

**Criterio de terminado:** al recibir un escaneo real, el dashboard muestra el dispositivo y su resultado sin usar el botón de reproducción histórica.

---

## Persona 6 — Integración, calidad y operación

**Objetivo:** asegurar que los módulos funcionan juntos y que cualquier integrante puede ejecutar el sistema.

### Tareas

1. Coordinar la definición y congelación inicial de contratos.
2. Preparar instrucciones de instalación, configuración y ejecución del sistema.
3. Documentar dependencias, variables de entorno, datos de prueba y procedimiento para acceder desde Android.
4. Mantener ejemplos de requests y respuestas para que los equipos puedan trabajar con datos simulados.
5. Diseñar y ejecutar pruebas:
   - Integración Android → API.
   - API → modelo.
   - API → base de datos.
   - Dashboard → API.
   - Flujo completo.
6. Diseñar pruebas de concurrencia junto con servidor y dashboard:
   - Varios dispositivos enviando escaneos simultáneamente.
   - Consultas del dashboard mientras se reciben escaneos.
   - Registro de latencia, errores y bloqueos.
7. Preparar un entorno de demostración reproducible y una lista de verificación.
8. Coordinar un registro de incidencias y verificar su resolución.
9. Revisar seguridad mínima y privacidad: acceso autenticado, protección de credenciales y política básica de conservación de datos.

**Criterio de terminado:** otro integrante puede levantar el MVP siguiendo la documentación y ejecutar una prueba completa. Los resultados de concurrencia quedan registrados.

---

# 4. Contratos: entradas y salidas de cada módulo

Estos contratos son una **propuesta inicial**, no describen la API que ya existe. Conviene acordarlos entre las seis personas antes de implementar en paralelo.

## 4.1 Flujo general

```text
Android
  │  escaneo JSON + token
  ▼
API / servidor
  ├──► Módulo de predicción ──► resultado
  ├──► Base de datos ─────────► escaneo + resultado persistidos
  │
  └──► API de consulta ───────► dashboard
```

## 4.2 Android → servidor: enviar un escaneo

**Propuesta:** `POST /api/v1/scans`

Cabecera:

```http
Authorization: Bearer <token>
Content-Type: application/json
```

Entrada:

```json
{
  "scan_id": "scan-001",
  "device_id": "device-001",
  "session_id": "session-001",
  "captured_at": "2026-01-15T14:30:00Z",
  "readings": [
    {
      "bssid": "70:0b:01:ef:f6:26",
      "rssi_dbm": -61
    },
    {
      "bssid": "70:0b:01:ef:f6:27",
      "rssi_dbm": -74
    }
  ]
}
```

Los BSSID anteriores son **solo ejemplos de formato**, no una lista validada para el proyecto.

**Reglas mínimas:**

- `scan_id`: identificador único generado por Android; se reutiliza en un reintento.
- `device_id`: identificador seudónimo del dispositivo, no necesariamente un identificador de hardware.
- `session_id`: sesión de captura a la que pertenece el escaneo.
- `captured_at`: fecha y hora UTC del teléfono; el servidor registra también su propia hora de recepción.
- `readings`: lista de redes observadas, no vacía.
- `rssi_dbm`: intensidad en dBm.
- La etiqueta de ubicación real, cuando exista, debe enviarse solo en el flujo autorizado de recolección de datos y no confundirse con la predicción.

**Respuesta exitosa propuesta — `201 Created`:**

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

Si no hay evidencia suficiente:

```json
{
  "scan_id": "scan-001",
  "status": "processed",
  "prediction": {
    "status": "unknown",
    "room": null,
    "point": null,
    "model_version": "knn-v1"
  }
}
```

**Errores y reintentos por acordar explícitamente:**

- `400`: datos inválidos.
- `401` / `403`: token inválido o sin permisos.
- `409`: mismo `scan_id` con contenido diferente.
- `503`: servicio o modelo no disponible.
- Mismo `scan_id` y mismo contenido: devolver el resultado previamente guardado, sin crear otro escaneo.

Para simplificar el MVP, la respuesta exitosa anterior supone que el escaneo **ya fue guardado y procesado**. Si se decide procesar en segundo plano, el contrato debe cambiar para reflejar un estado pendiente.

## 4.3 Servidor → módulo de predicción

Para el MVP recomiendo una **función interna**, no un endpoint separado:

```python
predict(readings, model) -> PredictionResult
```

| Elemento | Contrato |
|---|---|
| Entrada | Lista de BSSID y RSSI de un escaneo, más modelo/configuración cargados |
| Salida | Estado `estimated` o `unknown`, salón y punto opcionales, versión del modelo |
| Error | Modelo no disponible, configuración inválida o entrada incompatible |

La función no debería depender directamente de Android ni del dashboard. La persona de predicción y la del servidor deben acordar si recibe datos crudos o ya normalizados; el preprocesamiento debe ser **el mismo** en entrenamiento e inferencia.

## 4.4 Servidor ↔ base de datos

| Operación | Entrada | Salida |
|---|---|---|
| Guardar escaneo | IDs, fechas y lecturas | Confirmación o error |
| Guardar predicción | `scan_id`, resultado y versión de modelo | Confirmación o error |
| Consultar última ubicación | `device_id` | Última predicción y fecha |
| Exportar entrenamiento | Filtros y versión de dataset | Datos etiquetados y metadatos |

Para una primera versión síncrona, servidor y base de datos deben acordar cómo guardar escaneo y predicción de forma consistente si una operación falla.

## 4.5 Dashboard → servidor

**Propuesta mínima:**

```http
GET /api/v1/devices
GET /api/v1/devices/{device_id}/latest
GET /api/v1/devices/{device_id}/history?limit=50
```

Ejemplo de última ubicación:

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

El equipo debe acordar cuánto tiempo puede pasar antes de marcar una ubicación como **desactualizada**. Una ubicación antigua no debe mostrarse como si fuera actual.

## 4.6 Sesiones y tokens

Para evitar confusiones:

- **Token:** autoriza al cliente a usar la API.
- **Sesión:** agrupa un período de captura de un dispositivo.
- **Escaneo:** conjunto de señales capturadas en un momento.
- **Lectura:** BSSID y RSSI de una red dentro de un escaneo.

Para el contrato faltaría acordar cómo se crean y cierran las sesiones; por ejemplo, mediante `POST /api/v1/sessions` y un endpoint de cierre. Para desarrollo puede usarse un mecanismo sencillo de aprovisionamiento de tokens, pero no conviene distribuir un único token fijo dentro de la aplicación para un despliegue real.

---

# 5. Orden de trabajo recomendado

## Fase 1 — Acuerdos y preparación

**Trabajan las seis personas.**

- Confirmar alcance: ambientes, dispositivos disponibles y funciones mínimas.
- Revisar BSSID y datos disponibles.
- Acordar contratos, errores, autenticación y estructura de base de datos.
- Crear ejemplos JSON y respuestas simuladas.
- Establecer cómo ejecutar cada componente.

**Hito:** todos pueden trabajar contra los mismos ejemplos, aunque los módulos todavía no estén terminados.

## Fase 2 — Primer flujo completo

- Android envía un escaneo de prueba.
- El servidor lo valida y guarda.
- El servidor devuelve inicialmente una predicción simulada si el modelo aún no está integrado.
- El dashboard muestra ese resultado desde la API.

**Hito:** Android → servidor → base de datos → dashboard funciona en vivo.

## Fase 3 — Modelo real y pruebas de dispositivos

- Sustituir la predicción simulada por k-NN.
- Evaluar con datos separados por sesión o recorrido.
- Probar Samsung, Redmi y otros Android disponibles.
- Corregir permisos, conectividad y errores de captura/envío.

**Hito:** el flujo completo funciona con un modelo real y hay resultados iniciales de calidad.

## Fase 4 — Concurrencia y cierre

- Probar envíos simultáneos y consultas del dashboard.
- Revisar comportamiento de SQLite bajo la carga elegida.
- Corregir fallos importantes.
- Documentar instalación, limitaciones y demostración final.

**Hito:** el equipo puede demostrar y repetir el MVP con evidencia de funcionamiento y mediciones.

---

# 6. Pruebas mínimas de aceptación

| Prueba | Resultado esperado |
|---|---|
| Escaneo válido desde Android | Se recibe, guarda y procesa |
| Escaneo vacío o mal formado | Se rechaza con error comprensible |
| Token inválido | La API rechaza el acceso |
| Reenvío del mismo escaneo | No se crean duplicados |
| BSSID faltantes | El modelo responde de forma definida o devuelve desconocido |
| Modelo no disponible | El sistema informa el error; no inventa una ubicación |
| Desconexión de Android | Se muestra el error y se aplican reintentos acotados |
| Dashboard sin datos | Muestra estado vacío, no valores simulados |
| Dispositivo sin actualizaciones | Se marca como desactualizado |
| Varios dispositivos | Cada resultado queda asociado al dispositivo correcto |
| Evaluación del modelo | Se reportan resultados sobre sesiones no usadas para entrenar |
| Carga concurrente | Se registran latencia, errores y bloqueos |

Para las pruebas de carga, antes de ejecutarlas acuerden un objetivo concreto. Por ejemplo, **10, 25 y 50 dispositivos simulados**, definiendo cada cuántos segundos envía cada uno. Son escenarios iniciales de prueba, **no una capacidad garantizada**. También deben definir los objetivos aceptables de latencia y errores según el uso previsto.

---

# 7. Definición de “MVP terminado”

El MVP está listo para demostración cuando:

1. Android captura y envía escaneos desde los dispositivos acordados.
2. La API autentica, valida y guarda los datos sin duplicarlos ante reintentos.
3. El modelo integrado devuelve una ubicación o «desconocido».
4. El dashboard muestra resultados reales y distingue datos antiguos.
5. Existe una evaluación del modelo sin fuga de datos.
6. Se ejecutaron pruebas de concurrencia con resultados registrados.
7. El sistema puede instalarse y ejecutarse siguiendo la documentación.
8. Se conocen y comunican sus limitaciones.

**Recomendación final:** hagan una reunión corta para acordar los contratos y, durante la primera integración, acepten una predicción simulada. Así pueden descubrir inmediatamente problemas de Android, red, API y dashboard sin esperar a que el modelo esté perfeccionado.
