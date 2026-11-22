"""Runs the real service loop with a scripted fake router table and a fake clock (5 s per poll)."""
import json
from types import SimpleNamespace

import httpx
import pytest

from noderadar import service, telegram
from noderadar.config import Settings
from noderadar.detector import Station

GR = "Guest Room"


def S(mac, rssi=-58, band="5 GHz"):
    return Station(mac, band, rssi)


def snap(**where):
    """snap(x="Kitchen", y="Guest Room") -> {mac: {node: Station}}"""
    return {m: {n: S(m)} for m, n in where.items()}


class Stop(Exception):
    pass


class FakeCollector:
    def __init__(self, house, node=None):
        self.house, self.node, self.i, self.j = house, node, 0, 0

    async def poll_house(self, entries):
        r = self.house[min(self.i, len(self.house) - 1)]
        self.i += 1
        return r

    async def poll(self):
        if self.node is None:
            raise AssertionError("the node must not be polled directly unless NEAR_ALERT=true")
        r = self.node[min(self.j, len(self.node) - 1)]
        self.j += 1
        return r, "node"


class FakeNames:
    def __init__(self, *_):
        pass

    async def refresh(self, force=False):
        pass

    def name(self, mac):
        return {"x": "Xphone", "y": "Yphone", "z": "Zphone", "w": "Wphone"}.get(mac, mac)


async def run_loop(monkeypatch, tmp_path, collector, polls, **settings):
    sent, calls, clock = [], {"n": 0}, {"t": 1_000_000.0}

    async def fake_send(text, s=None):
        sent.append(text)

    async def fake_sleep(_):
        clock["t"] += 5.0
        calls["n"] += 1
        if calls["n"] >= polls:
            raise Stop

    monkeypatch.setattr(service, "Collector", lambda s: collector)
    monkeypatch.setattr(service, "NameResolver", FakeNames)
    monkeypatch.setattr(service.telegram, "send", fake_send)
    monkeypatch.setattr(service.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(service, "time", SimpleNamespace(time=lambda: clock["t"], monotonic=lambda: clock["t"]))
    s = Settings(_env_file=None, events_path=tmp_path / "e.jsonl", node_label=GR, **settings)
    with pytest.raises(Stop):
        await service.run(s)
    path = tmp_path / "e.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    return [t.rsplit(" ", 1)[0] for t in sent], events  # strip HH:MM


async def go(monkeypatch, tmp_path, house, **kw):
    return await run_loop(monkeypatch, tmp_path, FakeCollector(house, kw.pop("node", None)), len(house), **kw)


@pytest.mark.asyncio
async def test_roam_into_guest_room_alerts_with_exact_text(monkeypatch, tmp_path):
    house = [snap(x="Kitchen")] + [snap(x=GR)] * 4
    texts, events = await go(monkeypatch, tmp_path, house)
    assert texts == ["Guest Room: Xphone roamed in from Kitchen (-58 dBm)"]
    assert [(e["event"], e["from"], e["to"], e["alerted"]) for e in events] == [("roam", "Kitchen", GR, True)]


@pytest.mark.asyncio
async def test_leaving_and_other_roams_are_silent_but_logged(monkeypatch, tmp_path):
    house = [snap(w=GR, y="Kitchen", z="Hallway")] + [snap(w="Kitchen", y="Hallway", z="Top kitchen")] * 4
    texts, events = await go(monkeypatch, tmp_path, house)
    assert texts == []
    assert sorted((e["mac"], e["from"], e["to"], e["alerted"]) for e in events) == [
        ("w", GR, "Kitchen", False), ("y", "Kitchen", "Hallway", False), ("z", "Hallway", "Top kitchen", False)]
    assert all(e["event"] == "roam" for e in events)


@pytest.mark.asyncio
async def test_fresh_join_on_guest_room_is_silent_by_default_but_logged(monkeypatch, tmp_path):
    house = [snap(w="Kitchen")] + [snap(w="Kitchen", x=GR)] * 4
    texts, events = await go(monkeypatch, tmp_path, house)
    assert texts == []
    assert [(e["event"], e["to"], e["alerted"]) for e in events] == [("join", GR, False)]


@pytest.mark.asyncio
async def test_fresh_join_alerts_when_enabled_but_only_on_guest_room(monkeypatch, tmp_path):
    house = [snap(w="Kitchen")] + [snap(w="Kitchen", x=GR, y="Hallway")] * 4
    texts, events = await go(monkeypatch, tmp_path, house, alert_fresh_join=True)
    assert texts == ["Guest Room: Xphone joined (-58 dBm)"]          # Yphone joined Hallway: no alert
    assert {(e["mac"], e["alerted"]) for e in events} == {("x", True), ("y", False)}


@pytest.mark.asyncio
async def test_debounce_60s_then_alerts_again(monkeypatch, tmp_path):
    # idx0 baseline Kitchen; idx1-2 GR (alert at idx2); idx3-4 Kitchen; idx5-6 GR (20 s after alert: silent);
    # long stay on Kitchen; idx21-22 GR (>60 s after the last alert): alerts again.
    house = ([snap(x="Kitchen")] + [snap(x=GR)] * 2 + [snap(x="Kitchen")] * 2 + [snap(x=GR)] * 2
             + [snap(x="Kitchen")] * 14 + [snap(x=GR)] * 2)
    texts, events = await go(monkeypatch, tmp_path, house)
    assert texts == ["Guest Room: Xphone roamed in from Kitchen (-58 dBm)"] * 2
    flags = [(e["to"], e["alerted"]) for e in events if e["event"] == "roam"]
    assert flags == [(GR, True), ("Kitchen", False), (GR, False), ("Kitchen", False), (GR, True)]


@pytest.mark.asyncio
async def test_roam_with_a_short_gap_in_the_table_still_counts(monkeypatch, tmp_path):
    # Devices often vanish from the table for a few seconds mid-roam.
    house = [snap(x="Kitchen")] + [{}] * 2 + [snap(x=GR)] * 3
    texts, _ = await go(monkeypatch, tmp_path, house)
    assert texts == ["Guest Room: Xphone roamed in from Kitchen (-58 dBm)"]


@pytest.mark.asyncio
async def test_one_poll_blip_to_guest_room_is_not_a_roam(monkeypatch, tmp_path):
    house = [snap(x="Kitchen"), snap(x=GR), snap(x="Kitchen"), snap(x="Kitchen")]
    texts, events = await go(monkeypatch, tmp_path, house)
    assert texts == [] and events == []


@pytest.mark.asyncio
async def test_baseline_poll_sends_nothing(monkeypatch, tmp_path):
    texts, events = await go(monkeypatch, tmp_path, [snap(x=GR, y="Kitchen")] * 3)
    assert texts == [] and events == []


@pytest.mark.asyncio
async def test_near_alert_is_off_by_default_and_never_polls_the_node(monkeypatch, tmp_path):
    # FakeCollector.poll() raises if called, so passing proves the node was not polled.
    texts, _ = await go(monkeypatch, tmp_path, [snap(x="Kitchen")] * 3)
    assert texts == []


@pytest.mark.asyncio
async def test_near_alert_still_works_when_enabled(monkeypatch, tmp_path):
    node = [[S("x", -70)], [S("x", -45)], [S("x", -45)], [S("x", -45)]]
    texts, events = await go(monkeypatch, tmp_path, [{}] * 4, node=node, near_alert=True)
    assert texts == ["Guest Room: Xphone is close (-45 dBm)"]
    assert [e["event"] for e in events] == ["near"]


@pytest.mark.asyncio
async def test_telegram_is_a_direct_bot_api_call(monkeypatch):
    """Alerts go straight to api.telegram.org: one POST, only chat_id + text, no other host."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    real = httpx.AsyncClient
    monkeypatch.setattr(telegram.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    s = Settings(_env_file=None, telegram_bot_token="TESTTOKEN", telegram_chat_id="42", hermes_env="/nonexistent")
    await telegram.send("hello", s)
    assert len(seen) == 1
    r = seen[0]
    assert (r.method, r.url.host, r.url.path) == ("POST", "api.telegram.org", "/botTESTTOKEN/sendMessage")
    assert json.loads(r.content) == {"chat_id": "42", "text": "hello"}
