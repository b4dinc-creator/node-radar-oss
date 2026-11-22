from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from . import events, telegram
from .collector import Collector
from .config import Settings, node_entries
from .house import HouseEvent, HouseTracker
from .names import NameResolver
from .proximity import NearDetector

log = logging.getLogger("noderadar")


def _sig(rssi: int | None) -> str:
    return f"{rssi} dBm" if rssi is not None else "RSSI n/a"


def format_roam_in(label: str, name: str, from_node: str | None, rssi: int | None, when: datetime) -> str:
    return f"{label}: {name} roamed in from {from_node} ({_sig(rssi)}) {when:%H:%M}"


def format_fresh_join(label: str, name: str, rssi: int | None, when: datetime) -> str:
    return f"{label}: {name} joined ({_sig(rssi)}) {when:%H:%M}"


def format_near(label: str, name: str, rssi: int, when: datetime) -> str:
    return f"{label}: {name} is close ({rssi} dBm) {when:%H:%M}"


async def _send(s: Settings, text: str) -> None:
    try:
        await telegram.send(text, s)
    except Exception as e:  # keep polling even if Telegram is down
        log.error("telegram failed: %s", e)


def _wants_alert(s: Settings, ev: HouseEvent, last_alert: dict[str, float], now: float) -> bool:
    """The ONLY alert trigger: a MAC moved to the watched node from another node.

    Leaving the watched node and moves between other nodes never alert. A fresh join on the watched
    node alerts only if ALERT_FRESH_JOIN is on. Same MAC alerting again within the debounce: silent.
    """
    if ev.to_node != s.node_label:
        return False
    if ev.kind == "join" and not s.alert_fresh_join:
        return False
    return now - last_alert.get(ev.mac, float("-inf")) >= s.debounce_seconds


async def run(s: Settings | None = None) -> None:
    s = s or Settings()
    col, names = Collector(s), NameResolver(Collector(s))
    names.c = col
    entries = node_entries(s)
    # cooldown 0: every roam is reported to the log; alert gating happens in _wants_alert.
    house = HouseTracker(s.debounce_seconds, 0.0, s.confirm_polls)
    near = NearDetector(s.near_dbm, s.rearm_dbm, s.rearm_seconds)
    last_alert: dict[str, float] = {}
    while True:
        started = time.monotonic()
        try:
            now = time.time()
            for ev in house.update(await col.poll_house(entries), now):
                await names.refresh()
                name, when = names.name(ev.mac), datetime.now()
                alert = _wants_alert(s, ev, last_alert, now)
                if ev.kind == "move":
                    text = (format_roam_in(s.node_label, name, ev.from_node, ev.station.rssi, when) if alert
                            else f"{name}: {ev.from_node} → {ev.to_node} ({_sig(ev.station.rssi)})")
                else:
                    text = (format_fresh_join(s.node_label, name, ev.station.rssi, when) if alert
                            else f"{ev.to_node}: {name} joined ({_sig(ev.station.rssi)})")
                events.append(s.events_path, {
                    "event": "roam" if ev.kind == "move" else "join", "mac": ev.mac, "from": ev.from_node,
                    "to": ev.to_node, "band": ev.station.band, "rssi": ev.station.rssi,
                    "alerted": alert, "text": text}, s.log_minutes)
                log.info("%s%s", "ALERT " if alert else "", text)
                if alert:
                    last_alert[ev.mac] = now
                    await _send(s, text)
        except Exception as e:
            log.error("roam poll failed: %s", e)
        if s.near_alert:
            # Disabled by default (NEAR_ALERT=false). Reads the watched node directly over SSH.
            try:
                stations, source = await col.poll()
                now = time.time()
                for st, avg in near.update(stations, now):
                    await names.refresh()
                    text = format_near(s.node_label, names.name(st.mac), avg, datetime.now())
                    events.append(s.events_path, {"event": "near", "mac": st.mac, "band": st.band, "rssi": avg,
                                                  "source": source, "alerted": True, "text": text}, s.log_minutes)
                    log.info("ALERT %s", text)
                    await _send(s, text)
            except Exception as e:
                log.error("near poll failed: %s", e)
        await asyncio.sleep(max(0.0, s.poll_seconds - (time.monotonic() - started)))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx logs the full request URL, which contains the Telegram bot token. asyncssh is very chatty.
    for noisy in ("httpx", "httpcore", "asyncssh"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    asyncio.run(run())
