import unittest
from unittest.mock import Mock

from procesamiento_escaneos import procesar_escaneo


class ProcesamientoEscaneosTest(unittest.TestCase):
    def setUp(self):
        self.escaneo = {
            "scan_id": "scan-001",
            "device_id": "device-001",
            "session_id": "session-001",
            "captured_at": "2026-01-15T14:30:00Z",
            "readings": [{"bssid": "70:0b:01:ef:f6:26", "rssi_dbm": -61}],
        }
        self.prediccion = {
            "status": "estimated",
            "room": "Lab 3",
            "point": "4",
            "model_version": "mock-v1",
        }
        self.predictor = Mock()
        self.predictor.predecir.return_value = self.prediccion
        self.repositorio = Mock()

    def test_predice_guarda_y_devuelve_el_resultado(self):
        resultado = procesar_escaneo(self.escaneo, self.predictor, self.repositorio)

        self.predictor.predecir.assert_called_once_with(self.escaneo["readings"])
        self.repositorio.guardar_procesado.assert_called_once_with(
            self.escaneo, self.prediccion
        )
        self.assertEqual(resultado, self.prediccion)

    def test_guarda_tambien_una_ubicacion_desconocida(self):
        self.prediccion.update(status="unknown", room=None, point=None)

        resultado = procesar_escaneo(self.escaneo, self.predictor, self.repositorio)

        self.assertEqual(resultado["status"], "unknown")
        self.repositorio.guardar_procesado.assert_called_once_with(
            self.escaneo, self.prediccion
        )

    def test_no_guarda_si_falla_la_prediccion(self):
        self.predictor.predecir.side_effect = RuntimeError("modelo no disponible")

        with self.assertRaisesRegex(RuntimeError, "modelo no disponible"):
            procesar_escaneo(self.escaneo, self.predictor, self.repositorio)
        self.repositorio.guardar_procesado.assert_not_called()

    def test_no_confirma_si_falla_el_guardado(self):
        self.repositorio.guardar_procesado.side_effect = RuntimeError("falló el guardado")

        with self.assertRaisesRegex(RuntimeError, "falló el guardado"):
            procesar_escaneo(self.escaneo, self.predictor, self.repositorio)


if __name__ == "__main__":
    unittest.main()
