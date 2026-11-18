from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bssid: str = Field(pattern=r"^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$")
    rssi_dbm: float = Field(ge=-120, le=0, allow_inf_nan=False)

    @field_validator("bssid", mode="before")
    @classmethod
    def normalize_bssid(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class ScanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scan_id: str = Field(min_length=1, max_length=80)
    device_id: str = Field(min_length=1, max_length=80)
    session_id: UUID
    captured_at: datetime
    readings: list[Reading] = Field(min_length=1, max_length=100)

    @field_validator("scan_id", "device_id")
    @classmethod
    def nonblank_id(cls, value):
        if not value.strip():
            raise ValueError("el identificador no puede estar vacío")
        return value.strip()

    @field_validator("captured_at")
    @classmethod
    def require_timezone(cls, value):
        if value.utcoffset() is None:
            raise ValueError("captured_at debe incluir zona horaria")
        return value

    @model_validator(mode="after")
    def unique_bssids(self):
        names = [reading.bssid for reading in self.readings]
        if len(names) != len(set(names)):
            raise ValueError("BSSID duplicado en el escaneo")
        return self


class LegacyReading(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    router_bssid: str
    rssi: float = Field(ge=-120, le=0, allow_inf_nan=False)

    @field_validator("device_id")
    @classmethod
    def nonblank_device(cls, value):
        if not value.strip():
            raise ValueError("device_id no puede estar vacío")
        return value.strip()

    @field_validator("router_bssid", mode="before")
    @classmethod
    def normalize_bssid(cls, value):
        return value.strip().lower() if isinstance(value, str) else value
