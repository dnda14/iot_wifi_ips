import unittest
from unittest.mock import Mock

from servidor import app


class ServidorTest(unittest.TestCase):
    def setUp(self):
        self.config_original = dict(app.config)
        self.addCleanup(self.restaurar_configuracion)
        app.config.pop("PREDICTOR", None)
        app.config.pop("REPOSITORIO_ESCANEOS", None)
        self.cliente = app.test_client()
        self.escaneo = {
            "scan_id": "scan-001",
            "device_id": "device-001",
            "session_id": "session-001",
            "captured_at": "2026-01-15T14:30:00Z",
            "readings": [{"bssid": "70:0b:01:ef:f6:26", "rssi_dbm": -61}],
        }

    def restaurar_configuracion(self):
        app.config.clear()
        app.config.update(self.config_original)

    def configurar_dependencias(self):
        predictor = Mock()
        predictor.predecir.return_value = {
            "status": "estimated", "room": "Lab 3", "point": "4",
            "model_version": "mock-v1",
        }
        repositorio = Mock()
        app.config["PREDICTOR"] = predictor
        app.config["REPOSITORIO_ESCANEOS"] = repositorio
        return predictor, repositorio

    def test_escaneo_valido_no_se_confirma_sin_persistencia(self):
        respuesta = self.cliente.post("/api/v1/scans", json=self.escaneo)
        self.assertEqual(respuesta.status_code, 503)
        self.assertIn("error", respuesta.get_json())

    def test_requiere_ambas_dependencias(self):
        for clave in ("PREDICTOR", "REPOSITORIO_ESCANEOS"):
            with self.subTest(clave=clave):
                app.config.pop("PREDICTOR", None)
                app.config.pop("REPOSITORIO_ESCANEOS", None)
                app.config[clave] = Mock()
                respuesta = self.cliente.post("/api/v1/scans", json=self.escaneo)
                self.assertEqual(respuesta.status_code, 503)

    def test_procesa_y_confirma_tras_el_guardado(self):
        predictor, repositorio = self.configurar_dependencias()
        respuesta = self.cliente.post("/api/v1/scans", json=self.escaneo)
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.get_json(), {
            "scan_id": "scan-001", "status": "processed",
            "prediction": predictor.predecir.return_value,
        })
        predictor.predecir.assert_called_once_with(self.escaneo["readings"])
        repositorio.guardar_procesado.assert_called_once_with(
            self.escaneo, predictor.predecir.return_value
        )

    def test_devuelve_ubicacion_desconocida(self):
        predictor, repositorio = self.configurar_dependencias()
        predictor.predecir.return_value = {
            "status": "unknown", "room": None, "point": None,
            "model_version": "mock-v1",
        }
        respuesta = self.cliente.post("/api/v1/scans", json=self.escaneo)
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.get_json()["prediction"]["status"], "unknown")
        repositorio.guardar_procesado.assert_called_once()

    def test_falla_modelo_o_guardado_sin_confirmar_exito(self):
        for componente in ("modelo", "guardado"):
            with self.subTest(componente=componente):
                predictor, repositorio = self.configurar_dependencias()
                if componente == "modelo":
                    predictor.predecir.side_effect = RuntimeError("detalle privado")
                else:
                    repositorio.guardar_procesado.side_effect = RuntimeError("detalle privado")
                with self.assertLogs(app.logger, level="ERROR"):
                    respuesta = self.cliente.post("/api/v1/scans", json=self.escaneo)
                self.assertEqual(respuesta.status_code, 503)
                self.assertNotIn("detalle privado", respuesta.get_data(as_text=True))
                if componente == "modelo":
                    repositorio.guardar_procesado.assert_not_called()

    def test_rechaza_escaneo_invalido(self):
        self.escaneo["readings"] = []
        respuesta = self.cliente.post("/api/v1/scans", json=self.escaneo)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("readings", respuesta.get_json()["error"])

    def test_rechaza_escaneo_sin_sesion(self):
        del self.escaneo["session_id"]
        respuesta = self.cliente.post("/api/v1/scans", json=self.escaneo)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("session_id", respuesta.get_json()["error"])

    def test_rechaza_json_malformado(self):
        respuesta = self.cliente.post(
            "/api/v1/scans", data="{", content_type="application/json"
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("error", respuesta.get_json())

    def test_conserva_endpoint_anterior(self):
        respuesta = self.cliente.post("/api/mediciones", json={"mediciones": []})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()["cantidad"], 0)


if __name__ == "__main__":
    unittest.main()
