import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..database import ScanConflict
from ..schemas import LegacyReading, Reading, ScanIn

router = APIRouter()


@router.post("/api/v1/scans", tags=["scans"])
async def create_scan(scan: ScanIn, request: Request):
    service = request.app.state.service
    data = scan.model_dump(mode="json")
    try:
        record, created = service.process(data)
    except ScanConflict:
        raise HTTPException(409, "scan_id existente con contenido diferente")
    except sqlite3.Error:
        raise HTTPException(503, "No se pudo guardar el escaneo")
    return JSONResponse({"scan_id": record["scan_id"], "status": "processed",
                         "prediction": record["prediction"]},
                        status_code=201 if created else 200)


@router.post("/api/reading", tags=["compatibility"], deprecated=True)
async def create_legacy_reading(reading: LegacyReading, request: Request):
    # La app Android actual envía una lectura por petición.
    try:
        validated = Reading(bssid=reading.router_bssid, rssi_dbm=reading.rssi)
    except ValidationError:
        raise HTTPException(422, "BSSID o RSSI inválido")
    try:
        return request.app.state.service.process_legacy(
            reading.device_id, validated.bssid, validated.rssi_dbm)
    except sqlite3.Error:
        raise HTTPException(503, "No se pudo guardar la lectura")
