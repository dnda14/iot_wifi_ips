import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.main import create_app
from app.config import FINGERPRINT_PATH, WEB_PATH


def scan(scan_id="scan-1", device="phone-1", session=None):
    return {
        "scan_id": scan_id, "device_id": device,
        "session_id": str(session or uuid4()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "readings": [
            {"bssid": "30:b5:c2:ef:3e:f0", "rssi_dbm": -52},
            {"bssid": "70:0b:01:ef:f6:26", "rssi_dbm": -56},
        ],
    }


async def with_client(app, test):
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as client:
            await test(client)


def test_scan_persists_and_retries_without_duplication(tmp_path):
    app = create_app(tmp_path / "ips.sqlite3", FINGERPRINT_PATH, WEB_PATH)
    async def check(client):
        body = scan()
        first = await client.post("/api/v1/scans", json=body)
        assert first.status_code == 201
        assert first.json()["prediction"]["status"] == "estimated"
        retry = await client.post("/api/v1/scans", json=body)
        assert retry.status_code == 200
        assert retry.json() == first.json()
        assert len((await client.get("/api/v1/devices/phone-1/history")).json()) == 1
        latest = (await client.get("/api/v1/devices/phone-1/latest")).json()
        assert latest["scan_id"] == body["scan_id"]
        changed = dict(body, readings=[{"bssid": "30:b5:c2:ef:3e:f0", "rssi_dbm": -80}])
        assert (await client.post("/api/v1/scans", json=changed)).status_code == 409
    asyncio.run(with_client(app, check))
    async def after_restart(client):
        assert (await client.get("/api/v1/devices/phone-1/latest")).json()["scan_id"] == "scan-1"
    asyncio.run(with_client(create_app(tmp_path / "ips.sqlite3", FINGERPRINT_PATH, WEB_PATH), after_restart))


def test_unknown_validation_and_separate_devices(tmp_path):
    app = create_app(tmp_path / "ips.sqlite3", FINGERPRINT_PATH, WEB_PATH)
    async def check(client):
        first = scan("a", "phone-a")
        first["readings"] = first["readings"][:1]
        assert (await client.post("/api/v1/scans", json=first)).json()["prediction"]["status"] == "unknown"
        assert (await client.post("/api/v1/scans", json=scan("b", "phone-b"))).status_code == 201
        assert len((await client.get("/api/v1/devices")).json()) == 2
        invalid = scan("c")
        invalid["readings"] = []
        assert (await client.post("/api/v1/scans", json=invalid)).status_code == 422
        assert (await client.get("/api/v1/devices/missing/latest")).status_code == 404
    asyncio.run(with_client(app, check))


def test_legacy_android_and_dashboard(tmp_path):
    app = create_app(tmp_path / "ips.sqlite3", FINGERPRINT_PATH, WEB_PATH)
    async def check(client):
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/static/js/app.js")).status_code == 200
        assert (await client.get("/api/v1/meta")).json()["bssids"] == 7
        unknown = await client.post("/api/reading", json={
            "device_id": "unmapped-phone", "router_bssid": "aa:bb:cc:dd:ee:ff", "rssi": -60})
        assert unknown.json()["usado"] is False
        assert "unmapped-phone" in (await client.get("/api/v1/diagnostics")).json()["devices"]
        for bssid, rssi in [("30:b5:c2:ef:3e:f0", -52), ("70:0b:01:ef:f6:26", -56)]:
            response = await client.post("/api/reading", json={
                "device_id": "old-phone", "router_bssid": bssid, "rssi": rssi})
            assert response.status_code == 200
        assert response.json()["ubicacion"]["salon"] == "301"
        assert "old-phone" in (await client.get("/api/ubicacion")).json()["ubicaciones"]
        assert (await client.get("/api/historial")).json()[0]["dispositivo"] == "old-phone"
    asyncio.run(with_client(app, check))
