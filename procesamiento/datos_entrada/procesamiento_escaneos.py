"""Interfaces de integración entre la API, la predicción y la persistencia.

Este módulo no proporciona un modelo ni una base de datos. El endpoint no lo
utiliza hasta que existan implementaciones reales para ambas dependencias.
"""

from typing import Literal, Protocol, TypedDict


class Lectura(TypedDict):
    bssid: str
    rssi_dbm: float


class Escaneo(TypedDict):
    scan_id: str
    device_id: str
    session_id: str
    captured_at: str
    readings: list[Lectura]


class Prediccion(TypedDict):
    status: Literal["estimated", "unknown"]
    room: str | None
    point: str | None
    model_version: str


class UltimaPrediccion(TypedDict):
    device_id: str
    last_seen_at: str
    prediction: Prediccion


class Predictor(Protocol):
    def predecir(self, lecturas: list[Lectura]) -> Prediccion:
        """Predice una ubicación o devuelve el estado unknown."""
        ...


class RepositorioEscaneos(Protocol):
    def guardar_procesado(self, escaneo: Escaneo, prediccion: Prediccion) -> None:
        """Guarda escaneo y predicción como una sola operación consistente.

        Debe lanzar una excepción si no puede confirmar el guardado. La
        idempotencia y las excepciones concretas quedan pendientes de acuerdo.
        """
        ...

    def obtener_ultima(self, device_id: str) -> UltimaPrediccion | None:
        """Devuelve el último resultado por recepción o None si no hay datos.

        last_seen_at representa la hora UTC de recepción del servidor. Los
        errores de consulta deben propagarse, no confundirse con falta de datos.
        """
        ...


def procesar_escaneo(
    escaneo: Escaneo, predictor: Predictor, repositorio: RepositorioEscaneos
) -> Prediccion:
    """Procesa un escaneo ya validado y devuelve la predicción tras guardarla.

    Los errores de predicción y persistencia se propagan al llamador; nunca se
    devuelve una confirmación de éxito si falla alguna de las dos operaciones.
    """
    prediccion = predictor.predecir(escaneo["readings"])
    repositorio.guardar_procesado(escaneo, prediccion)
    return prediccion
