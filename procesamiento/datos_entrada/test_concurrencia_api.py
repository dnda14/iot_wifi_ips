"""Prueba HTTP local: 50 clientes en paralelo con dependencias simuladas."""

from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import json
from statistics import median
import threading
import time
import unittest

from werkzeug.serving import WSGIRequestHandler, make_server

from servidor import app


CLIENTES = 50


class PredictorSimulado:
    def predecir(self, lecturas):
        return {
            "status": "unknown", "room": None, "point": None,
            "model_version": "mock-concurrencia",
        }


class RepositorioSimulado:
    """Registra IDs en memoria solo para comprobar aislamiento entre peticiones."""

    def __init__(self):
        self.ids = []
        self.lock = threading.Lock()

    def guardar_procesado(self, escaneo, prediccion):
        with self.lock:
            self.ids.append(escaneo["scan_id"])


class ManejadorSilencioso(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        pass


class ConcurrenciaApiTest(unittest.TestCase):
    def test_cincuenta_solicitudes_http_en_paralelo(self):
        config_original = dict(app.config)
        repositorio = RepositorioSimulado()
        app.config["PREDICTOR"] = PredictorSimulado()
        app.config["REPOSITORIO_ESCANEOS"] = repositorio
        try:
            servidor = make_server(
                "127.0.0.1", 0, app, threaded=True,
                request_handler=ManejadorSilencioso,
            )
            hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
            hilo.start()
            try:
                barrera = threading.Barrier(CLIENTES, timeout=30)

                def enviar(indice):
                    escaneo = {
                        "scan_id": f"scan-{indice:03d}",
                        "device_id": f"device-{indice:03d}",
                        "session_id": f"session-{indice:03d}",
                        "captured_at": "2026-01-15T14:30:00Z",
                        "readings": [{"bssid": "70:0b:01:ef:f6:26", "rssi_dbm": -61}],
                    }
                    barrera.wait()
                    inicio = time.perf_counter()
                    conexion = HTTPConnection("127.0.0.1", servidor.server_port, timeout=30)
                    try:
                        conexion.request(
                            "POST", "/api/v1/scans", body=json.dumps(escaneo),
                            headers={"Content-Type": "application/json"},
                        )
                        respuesta = conexion.getresponse()
                        datos = json.loads(respuesta.read())
                        return respuesta.status, datos.get("scan_id"), time.perf_counter() - inicio
                    finally:
                        conexion.close()

                inicio_total = time.perf_counter()
                with ThreadPoolExecutor(max_workers=CLIENTES) as ejecutor:
                    resultados = list(ejecutor.map(enviar, range(CLIENTES)))
                duracion = time.perf_counter() - inicio_total
            finally:
                servidor.shutdown()
                hilo.join(timeout=5)
                servidor.server_close()
        finally:
            app.config.clear()
            app.config.update(config_original)

        errores = sum(estado != 201 for estado, _, _ in resultados)
        tiempos_ms = sorted(tiempo * 1000 for _, _, tiempo in resultados)
        print(
            f"\nConcurrencia HTTP simulada: {CLIENTES} solicitudes, "
            f"{errores} errores, total {duracion:.3f} s, "
            f"latencia mediana {median(tiempos_ms):.1f} ms, "
            f"máxima {tiempos_ms[-1]:.1f} ms"
        )
        self.assertEqual(errores, 0)
        ids_esperados = {f"scan-{indice:03d}" for indice in range(CLIENTES)}
        self.assertEqual({scan_id for _, scan_id, _ in resultados}, ids_esperados)
        self.assertEqual(len(repositorio.ids), CLIENTES)
        self.assertEqual(set(repositorio.ids), ids_esperados)


if __name__ == "__main__":
    unittest.main()
