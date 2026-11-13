import unittest

from servidor import app


class ServidorTest(unittest.TestCase):
    def setUp(self):
        self.cliente = app.test_client()
        self.escaneo = {
            "scan_id": "scan-001",
            "device_id": "device-001",
            "session_id": "session-001",
            "captured_at": "2026-01-15T14:30:00Z",
            "readings": [{"bssid": "70:0b:01:ef:f6:26", "rssi_dbm": -61}],
        }

    def test_escaneo_valido_no_se_confirma_sin_persistencia(self):
        respuesta = self.cliente.post("/api/v1/scans", json=self.escaneo)
        self.assertEqual(respuesta.status_code, 503)
        self.assertIn("error", respuesta.get_json())

    def test_rechaza_escaneo_invalido(self):
        self.escaneo["readings"] = []
        respuesta = self.cliente.post("/api/v1/scans", json=self.escaneo)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("readings", respuesta.get_json()["error"])

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
