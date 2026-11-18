from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

from .api import compatibility, devices, scans
from .config import DATABASE_PATH, FINGERPRINT_PATH, WEB_PATH
from .database import Database
from .prediction import Predictor
from .service import ScanService


def create_app(database_path: Path = DATABASE_PATH,
               fingerprint_path: Path = FINGERPRINT_PATH,
               web_path: Path = WEB_PATH) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.service = ScanService(Database(database_path), Predictor(fingerprint_path))
        yield

    application = FastAPI(title="Wi-Fi IPS API", version="0.1.0", lifespan=lifespan)
    application.include_router(scans.router)
    application.include_router(devices.router)
    application.include_router(compatibility.router)
    assets = {
        "css/app.css": ("text/css", (web_path / "css/app.css").read_bytes()),
        "js/app.js": ("application/javascript", (web_path / "js/app.js").read_bytes()),
    }
    admin_html = (web_path / "index.html").read_text(encoding="utf-8")

    @application.get("/static/{asset_path:path}", include_in_schema=False)
    async def static_asset(asset_path: str):
        from fastapi import HTTPException
        if asset_path not in assets:
            raise HTTPException(404)
        content_type, content = assets[asset_path]
        return Response(content, media_type=content_type)

    @application.get("/", include_in_schema=False)
    async def admin():
        return HTMLResponse(admin_html)

    return application


app = create_app()
