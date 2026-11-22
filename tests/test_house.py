from noderadar.detector import Station
from noderadar.house import HouseTracker


def S(mac, band="5 GHz", rssi=-50):
    return Station(mac, band, rssi)


def snap(**where):  # snap(a=("Kitchen",))
    return {m: {n: S(m) for n in nodes} for m, nodes in where.items()}


def test_first_poll_baseline():
    h = HouseTracker()
    assert h.update(snap(a=["Kitchen"]), 0) == []


def test_move_needs_two_polls_and_fires_once():
    h = HouseTracker(confirm=2)
    h.update(snap(a=["Kitchen"]), 0)
    assert h.update(snap(a=["Hallway"]), 5) == []          # first sighting only
    ev = h.update(snap(a=["Hallway"]), 10)
    assert [(e.kind, e.from_node, e.to_node) for e in ev] == [("move", "Kitchen", "Hallway")]
    assert h.update(snap(a=["Hallway"]), 15) == []


def test_double_listing_during_roam_is_not_a_move():
    h = HouseTracker(confirm=2)
    h.update(snap(a=["Kitchen"]), 0)
    assert h.update(snap(a=["Kitchen", "Hallway"]), 5) == []   # keeps current while still listed
    assert h.update(snap(a=["Hallway"]), 10) == []             # only one sighting of Hallway so far
    assert len(h.update(snap(a=["Hallway"]), 15)) == 1


def test_ping_pong_cooldown():
    h = HouseTracker(cooldown=60, confirm=1)
    h.update(snap(a=["Kitchen"]), 0)
    assert len(h.update(snap(a=["Hallway"]), 5)) == 1
    assert h.update(snap(a=["Kitchen"]), 10) == []             # inside cooldown: silent, state still updated
    assert len(h.update(snap(a=["Hallway"]), 100)) == 1


def test_new_device_is_join():
    h = HouseTracker(confirm=1)
    h.update(snap(a=["Kitchen"]), 0)
    ev = h.update(snap(a=["Kitchen"], b=["Hallway"]), 5)
    assert [(e.kind, e.to_node, e.mac) for e in ev] == [("join", "Hallway", "b")]


def test_leave_silent_and_quick_rejoin_same_node_ignored():
    h = HouseTracker(debounce=60, confirm=1)
    h.update(snap(a=["Kitchen"]), 0)
    assert h.update({}, 5) == []
    assert h.update(snap(a=["Kitchen"]), 30) == []


def test_quick_rejoin_elsewhere_is_move_from_last_node():
    h = HouseTracker(debounce=60, confirm=1)
    h.update(snap(a=["Kitchen"]), 0)
    h.update({}, 5)
    ev = h.update(snap(a=["Hallway"]), 20)
    assert [(e.kind, e.from_node, e.to_node) for e in ev] == [("move", "Kitchen", "Hallway")]


def test_rejoin_after_debounce_is_join():
    h = HouseTracker(debounce=60, confirm=1)
    h.update(snap(a=["Kitchen"]), 0)
    h.update({}, 5)
    assert [e.kind for e in h.update(snap(a=["Kitchen"]), 100)] == ["join"]
