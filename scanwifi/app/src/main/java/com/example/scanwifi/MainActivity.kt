package com.example.scanwifi

import android.Manifest
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.MediaStore
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.WindowManager
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.io.BufferedWriter
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

/**
 * Registra RSSI WiFi a la MAYOR frecuencia posible.
 *
 * Fuentes (activables por separado):
 *  1) Escaneo continuo: ve TODAS las redes, pero cada escaneo real tarda unos
 *     segundos. Requiere desactivar "Limitación de búsqueda de Wi-Fi" en
 *     Opciones de desarrollador.
 *  2) RSSI de la red conectada: se consulta cada pocos cientos de ms, pero solo
 *     ve el router al que estás conectado.
 *
 * Salidas (activables por separado):
 *  - Archivo .txt (CSV) en Descargas/LPS, un archivo nuevo por cada sesión
 *    (cada vez que pulsas Iniciar). Cada línea lleva la etiqueta de "lugar".
 *  - Envío HTTP a un servidor (opcional).
 *
 * Uso típico: escribe el lugar (ej. "cocina"), pulsa Iniciar, toma datos,
 * pulsa Detener, muévete, cambia el lugar y vuelve a Iniciar. También puedes
 * cambiar el lugar con la grabación en marcha: las lecturas siguientes ya
 * llevarán la nueva etiqueta.
 */
class MainActivity : Activity() {

    private lateinit var wifi: WifiManager
    private val handler = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()       // envío al servidor
    private val fileIo = Executors.newSingleThreadExecutor()   // escritura del archivo
    private var wifiLock: WifiManager.WifiLock? = null

    private var running = false
    private var serverUrl = ""
    private var deviceId = ""
    private var useScan = true
    private var useConn = true
    private var sendEnabled = false
    private var saveEnabled = true

    // Archivo de la sesión
    private var writer: BufferedWriter? = null
    private var filePath = ""
    private val savedCount = AtomicInteger(0)
    @Volatile private var fileErrLogged = false
    @Volatile private var place = ""

    // Filtro de routers: lista de BSSID (o prefijos). Vacía = se registran todos
    private var filterList: List<String> = emptyList()
    private var lastNoUpdateLogAt = 0L

    // Para medir cada cuánto cambia realmente el valor de la red conectada
    private var lastConnRssi = Int.MIN_VALUE
    private var lastConnChangeAt = 0L
    private var changeWin = 0
    private var connPeriodMs = 500L

    // Contadores de la ventana de 5 s (solo hilo principal)
    private var scanWin = 0
    private var cacheWin = 0
    private var connWin = 0
    private var lastScanAt = 0L

    // Contadores del hilo de envío
    private val pending = AtomicInteger(0)
    private val sentOk = AtomicInteger(0)
    private val sentFail = AtomicInteger(0)
    @Volatile private var lastErrLogAt = 0L

    // Último "timestamp" visto por BSSID, para descartar resultados repetidos
    private val lastSeen = HashMap<String, Long>()

    private lateinit var etUrl: EditText
    private lateinit var etDevice: EditText
    private lateinit var etPlace: EditText
    private lateinit var etFilter: EditText
    private lateinit var etPeriod: EditText
    private lateinit var cbScan: CheckBox
    private lateinit var cbConn: CheckBox
    private lateinit var cbSave: CheckBox
    private lateinit var cbSend: CheckBox
    private lateinit var btnToggle: Button
    private lateinit var tvLive: TextView
    private lateinit var tvFile: TextView
    private lateinit var tvLog: TextView
    private lateinit var scroll: ScrollView

    private val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
    // Solo se usa desde el hilo principal
    private val stampFmt = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)

    // ───────────────────────── Escaneo continuo ─────────────────────────
    private fun logWifiDiagnostics() {
        log("Wi-Fi activado: ${wifi.isWifiEnabled}")

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                log("Throttling activo: ${wifi.isScanThrottleEnabled}")
            } catch (e: Exception) {
                log("No se pudo consultar el throttling: ${e.message}")
            }
        } else {
            log("La API de consulta del throttling no está disponible")
        }
    }
    private val scanRetry = Runnable { requestScan() }

    private val scanReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (!running || !useScan) return
            val updated = intent?.getBooleanExtra(WifiManager.EXTRA_RESULTS_UPDATED, true) ?: true
            if (updated) {
                processResults(true)
                requestScan() // encadena el siguiente escaneo de inmediato
            } else {
                // Android no hizo el escaneo pedido, pero puede tener datos recientes de sus
                // propios escaneos: los leemos igual (solo se guardan los de menos de 10 s)
                processResults(false)
                val t = System.currentTimeMillis()
                if (t - lastNoUpdateLogAt > 5000) {
                    lastNoUpdateLogAt = t
                    log("Android no dejó hacer el escaneo (resultados sin actualizar); leo su caché y reintento en 2 s")
                }
                handler.postDelayed(scanRetry, 2000)
            }
        }
    }

    private fun requestScan() {
        if (!running || !useScan) return
        handler.removeCallbacks(scanRetry)
        val ok = try {
            wifi.startScan()
        } catch (e: SecurityException) {
            false
        }
        if (ok) {
            // Vigilante: si el escaneo nunca termina, se reintenta
            handler.postDelayed(scanRetry, 12000)
        } else {
            log("startScan() rechazado; reintento en 2 s (¿throttling activo o ubicación apagada?)")
            handler.postDelayed(scanRetry, 2000)
        }
    }

    /** Edad del dato en segundos (ScanResult.timestamp está en microsegundos desde el arranque). */
    private fun ageOf(timestampUs: Long): Double =
        (SystemClock.elapsedRealtime() * 1000L - timestampUs) / 1_000_000.0

    private fun processResults(updated: Boolean) {
        val results = try {
            wifi.scanResults
        } catch (e: SecurityException) {
            log("Sin permiso de ubicación.")
            return
        }

        if (updated && results.isEmpty()) {
            log("Android devolvió 0 redes. Revisa que la UBICACIÓN del teléfono esté activada y el permiso sea \"Precisa\".")
        }

        val now = System.currentTimeMillis()
        val gap = if (lastScanAt == 0L || !updated) "" else " (+${"%.1f".format((now - lastScanAt) / 1000.0)} s)"
        if (updated) {
            lastScanAt = now
            scanWin++
        }

        // Solo registramos redes cuyo timestamp cambió (dato realmente nuevo)
        val fresh = results.filter { lastSeen[it.BSSID] != it.timestamp }
        fresh.forEach { lastSeen[it.BSSID] = it.timestamp }

        // Además, solo las que están en tu lista (si la lista está vacía, todas)
        val wantedNow = fresh.filter { wanted(it.BSSID) }

        // Solo se guardan datos recientes (≤ 10 s); los viejos de la caché no sirven para medir
        val usable = wantedNow.filter { ageOf(it.timestamp) <= 10.0 }

        if (!updated) {
            if (usable.isNotEmpty()) {
                cacheWin++
                log("Caché de Android: ${usable.size} redes recientes")
                usable.forEach {
                    val bssid = it.BSSID.lowercase(Locale.ROOT)
                    record("scan", bssid, it.SSID, it.level, it.frequency, ageOf(it.timestamp))
                    enqueue(bssid, it.level)
                }
            }
            return
        }

        val filtNote = if (filterList.isEmpty()) "" else ", ${wantedNow.size} de tu lista"
        log("Escaneo: ${fresh.size}/${results.size} redes nuevas$filtNote$gap")
        // El log muestra TODAS las redes con su BSSID, para que puedas copiar los tuyos al filtro
        val top = results.sortedByDescending { it.level }.take(5).joinToString("\n") {
            val name = if (it.SSID.isNullOrEmpty()) "(oculta)" else it.SSID
            "  $name  ${it.BSSID.lowercase(Locale.ROOT)}  ${it.frequency} MHz  ${it.level} dBm"
        }
        if (top.isNotEmpty()) log("Más fuertes:\n$top")
        if (filterList.isNotEmpty()) {
            val found = filterList.count { f ->
                results.any { it.BSSID.lowercase(Locale.ROOT).startsWith(f) }
            }
            log("Tu lista: $found de ${filterList.size} aparecen en este escaneo")
        }
        usable.forEach {
            val bssid = it.BSSID.lowercase(Locale.ROOT)
            record("scan", bssid, it.SSID, it.level, it.frequency, ageOf(it.timestamp))
            enqueue(bssid, it.level)
        }
    }

    // ───────────────────────── RSSI de la red conectada ─────────────────────────

    private val connLoop = object : Runnable {
        @Suppress("DEPRECATION")
        override fun run() {
            if (!running || !useConn) return
            val info = try {
                wifi.connectionInfo
            } catch (e: SecurityException) {
                null
            }
            if (info != null && info.networkId != -1) {
                val bssid = info.bssid
                val rssi = info.rssi
                if (bssid != null && bssid != "02:00:00:00:00:00" && rssi > -127) {
                    connWin++
                    val now = System.currentTimeMillis()
                    if (rssi != lastConnRssi) {
                        val since = if (lastConnChangeAt == 0L) "" else
                            " (cambió tras ${"%.1f".format((now - lastConnChangeAt) / 1000.0)} s)"
                        log("Conectada: $rssi dBm$since")
                        lastConnRssi = rssi
                        lastConnChangeAt = now
                        changeWin++
                    }
                    tvLive.text = "Conectada: ${info.ssid}\n${bssid.lowercase(Locale.ROOT)}\n" +
                            "RSSI: $rssi dBm   [${timeFmt.format(Date())}]"
                    val b = bssid.lowercase(Locale.ROOT)
                    if (wanted(b)) {
                        record("conn", b, info.ssid?.trim('"'), rssi, info.frequency, 0.0)
                        enqueue(b, rssi)
                    }
                }
            }
            handler.postDelayed(this, connPeriodMs)
        }
    }

    // ───────────────────────── Resumen cada 5 s ─────────────────────────

    private val statsLoop = object : Runnable {
        override fun run() {
            if (!running) return
            val sec = 5.0
            val ok = sentOk.getAndSet(0)
            val bad = sentFail.getAndSet(0)
            val sb = StringBuilder("Resumen 5 s:")
            if (useScan) {
                val each = if (scanWin > 0) "%.1f".format(sec / scanWin) else "-"
                sb.append(" escaneos=$scanWin (1 cada $each s) lecturas de caché=$cacheWin")
            }
            if (useConn) {
                sb.append(" | conectada: $connWin lecturas, $changeWin cambios de valor")
                sb.append(" (${"%.1f".format(changeWin / sec)}/s)")
            }
            if (saveEnabled) sb.append(" | guardadas=${savedCount.get()}")
            if (sendEnabled) sb.append(" | enviadas=$ok fallidas=$bad cola=${pending.get()}")
            scanWin = 0
            cacheWin = 0
            connWin = 0
            changeWin = 0
            log(sb.toString())
            updateFileLabel()
            handler.postDelayed(this, 5000)
        }
    }

    // ───────────────────────── Ciclo de vida y UI ─────────────────────────

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        buildUi()

        ContextCompat.registerReceiver(
            this,
            scanReceiver,
            IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION),
            ContextCompat.RECEIVER_NOT_EXPORTED
        )
    }

    override fun onDestroy() {
        stopReporting()
        unregisterReceiver(scanReceiver)
        fileIo.shutdown() // termina de escribir lo pendiente y cierra
        super.onDestroy()
    }

    private fun buildUi() {
        val prefs = getSharedPreferences("lps", Context.MODE_PRIVATE)
        val pad = (16 * resources.displayMetrics.density).toInt()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }

        etUrl = EditText(this).apply {
            hint = "URL del servidor (http://192.168.1.50:8000)"
            setText(prefs.getString("url", "http://192.168.1.50:8000"))
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine()
        }
        etDevice = EditText(this).apply {
            hint = "device_id"
            setText(prefs.getString("device", "celular_ramon"))
            setSingleLine()
        }
        etPlace = EditText(this).apply {
            hint = "Lugar / etiqueta (ej. cocina, pasillo, punto 3)"
            setText(prefs.getString("place", ""))
            setSingleLine()
        }
        place = etPlace.text.toString().trim()
        // Se puede cambiar con la grabación en marcha: las siguientes lecturas usan la nueva etiqueta
        etPlace.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                place = s?.toString()?.trim() ?: ""
            }
        })
        etFilter = EditText(this).apply {
            hint = "BSSID de tus routers, separados por coma o línea (vacío = todos)"
            setText(prefs.getString("filter", ""))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            minLines = 2
        }
        etPeriod = EditText(this).apply {
            hint = "Periodo de lectura de la red conectada (ms)"
            setText(prefs.getString("period", "500"))
            inputType = InputType.TYPE_CLASS_NUMBER
            setSingleLine()
        }
        cbScan = CheckBox(this).apply {
            text = "Escaneo continuo (todas las redes)"
            isChecked = prefs.getBoolean("scan", true)
        }
        cbConn = CheckBox(this).apply {
            text = "RSSI de la red conectada (rápido)"
            isChecked = prefs.getBoolean("conn", true)
        }
        cbSave = CheckBox(this).apply {
            text = "Guardar en archivo .txt (Descargas/LPS)"
            isChecked = prefs.getBoolean("save", true)
        }
        cbSend = CheckBox(this).apply {
            text = "Enviar al servidor (apagado = no envía nada)"
            isChecked = prefs.getBoolean("send", false)
        }
        btnToggle = Button(this).apply {
            text = "▶ Iniciar grabación"
            setOnClickListener { if (running) stopReporting() else startReporting() }
        }
        tvLive = TextView(this).apply {
            textSize = 18f
            text = "RSSI en vivo: sin datos todavía"
            setPadding(0, pad / 2, 0, pad / 2)
        }
        tvFile = TextView(this).apply {
            textSize = 13f
            text = "Archivo: (se crea al iniciar)"
        }
        tvLog = TextView(this).apply { textSize = 12f }
        scroll = ScrollView(this).apply { addView(tvLog) }

        root.addView(etUrl)
        root.addView(etDevice)
        root.addView(etPlace)
        root.addView(etFilter)
        root.addView(etPeriod)
        root.addView(cbScan)
        root.addView(cbConn)
        root.addView(cbSave)
        root.addView(cbSend)
        root.addView(btnToggle)
        root.addView(tvLive)
        root.addView(tvFile)
        root.addView(
            scroll,
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f)
        )
        setContentView(root)
    }

    private fun log(msg: String) {
        runOnUiThread {
            val lines = tvLog.text.toString().lines().takeLast(200)
            tvLog.text = (lines + "[${timeFmt.format(Date())}] $msg").joinToString("\n")
            scroll.post { scroll.fullScroll(ScrollView.FOCUS_DOWN) }
        }
    }

    private fun updateFileLabel() {
        tvFile.text = if (writer != null) {
            "Archivo: $filePath\nLecturas guardadas: ${savedCount.get()}   |   Lugar actual: '$place'"
        } else if (filePath.isNotEmpty()) {
            "Último archivo: $filePath\nLecturas guardadas: ${savedCount.get()}"
        } else {
            "Archivo: (se crea al iniciar)"
        }
    }

    // ───────────────────────── Control ─────────────────────────

    @Suppress("DEPRECATION")
    private fun startReporting() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION
                ),
                1
            )
            return
        }
        logWifiDiagnostics()
        serverUrl = etUrl.text.toString().trim().trimEnd('/')
        deviceId = etDevice.text.toString().trim()
        place = etPlace.text.toString().trim()
        filterList = etFilter.text.toString().lowercase(Locale.ROOT)
            .split(Regex("[,;\\s]+"))
            .filter { it.isNotBlank() }
        connPeriodMs = (etPeriod.text.toString().toLongOrNull() ?: 500L).coerceAtLeast(100L)
        useScan = cbScan.isChecked
        useConn = cbConn.isChecked
        saveEnabled = cbSave.isChecked
        sendEnabled = cbSend.isChecked

        if (!useScan && !useConn) {
            log("Activa al menos una fuente de lectura.")
            return
        }

        getSharedPreferences("lps", Context.MODE_PRIVATE).edit()
            .putString("url", serverUrl)
            .putString("device", deviceId)
            .putString("place", place)
            .putString("filter", etFilter.text.toString())
            .putString("period", etPeriod.text.toString())
            .putBoolean("scan", useScan)
            .putBoolean("conn", useConn)
            .putBoolean("save", saveEnabled)
            .putBoolean("send", sendEnabled)
            .apply()

        // Archivo nuevo por cada sesión
        savedCount.set(0)
        fileErrLogged = false
        if (saveEnabled && !openFile()) return

        // Mantiene la radio WiFi activa y con poca latencia mientras se mide
        wifiLock = try {
            val mode = if (Build.VERSION.SDK_INT >= 29) {
                WifiManager.WIFI_MODE_FULL_LOW_LATENCY
            } else {
                WifiManager.WIFI_MODE_FULL_HIGH_PERF
            }
            wifi.createWifiLock(mode, "lps:rssi").apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (e: Exception) {
            log("No se pudo activar el WifiLock (¿falta el permiso WAKE_LOCK?). Se continúa sin él.")
            null
        }

        lastSeen.clear()
        scanWin = 0
        cacheWin = 0
        connWin = 0
        lastScanAt = 0L
        lastConnRssi = Int.MIN_VALUE
        lastConnChangeAt = 0L
        changeWin = 0
        running = true
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        btnToggle.text = "■ Detener grabación"
        val dest = buildString {
            if (saveEnabled) append("guardando en archivo")
            if (sendEnabled) append(if (isEmpty()) "enviando a $serverUrl como '$deviceId'" else " + enviando a $serverUrl")
            if (isEmpty()) append("solo mostrando (sin guardar ni enviar)")
        }
        val filt = if (filterList.isEmpty()) "todos los routers" else "${filterList.size} en tu lista"
        log("Midiendo en '$place': $dest | routers: $filt | escaneo=$useScan | conectada=$useConn cada $connPeriodMs ms")
        updateFileLabel()

        if (useScan) requestScan()
        if (useConn) handler.post(connLoop)
        handler.postDelayed(statsLoop, 5000)
    }

    private fun stopReporting() {
        val wasRunning = running
        running = false
        handler.removeCallbacksAndMessages(null)
        try {
            wifiLock?.let { if (it.isHeld) it.release() }
        } catch (e: Exception) {
            // nada que hacer
        }
        wifiLock = null
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (::btnToggle.isInitialized) btnToggle.text = "▶ Iniciar grabación"
        val hadFile = writer != null
        closeFile()
        if (wasRunning) {
            log("Detenido.")
            if (hadFile) log("Archivo guardado: $filePath (${savedCount.get()} lecturas)")
        }
        if (::tvFile.isInitialized) updateFileLabel()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        val fineGranted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED
        if (requestCode == 1 && fineGranted) {
            startReporting()
        } else {
            log("Falta el permiso de ubicación precisa: elige \"Precisa\" al aceptar, o actívalo en Ajustes de la app.")
        }
    }

    // ───────────────────────── Guardado en archivo ─────────────────────────

    /**
     * Crea el archivo de la sesión.
     * Android 10+: Descargas/LPS/ (MediaStore, no necesita permisos de almacenamiento).
     * Android 9 o menor: carpeta de la app (Android/data/<paquete>/files).
     */
    private fun openFile(): Boolean {
        val name = "rssi_" + SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date()) + ".txt"
        return try {
            val out: OutputStream
            val path: String
            if (Build.VERSION.SDK_INT >= 29) {
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, name)
                    put(MediaStore.Downloads.MIME_TYPE, "text/plain")
                    put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/LPS")
                }
                val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    ?: run { log("No se pudo crear el archivo en Descargas."); return false }
                out = contentResolver.openOutputStream(uri)
                    ?: run { log("No se pudo abrir el archivo para escribir."); return false }
                path = "Descargas/LPS/$name"
            } else {
                val dir = getExternalFilesDir(null)
                    ?: run { log("No hay almacenamiento externo disponible."); return false }
                out = FileOutputStream(File(dir, name))
                path = File(dir, name).absolutePath
            }
            val w = out.bufferedWriter()
            w.write("timestamp_ms,fecha_hora,lugar,fuente,bssid,ssid,rssi_dbm,frecuencia_mhz,edad_s")
            w.newLine()
            w.flush()
            writer = w
            filePath = path
            true
        } catch (e: Exception) {
            log("No se pudo crear el archivo: ${e.message}")
            false
        }
    }

    private fun closeFile() {
        val w = writer ?: return
        writer = null
        // Va por la misma cola que las escrituras, así se cierra después de la última línea
        fileIo.execute {
            try {
                w.flush()
                w.close()
            } catch (e: Exception) {
                // nada que hacer
            }
        }
    }

    /**
     * ¿Este BSSID está en tu lista? Cada entrada puede ser el BSSID completo o solo
     * el inicio (ej. "aa:bb:cc:dd:ee:f" cubre las variantes de 2,4 y 5 GHz del mismo router).
     * Lista vacía = se aceptan todos.
     */
    private fun wanted(bssid: String): Boolean {
        if (filterList.isEmpty()) return true
        val b = bssid.lowercase(Locale.ROOT)
        return filterList.any { b.startsWith(it) }
    }

    private fun clean(s: String?): String =
        (s ?: "").replace(',', ' ').replace('"', ' ').replace('\n', ' ').replace('\r', ' ').trim()

    /** Guarda una lectura (se llama siempre desde el hilo principal). */
    private fun record(
        source: String, bssid: String, ssid: String?, rssi: Int, freq: Int, ageS: Double
    ) {
        val w = writer ?: return
        val now = System.currentTimeMillis()
        val line = listOf(
            now, stampFmt.format(Date(now)), clean(place), source, bssid, clean(ssid), rssi, freq,
            String.format(Locale.US, "%.1f", ageS.coerceAtLeast(0.0))
        ).joinToString(",")
        savedCount.incrementAndGet()
        fileIo.execute {
            try {
                w.write(line)
                w.newLine()
                w.flush()
            } catch (e: Exception) {
                if (!fileErrLogged) {
                    fileErrLogged = true
                    log("Error al escribir el archivo: ${e.message}")
                }
            }
        }
    }

    // ───────────────────────── Envío al servidor ─────────────────────────

    private fun enqueue(bssid: String, rssi: Int) {
        // Si el servidor no da abasto, se descartan lecturas en vez de acumular memoria
        if (!sendEnabled || pending.get() > 300) return
        pending.incrementAndGet()
        io.execute {
            try {
                if (send(bssid, rssi)) {
                    sentOk.incrementAndGet()
                } else {
                    sentFail.incrementAndGet()
                    val now = System.currentTimeMillis()
                    if (now - lastErrLogAt > 5000) {
                        lastErrLogAt = now
                        log("No se pudo enviar al servidor (¿URL, WiFi o servidor caído?)")
                    }
                }
            } finally {
                pending.decrementAndGet()
            }
        }
    }

    private fun send(bssid: String, rssi: Int): Boolean {
        return try {
            val conn = URL("$serverUrl/api/reading").openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.connectTimeout = 3000
            conn.readTimeout = 3000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            val body = JSONObject()
                .put("device_id", deviceId)
                .put("router_bssid", bssid)
                .put("rssi", rssi)
                .toString()
            conn.outputStream.use { it.write(body.toByteArray()) }
            val ok = conn.responseCode in 200..299
            conn.inputStream.close()
            conn.disconnect()
            ok
        } catch (e: Exception) {
            false
        }
    }
}