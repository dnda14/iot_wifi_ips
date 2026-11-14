# Análisis del proyecto: posicionamiento Wi‑Fi en vivo

## Objetivo

El objetivo es construir un **sistema de posicionamiento Wi‑Fi en vivo (IPS)**: una aplicación Android captura mediciones RSSI y las envía a un backend que las procesa inmediatamente, estima la ubicación y presenta el resultado en un dashboard y/o historial.

El estado actual es un prototipo con captura Android y procesamiento offline, más una demostración que reproduce datos históricos. La comunicación de extremo a extremo aún no está implementada.

## Componentes actuales

### Aplicación Android

`scanwifi/app/src/main/java/com/example/scanwifi/MainActivity.kt`

- Permite etiquetar una ubicación y capturar RSSI de redes cercanas o de la red conectada.
- Puede guardar las lecturas como CSV en `Descargas/LPS`.
- Tiene una opción para enviar mediciones al servidor.
- El cuerpo que envía actualmente contiene `device_id`, `router_bssid` y `rssi`.
- El envío se dirige a `POST /api/reading`.

### Procesamiento de datos

En `procesamiento/datos_entrada/`:

- `filtrar_wifi.py` filtra registros por una lista de BSSID.
- `construir_fingerprints.py` agrupa registros por tiempo, calcula medianas RSSI por ubicación, construye fingerprints y evalúa k-NN.
- `probar_vivo.py` simula una predicción leyendo un archivo local. No se conecta a la app ni a un backend.

### Servidores

- `servidor.py` expone `POST /api/mediciones`, valida que el cuerpo tenga una lista `mediciones` y responde con un conteo. No predice ubicaciones ni persiste mediciones.
- `servidor_ips.py` carga `escaneos.csv` y `fingerprint.csv` al iniciar, predice k-NN al recorrer esos datos y sirve un dashboard. Su endpoint `/api/siguiente` reproduce un escaneo guardado; no recibe datos de la app. Escucha en `127.0.0.1:8000`, inaccesible desde otros dispositivos de la red local.
- `ips_demo.sqlite3` almacena el historial de la demostración.

## Hallazgos principales

### 1. El flujo Android → backend está desconectado

La app envía a `/api/reading`, pero ninguno de los servidores implementa esa ruta con el formato esperado:

- Flask acepta `POST /api/mediciones` y espera `{"mediciones": [...]}`.
- El dashboard no tiene un endpoint de ingestión en vivo.
- El dashboard utiliza escaneos históricos y no consume mediciones entrantes.

Por tanto, activar el envío en la aplicación no da lugar a una predicción en vivo.

### 2. El backend de demostración no es accesible desde el teléfono

`servidor_ips.py` enlaza el servidor a `127.0.0.1`. Para pruebas desde un teléfono debe escuchar en una interfaz de red accesible, protegerse adecuadamente y usarse la IP o nombre del equipo servidor. En Android, el tráfico HTTP sin TLS está habilitado en el manifest (`usesCleartextTraffic="true"`), lo que puede servir en pruebas controladas, pero no es apropiado para producción.

### 3. La evaluación del modelo tiene fuga de datos

`construir_fingerprints.py` construye el fingerprint con todos los escaneos y luego predice esos mismos escaneos. Cada dato evaluado también participa en las referencias. El CSV contiene 293 predicciones, con 240 aciertos de salón (82,0%), pero esta cifra no es una estimación independiente del rendimiento real.

Se debe separar entrenamiento y prueba por sesión/archivo o recorrido, y reportar resultados por salón y punto, además del error espacial. No basta con dividir filas aleatoriamente si mediciones muy cercanas del mismo recorrido quedan en ambos conjuntos.

### 4. Inconsistencia en la lista de BSSID

`filtrar_wifi.py` incluye `70:0b:01:ef:f6:27`, mientras que `construir_fingerprints.py` usa `70:0b:01:ef:f6:26`. El filtro advierte también de una posible diferencia de BSSID. Hay que confirmar qué identificadores corresponden a los puntos de acceso y usar una única configuración coherente en captura, filtrado y fingerprint.

### 5. El prototipo depende de CSV precargados

El dashboard informa de una ubicación de prueba y avanza por los escaneos guardados. Es una demo offline, no una prueba de latencia o comportamiento en vivo.

### 6. Reproducibilidad y robustez

- Los scripts Python usan rutas relativas al directorio de trabajo en varios lugares; invocarlos desde otra ubicación puede hacer que no encuentren los archivos.
- `probar_vivo.py` puede fallar si el TXT no contiene registros válidos, al acceder al primer elemento de una lista vacía.
- No se encontró un archivo de dependencias Python ni instrucciones de instalación y ejecución.
- El repositorio contiene CSV derivados, base SQLite de demo y `__pycache__`; conviene distinguir entradas, artefactos generados y datos de demostración.

## Datos observados en el repositorio

- `escaneos.csv`: 293 filas provenientes de 35 archivos.
- `fingerprint.csv`: 35 fingerprints.
- `predicciones_knn.csv`: 240/293 aciertos de salón (82,0%) con el método de validación actual, sujeto a la fuga de datos descrita arriba.
- Las ubicaciones presentes corresponden a `301`, `Lab 3` y `Lab 4`.

## Dirección recomendada para convertirlo en sistema en vivo

### 1. Definir un contrato único de ingestión

Acordar una sola ruta y estructura JSON entre app y backend. Para el enfoque actual, la ruta que usa la app (`POST /api/reading`) puede ser el punto de partida. Definir explícitamente si el backend recibe una lectura individual o un lote, y validar campos, tipos, identificadores y valores RSSI. Incluir un timestamp generado en el dispositivo y, si se necesita, identificador de sesión.

### 2. Implementar backend de ingestión y predicción

El backend debe:

1. Recibir y validar lecturas de la app.
2. Asociar lecturas cercanas temporalmente en una ventana de escaneo, o aceptar un vector completo por escaneo.
3. Normalizar las mediciones a los BSSID esperados y asignar RSSI ausente de forma consistente.
4. Ejecutar la predicción contra un fingerprint cargado y validado.
5. Responder con salón, punto/coordenadas, confianza y metadatos útiles.
6. Persistir las mediciones y predicciones si el historial es un requisito.

El código actual de k-NN puede servir como prototipo, pero se debe evitar duplicar implementaciones divergentes entre scripts y servidor: extraer la lógica de predicción a un módulo reutilizable.

### 3. Conectar el dashboard a resultados reales

El dashboard debe consultar predicciones nuevas o recibirlas por un mecanismo de actualización (por ejemplo, polling al inicio). El endpoint `/api/siguiente` puede conservarse como modo de demo, pero debe distinguirse claramente del flujo en vivo.

### 4. Tratar la conectividad y seguridad

- Configurar una dirección de escucha accesible desde la LAN y documentar cómo obtener la IP del servidor.
- Para pruebas, limitar el acceso a una red confiable; para despliegue, añadir TLS y autenticación/autorización.
- Manejar errores de red, reintentos y límites de cola en Android sin acumular lecturas indefinidamente.
- Definir qué pasa cuando las lecturas llegan tarde, repetidas o fuera de orden.

### 5. Validar la calidad del sistema

- Recoger sesiones independientes para construir el fingerprint y probar predicciones.
- Medir exactitud de salón, exactitud de punto, error espacial y latencia extremo a extremo.
- Probar escenarios con BSSID faltantes, escaneos vacíos, ubicación desconocida, conectividad intermitente y varios dispositivos.
- Establecer umbrales de confianza y una respuesta explícita de “desconocido” cuando la evidencia no alcance.

## Prioridades sugeridas

1. Confirmar y unificar los BSSID válidos.
2. Acordar el contrato HTTP app/backend y corregir la incompatibilidad de rutas y formatos.
3. Implementar ingestión en vivo, agrupación de lecturas, predicción y persistencia.
4. Hacer que Android llegue al backend desde la red local y probar el flujo completo.
5. Conectar el dashboard a predicciones entrantes, manteniendo separado el modo de reproducción.
6. Rehacer la evaluación sin fuga de datos y documentar instalación, configuración y operación.

## Interfaz: cómo debería funcionar en vivo

La interfaz tiene dos partes con funciones distintas: la app Android es el **capturador de mediciones**, y el dashboard web es la **vista de seguimiento**. No conviene que ambas intenten ser la misma interfaz ni que el dashboard simule una captura que no está ocurriendo.

### App Android: captura y estado del dispositivo

La app debería guiar al usuario por una sesión clara:

1. **Configurar conexión**: mostrar URL del backend y estado de conexión, con una acción explícita para probarla.
2. **Identificar dispositivo/sesión**: mantener un `device_id` y crear un identificador de sesión para asociar las mediciones.
3. **Iniciar captura**: pedir permisos, validar que Wi‑Fi y ubicación estén disponibles, y mostrar un estado visible de captura activa.
4. **Capturar y transmitir**: agrupar mediciones por ventanas de escaneo o enviar el vector completo de BSSID/RSSI; enviar lotes periódicos en lugar de una petición por cada lectura si el volumen de datos lo requiere.
5. **Mostrar estado operativo**: última lectura, redes/BSSID detectados, última transmisión, latencia, cantidad en cola y errores recuperables.
6. **Detener sesión**: cerrar la captura, vaciar la cola pendiente de forma acotada y mostrar un resumen de lecturas enviadas/fallidas.

Las etiquetas manuales de lugar son apropiadas para recolectar datos de entrenamiento y validación. En el modo de uso normal, la ubicación estimada debe venir del backend; no se debe tratar la etiqueta introducida por el usuario como si fuera una predicción.

### Dashboard web: ubicación y telemetría del sistema

El dashboard debería incluir:

- **Estado del dispositivo**: conectado/desconectado, última actualización y sesión activa.
- **Ubicación actual**: salón y punto/coordenadas estimados, hora de la última predicción y confianza.
- **Plano**: destacar el punto estimado, indicar zonas no cubiertas y diferenciar “sin datos” de “desconocido”. Evitar mostrar precisión geométrica real si las coordenadas son únicamente relativas.
- **Historial en tiempo real**: nuevas predicciones con hora, dispositivo y confianza; filtros por dispositivo o rango de tiempo si hacen falta.
- **Alertas**: reglas configurables para zonas autorizadas, pérdida de señal o confianza baja. La alerta debe basarse en datos recientes y no presentar una ubicación antigua como actual.
- **Modo demo separado**: conservar la reproducción de CSV para desarrollo, claramente marcada como simulación y sin mezclarla con los datos en vivo.

### Cómo se trabaja el flujo de interfaz y backend

Un ciclo típico de extremo a extremo sería:

```text
Android captura BSSID/RSSI
        → agrupa y envía un escaneo con device_id, session_id y timestamp
        → API valida y guarda/actualiza la sesión
        → motor k-NN calcula salón, punto, confianza y timestamp
        → Android recibe confirmación (opcionalmente la predicción)
        → dashboard consulta o recibe la predicción y actualiza el plano/historial
```

Para una primera versión basta con que el dashboard consulte `GET /api/devices/{id}/latest` cada pocos segundos. Es más fácil de implementar y depurar que WebSocket. Si se requiere menor latencia o muchos dispositivos, se puede pasar a Server-Sent Events o WebSocket. En cualquiera de las alternativas, la API debe ser la fuente de verdad: la UI no debería ejecutar una copia distinta del algoritmo.

### Orden práctico de implementación de la interfaz

1. Definir primero las vistas y estados: desconectado, conectando, capturando, predicción disponible, datos obsoletos, error y desconocido.
2. Acordar el esquema de petición y respuesta API; crear ejemplos JSON y probarlos sin UI.
3. Añadir en Android la prueba de conexión y el envío de un escaneo completo, con errores y reintentos visibles.
4. Añadir en backend una consulta para obtener la última predicción y el historial; separar claramente endpoints de demo y de producción.
5. Implementar el dashboard consumiendo esos endpoints con datos falsos antes de conectarlo a hardware.
6. Probar en la misma red con un teléfono y servidor, verificando latencia, desconexiones, datos vacíos y recuperación.

La interfaz actual de Android está construida programáticamente con vistas nativas, mientras que el dashboard está embebido como HTML/JavaScript dentro de `servidor_ips.py`. Se puede evolucionar sin reescribir todo: primero separar la lógica de API/servidor del HTML, y luego decidir si se mantiene ese dashboard ligero o se crea un frontend independiente. La prioridad inmediata no es el rediseño visual, sino que cada estado de la interfaz refleje correctamente lo que está ocurriendo en captura, transmisión y predicción.
