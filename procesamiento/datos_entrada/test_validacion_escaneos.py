import copy
import unittest

from validacion_escaneos import EscaneoInvalido, validar_escaneo


class ValidacionEscaneosTest(unittest.TestCase):
    def setUp(self):
        self.escaneo = {
            "scan_id": "scan-001",
            "device_id": "device-001",
            "session_id": "session-001",
            "captured_at": "2026-01-15T14:30:00Z",
            "readings": [{"bssid": "70:0b:01:ef:f6:26", "rssi_dbm": -61}],
        }

    def test_acepta_un_escaneo_valido_sin_modificarlo(self):
        original = copy.deepcopy(self.escaneo)
        validar_escaneo(self.escaneo)
        self.assertEqual(self.escaneo, original)

    def test_rechaza_cuerpos_que_no_son_objetos(self):
        for cuerpo in (None, [], "texto", 1):
            with self.subTest(cuerpo=cuerpo), self.assertRaises(EscaneoInvalido):
                validar_escaneo(cuerpo)

    def test_rechaza_identificadores_ausentes_o_vacios(self):
        for campo in ("scan_id", "device_id", "session_id"):
            for valor in (None, " ", 42):
                with self.subTest(campo=campo, valor=valor):
                    self.escaneo[campo] = valor
                    with self.assertRaises(EscaneoInvalido):
                        validar_escaneo(self.escaneo)
                    self.setUp()

    def test_valida_fecha_utc(self):
        for fecha in (None, "", "no es fecha", "2026-01-15T14:30:00", "2026-01-15T14:30:00-05:00"):
            with self.subTest(fecha=fecha):
                self.escaneo["captured_at"] = fecha
                with self.assertRaises(EscaneoInvalido):
                    validar_escaneo(self.escaneo)
        self.escaneo["captured_at"] = "2026-01-15T14:30:00+00:00"
        validar_escaneo(self.escaneo)

    def test_rechaza_lista_de_lecturas_invalida(self):
        for lecturas in (None, [], {}, "texto"):
            with self.subTest(lecturas=lecturas):
                self.escaneo["readings"] = lecturas
                with self.assertRaises(EscaneoInvalido):
                    validar_escaneo(self.escaneo)

    def test_rechaza_lecturas_invalidas(self):
        for lectura in (None, {}, {"bssid": " ", "rssi_dbm": -61},
                        {"bssid": "aa", "rssi_dbm": True},
                        {"bssid": "aa", "rssi_dbm": "-61"},
                        {"bssid": "aa", "rssi_dbm": float("nan")},
                        {"bssid": "aa", "rssi_dbm": float("inf")}):
            with self.subTest(lectura=lectura):
                self.escaneo["readings"] = [lectura]
                with self.assertRaises(EscaneoInvalido):
                    validar_escaneo(self.escaneo)


if __name__ == "__main__":
    unittest.main()
