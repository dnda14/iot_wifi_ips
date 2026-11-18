import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINGERPRINT_PATH = Path(os.getenv(
    "IPS_FINGERPRINT_PATH", ROOT / "procesamiento/datos_entrada/fingerprint.csv"
))
DATABASE_PATH = Path(os.getenv(
    "IPS_DATABASE_PATH", ROOT / "backend/data/ips.sqlite3"
))
WEB_PATH = ROOT / "web-admin"
MODEL_VERSION = "knn-v1"
