from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Station:
    mac: str
    band: str       # "2.4 GHz" / "5 GHz"
    rssi: int | None
