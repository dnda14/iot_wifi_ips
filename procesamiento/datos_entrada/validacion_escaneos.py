"""Validación estructural provisional del contrato de escaneos del MVP."""

from datetime import datetime, timedelta
import math


class EscaneoInvalido(ValueError):
    """El cuerpo recibido no cumple la estructura básica del contrato."""


def validar_escaneo(datos):
    """Valida la estructura mínima de un escaneo; no modifica la entrada.

    Los formatos de identificadores y BSSID, y los límites de RSSI y cantidad
    de lecturas, están pendientes de acuerdo con el equipo.
    """
    if not isinstance(datos, dict):
        raise EscaneoInvalido("El cuerpo debe ser un objeto JSON")

    for campo in ("scan_id", "device_id", "session_id", "captured_at"):
        valor = datos.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            raise EscaneoInvalido(f"{campo} debe ser una cadena no vacía")

    try:
        fecha = datetime.fromisoformat(datos["captured_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise EscaneoInvalido("captured_at debe ser una fecha ISO 8601 en UTC") from error
    if fecha.tzinfo is None or fecha.utcoffset() != timedelta(0):
        raise EscaneoInvalido("captured_at debe ser una fecha ISO 8601 en UTC")

    lecturas = datos.get("readings")
    if not isinstance(lecturas, list) or not lecturas:
        raise EscaneoInvalido("readings debe ser una lista no vacía")

    for indice, lectura in enumerate(lecturas):
        if not isinstance(lectura, dict):
            raise EscaneoInvalido(f"readings[{indice}] debe ser un objeto")
        bssid = lectura.get("bssid")
        if not isinstance(bssid, str) or not bssid.strip():
            raise EscaneoInvalido(f"readings[{indice}].bssid debe ser una cadena no vacía")
        rssi = lectura.get("rssi_dbm")
        if isinstance(rssi, bool) or not isinstance(rssi, (int, float)):
            raise EscaneoInvalido(f"readings[{indice}].rssi_dbm debe ser un número finito")
        if isinstance(rssi, float) and not math.isfinite(rssi):
            raise EscaneoInvalido(f"readings[{indice}].rssi_dbm debe ser un número finito")
