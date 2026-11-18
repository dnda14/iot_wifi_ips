import sqlite3
from contextlib import contextmanager
from pathlib import Path


class ScanConflict(Exception):
    """Un scan_id existente llegó con contenido distinto."""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS scans (
                    scan_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    room TEXT,
                    point INTEGER,
                    zone TEXT,
                    confidence REAL,
                    aps INTEGER NOT NULL,
                    model_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS readings (
                    scan_id TEXT NOT NULL REFERENCES scans(scan_id),
                    bssid TEXT NOT NULL,
                    rssi_dbm REAL NOT NULL,
                    PRIMARY KEY (scan_id, bssid)
                );
                CREATE INDEX IF NOT EXISTS scans_device_time
                    ON scans(device_id, received_at DESC);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    def save(self, scan: dict, payload_hash: str, prediction: dict, received_at: str,
             source: str = "v1") -> tuple[dict, bool]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute("SELECT * FROM scans WHERE scan_id=?", (scan["scan_id"],)).fetchone()
                if existing:
                    if existing["payload_hash"] != payload_hash:
                        raise ScanConflict()
                    db.commit()
                    return self._record(existing), False
                db.execute("""
                    INSERT INTO scans (scan_id, device_id, session_id, captured_at,
                        received_at, payload_hash, source, status, room, point, zone,
                        confidence, aps, model_version)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (scan["scan_id"], scan["device_id"], scan["session_id"],
                      scan["captured_at"], received_at, payload_hash, source,
                      prediction["status"], prediction["room"], prediction["point"],
                      prediction["zone"], prediction["confidence"], prediction["aps"],
                      prediction["model_version"]))
                db.executemany("INSERT INTO readings (scan_id,bssid,rssi_dbm) VALUES (?,?,?)",
                               [(scan["scan_id"], item["bssid"], item["rssi_dbm"])
                                for item in scan["readings"]])
                row = db.execute("SELECT * FROM scans WHERE scan_id=?", (scan["scan_id"],)).fetchone()
                db.commit()
                return self._record(row), True
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _record(row):
        return {"scan_id": row["scan_id"], "device_id": row["device_id"],
                "session_id": row["session_id"], "captured_at": row["captured_at"],
                "received_at": row["received_at"],
                "prediction": {"status": row["status"], "room": row["room"],
                               "point": row["point"], "zone": row["zone"],
                               "confidence": row["confidence"], "aps": row["aps"],
                               "model_version": row["model_version"]}}

    def latest(self, device_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM scans WHERE device_id=? ORDER BY received_at DESC, rowid DESC LIMIT 1",
                             (device_id,)).fetchone()
            return self._record(row) if row else None

    def devices(self):
        with self.connect() as db:
            ids = [row[0] for row in db.execute("SELECT DISTINCT device_id FROM scans ORDER BY device_id")]
        return [self.latest(device_id) for device_id in ids]

    def history(self, device_id=None, limit=50):
        query = "SELECT * FROM scans"
        params = []
        if device_id is not None:
            query += " WHERE device_id=?"
            params.append(device_id)
        query += " ORDER BY received_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        with self.connect() as db:
            return [self._record(row) for row in db.execute(query, params)]

    def count(self):
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
