"""Whole-house movement tracking (pure logic, no I/O).

Input each poll: client MAC -> {node label: Station}. Output: Move / Join events.
- A new location must be seen `confirm` polls in a row (filters the brief double-listing during a roam).
- A move is announced at most once per `cooldown` s per device (stops ping-pong spam between two nodes).
- A device that vanishes and returns to the SAME node within `debounce` s is ignored; returning to a
  DIFFERENT node within that window is reported as a move from where it was last seen.
- The first poll is a baseline: no events.
"""
from __future__ import annotations

from dataclasses import dataclass

from .detector import Station


@dataclass(frozen=True)
class HouseEvent:
    kind: str              # "move" | "join"
    mac: str
    to_node: str
    station: Station
    from_node: str | None = None


class HouseTracker:
    def __init__(self, debounce: float = 60.0, cooldown: float = 60.0, confirm: int = 2):
        self.debounce, self.cooldown, self.confirm = debounce, cooldown, confirm
        self._loc: dict[str, str] = {}              # confirmed location of devices currently present
        self._pending: dict[str, tuple[str, int]] = {}
        self._gone_at: dict[str, float] = {}
        self._last_node: dict[str, str] = {}
        self._last_move: dict[str, float] = {}
        self._started = False

    def update(self, snap: dict[str, dict[str, Station]], now: float) -> list[HouseEvent]:
        snap = {m.lower(): v for m, v in snap.items() if v}
        if not self._started:
            self._started = True
            self._loc = {m: self._pick(m, v) for m, v in snap.items()}
            return []
        events: list[HouseEvent] = []
        for mac in list(self._loc):
            if mac not in snap:
                self._gone_at[mac] = now
                self._last_node[mac] = self._loc.pop(mac)
                self._pending.pop(mac, None)
        for mac, nodes in snap.items():
            cand = self._pick(mac, nodes)
            if self._loc.get(mac) == cand:
                self._pending.pop(mac, None)
                continue
            node, n = self._pending.get(mac, (None, 0))
            n = n + 1 if node == cand else 1
            self._pending[mac] = (cand, n)
            if n < self.confirm:
                continue
            self._pending.pop(mac, None)
            prev, st = self._loc.get(mac), nodes[cand]
            self._loc[mac] = cand
            if prev is not None:
                if now - self._last_move.get(mac, -1e9) >= self.cooldown:
                    self._last_move[mac] = now
                    events.append(HouseEvent("move", mac, cand, st, prev))
                continue
            gone, last = self._gone_at.get(mac), self._last_node.get(mac)
            if gone is not None and now - gone < self.debounce:
                if last != cand:
                    self._last_move[mac] = now
                    events.append(HouseEvent("move", mac, cand, st, last))
                continue
            events.append(HouseEvent("join", mac, cand, st))
        return events

    def _pick(self, mac: str, nodes: dict[str, Station]) -> str:
        """Listed on several nodes at once: keep the current one if still listed, else the first by name."""
        cur = self._loc.get(mac)
        return cur if cur in nodes else sorted(nodes)[0]
