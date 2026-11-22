"""'Device is close' detection from RSSI (pure logic, no I/O).

Per device (MAC):
- Smooth with the mean of the last 2 readings (a single reading counts as-is, so a device that
  appears already near alerts on its first poll).
- Alert when that mean is >= near_dbm (e.g. -50 means -50, -45, -40 ...).
- After alerting, stay silent until re-armed: the smoothed RSSI has been below rearm_dbm
  continuously for rearm_seconds, or the device left the node (its state is dropped).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .detector import Station


@dataclass
class _State:
    readings: deque = field(default_factory=lambda: deque(maxlen=2))
    armed: bool = True
    below_since: float | None = None


class NearDetector:
    def __init__(self, near_dbm: int = -50, rearm_dbm: int = -60, rearm_seconds: float = 30.0):
        if rearm_dbm >= near_dbm:
            raise ValueError(f"REARM_DBM ({rearm_dbm}) must be weaker (lower) than NEAR_DBM ({near_dbm})")
        self.near, self.rearm, self.rearm_s = near_dbm, rearm_dbm, rearm_seconds
        self._st: dict[str, _State] = {}

    def update(self, stations: list[Station], now: float) -> list[tuple[Station, int]]:
        """Return [(station, smoothed_rssi)] for devices that just came close."""
        present = {s.mac.lower() for s in stations}
        for mac in list(self._st):
            if mac not in present:
                del self._st[mac]          # left the node: re-armed when it comes back
        alerts = []
        for s in stations:
            # wl reports 0 / nothing when it has no valid reading; ignore those samples.
            if s.rssi is None or s.rssi >= 0:
                continue
            st = self._st.setdefault(s.mac.lower(), _State())
            st.readings.append(s.rssi)
            avg = sum(st.readings) / len(st.readings)
            if st.armed:
                if avg >= self.near:
                    st.armed = False
                    st.below_since = None
                    alerts.append((s, round(avg)))
            elif avg < self.rearm:
                if st.below_since is None:
                    st.below_since = now
                if now - st.below_since >= self.rearm_s:
                    st.armed, st.below_since = True, None
            else:
                st.below_since = None      # came back above the re-arm level: restart the 30 s timer
        return alerts
