import csv
import math
from collections import defaultdict
from pathlib import Path

from .config import MODEL_VERSION

ABSENT = -100.0
MIN_APS = 2


class Predictor:
    def __init__(self, path: Path):
        if not path.is_file():
            raise FileNotFoundError(f"No existe el fingerprint: {path}")
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            self.bssids = [name.lower() for name in (reader.fieldnames or [])
                           if name.count(":") == 5]
            self.references = []
            for row in reader:
                try:
                    signals = {b: float(row[b]) for b in self.bssids}
                    if not all(math.isfinite(v) for v in signals.values()):
                        continue
                    self.references.append({
                        "salon": row["salon"].strip(), "punto": int(row["punto"]),
                        "zona": row.get("zona", "").strip(), "signals": signals,
                    })
                except (KeyError, TypeError, ValueError):
                    continue
        if not self.bssids or not self.references:
            raise ValueError("El fingerprint no contiene referencias válidas")

    def predict(self, readings: dict[str, float]) -> dict:
        signals = {b: value for b, value in readings.items() if b in self.bssids}
        if len(signals) < MIN_APS:
            return {"status": "unknown", "room": None, "point": None,
                    "zone": None, "confidence": None, "aps": len(signals),
                    "model_version": MODEL_VERSION}
        candidates = []
        for ref in self.references:
            overlap = [(value, ref["signals"][b]) for b, value in signals.items()
                       if ref["signals"].get(b, ABSENT) > ABSENT]
            if len(overlap) < MIN_APS:
                continue
            distance = math.sqrt(sum((a - b) ** 2 for a, b in overlap) / len(overlap))
            candidates.append((distance, ref))
        if not candidates:
            return {"status": "unknown", "room": None, "point": None,
                    "zone": None, "confidence": None, "aps": len(signals),
                    "model_version": MODEL_VERSION}
        candidates.sort(key=lambda pair: pair[0])
        votes = defaultdict(float)
        for distance, ref in candidates[:3]:
            votes[(ref["salon"], ref["punto"], ref["zona"])] += 1 / (distance + 0.001)
        (room, point, zone), weight = max(votes.items(), key=lambda pair: pair[1])
        return {"status": "estimated", "room": room, "point": point,
                "zone": zone, "confidence": round(weight / sum(votes.values()), 3),
                "aps": len(signals), "model_version": MODEL_VERSION}

    def layout(self):
        result = {}
        for ref in self.references:
            room = ref["salon"]
            lanes = result.setdefault(room, {"interior": [], "pasillo": []})
            lane = "pasillo" if "pasillo" in ref["zona"].lower() or ref["punto"] >= 10 else "interior"
            if ref["punto"] not in lanes[lane]:
                lanes[lane].append(ref["punto"])
        for lanes in result.values():
            for points in lanes.values():
                points.sort()
        return result
