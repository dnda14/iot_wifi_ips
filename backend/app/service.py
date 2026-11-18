import hashlib
import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from .database import Database
from .prediction import Predictor

WINDOW_SECONDS = 15.0


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ScanService:
    def __init__(self, database: Database, predictor: Predictor):
        self.database = database
        self.predictor = predictor
        self.lock = threading.RLock()
        self.windows = defaultdict(dict)
        self.diagnostics = {}
        self.reading_count = 0

    def process(self, scan: dict, source="v1"):
        # El hash se calcula después de normalizar, con orden de BSSID estable.
        canonical = dict(scan)
        canonical["readings"] = sorted(scan["readings"], key=lambda item: item["bssid"])
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
        prediction = self.predictor.predict({item["bssid"]: item["rssi_dbm"]
                                             for item in scan["readings"]})
        return self.database.save(scan, digest, prediction, utc_now(), source)

    def process_legacy(self, device_id: str, bssid: str, rssi: float):
        now = time.monotonic()
        with self.lock:
            self.reading_count += 1
            known = bssid in self.predictor.bssids
            stats = self.diagnostics.setdefault(device_id, {
                "lecturas": 0, "conocidas": 0, "desconocidas": 0,
                "ultima_lectura_iso": "", "ultimo_bssid": "", "bssid_reconocido": False,
            })
            stats["lecturas"] += 1
            stats["conocidas" if known else "desconocidas"] += 1
            stats["ultima_lectura_iso"] = utc_now()
            stats["ultimo_bssid"] = bssid
            stats["bssid_reconocido"] = known
            window = self.windows[device_id]
            for name, (_, timestamp) in list(window.items()):
                if now - timestamp > WINDOW_SECONDS:
                    del window[name]
            if not known:
                return {"estado": "recibido", "usado": False, "dispositivo": device_id,
                        "motivo": "BSSID fuera del fingerprint"}
            window[bssid] = (rssi, now)
            if len(window) < 2:
                return {"estado": "recibido", "usado": True, "dispositivo": device_id,
                        "aps": len(window), "esperando": "mas BSSID conocidos"}
            captured = utc_now()
            scan = {"scan_id": str(uuid4()), "device_id": device_id,
                    "session_id": "legacy:" + device_id, "captured_at": captured,
                    "readings": [{"bssid": name, "rssi_dbm": value}
                                 for name, (value, _) in window.items()]}
            record, _ = self.process(scan, "legacy")
            return {"estado": "recibido", "usado": True,
                    "ubicacion": legacy_position(record)}

    def diagnostic_snapshot(self):
        with self.lock:
            now = time.monotonic()
            result = {device: dict(stats, aps_ventana=sum(
                now - stamp <= WINDOW_SECONDS for _, stamp in self.windows[device].values()))
                for device, stats in self.diagnostics.items()}
            return result, self.reading_count


def legacy_position(record):
    prediction = record["prediction"]
    if prediction["status"] != "estimated":
        return None
    return {"dispositivo": record["device_id"], "salon": prediction["room"],
            "punto": prediction["point"], "zona": prediction["zone"],
            "confianza": prediction["confidence"], "aps": prediction["aps"],
            "fecha_iso": record["received_at"]}
