from fastapi import APIRouter, Request

from ..service import WINDOW_SECONDS, legacy_position

router = APIRouter(tags=["compatibility"])


@router.get("/api/estado", deprecated=True)
async def status(request: Request):
    predictor = request.app.state.service.predictor
    return {"listo": True, "referencias": len(predictor.references),
            "bssids": len(predictor.bssids), "lista_bssids": predictor.bssids,
            "plano": predictor.layout(), "puerto": 8000,
            "ventana_segundos": WINDOW_SECONDS, "min_aps": 2}


@router.get("/api/ubicacion", deprecated=True)
async def locations(request: Request):
    service = request.app.state.service
    records = service.database.devices()
    positions = {row["device_id"]: legacy_position(row) for row in records}
    positions = {key: value for key, value in positions.items() if value is not None}
    diagnostics, reading_count = service.diagnostic_snapshot()
    for row in records:
        device = row["device_id"]
        if device not in diagnostics:
            diagnostics[device] = {"lecturas": 0, "conocidas": 0, "desconocidas": 0,
                                   "aps_ventana": row["prediction"]["aps"],
                                   "ultima_lectura_iso": row["received_at"],
                                   "ultimo_bssid": "", "bssid_reconocido": True}
    last = service.database.history(limit=1)
    return {"ultima": legacy_position(last[0]) if last else None,
            "ubicaciones": positions, "dispositivos": [r["device_id"] for r in records],
            "diagnostico": diagnostics, "lecturas": reading_count}


@router.get("/api/historial", deprecated=True)
async def history(request: Request):
    rows = request.app.state.service.database.history(limit=50)
    return [{"fecha": row["received_at"], "dispositivo": row["device_id"],
             "salon": row["prediction"]["room"], "punto": row["prediction"]["point"],
             "zona": row["prediction"]["zone"], "aps": row["prediction"]["aps"],
             "confianza": row["prediction"]["confidence"]}
            for row in rows if row["prediction"]["status"] == "estimated"]
