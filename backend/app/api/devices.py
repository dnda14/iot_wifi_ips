from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/v1", tags=["devices"])


@router.get("/devices")
async def list_devices(request: Request):
    return request.app.state.service.database.devices()


@router.get("/meta", tags=["system"])
async def metadata(request: Request):
    predictor = request.app.state.service.predictor
    return {"model_version": "knn-v1", "references": len(predictor.references),
            "bssids": len(predictor.bssids), "layout": predictor.layout()}


@router.get("/diagnostics", tags=["system"])
async def diagnostics(request: Request):
    snapshot, readings = request.app.state.service.diagnostic_snapshot()
    return {"devices": snapshot, "readings": readings}


@router.get("/history", tags=["history"])
async def global_history(request: Request, limit: int = Query(50, ge=1, le=200)):
    return request.app.state.service.database.history(limit=limit)


@router.get("/devices/{device_id}/latest")
async def latest(device_id: str, request: Request):
    row = request.app.state.service.database.latest(device_id)
    if row is None:
        raise HTTPException(404, "Dispositivo sin escaneos")
    return row


@router.get("/devices/{device_id}/history")
async def history(device_id: str, request: Request, limit: int = Query(50, ge=1, le=200)):
    return request.app.state.service.database.history(device_id, limit)
