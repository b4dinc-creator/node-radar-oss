import pytest

from noderadar.detector import Station
from noderadar.proximity import NearDetector


def S(rssi, mac="aa:00:00:00:00:01"):
    return Station(mac, "5 GHz", rssi)


def run(det, series, start=0, step=5):
    """Feed one device's RSSI series; return {t: smoothed_rssi} for every poll that alerted."""
    fired = {}
    for i, r in enumerate(series):
        t = start + i * step
        out = det.update([S(r)] if r is not None else [], t)
        if out:
            fired[t] = out[0][1]
    return fired


def test_threshold_is_inclusive_and_stronger_counts():
    for r in (-50, -45, -40):
        assert run(NearDetector(), [r]) == {0: r}
    assert run(NearDetector(), [-51]) == {}


def test_joins_already_near_alerts_on_first_poll():
    assert run(NearDetector(), [-42]) == {0: -42}


def test_single_noisy_sample_does_not_fire():
    # -70 then a -40 spike: mean of last two is -55, not near.
    assert run(NearDetector(), [-70, -40, -70, -70]) == {}


def test_uses_mean_of_last_two_not_older():
    # readings -90,-46,-44: at t=10 the mean of (-46,-44) = -45 fires (the -90 has aged out).
    assert run(NearDetector(), [-90, -46, -44]) == {10: -45}


def test_fires_once_while_standing_near():
    # 2 minutes at 5 s polls, always near: exactly one alert.
    assert len(run(NearDetector(), [-45] * 24)) == 1


def test_signal_wobble_between_near_and_rearm_levels_does_not_repeat():
    series = [-45, -48, -55, -58, -52, -49, -57, -45] * 3
    assert len(run(NearDetector(), series)) == 1


def test_rearms_after_30s_below_minus60_then_fires_again():
    det = NearDetector()
    fired = run(det, [-45] + [-70] * 8)           # t=0 fires; weak from t=5 (avg<-60 from t=10)...
    assert list(fired) == [0]
    # ... 30 s below -60 reached; approach again:
    out = det.update([S(-44)], 100)
    assert out == []                              # mean(-70,-44) = -57: still not near
    out = det.update([S(-44)], 105)
    assert out and out[0][1] == -44               # mean(-44,-44): fires again


def test_not_rearmed_if_below_minus60_for_less_than_30s():
    det = NearDetector()
    det.update([S(-45)], 0)
    for t in (5, 10, 15, 20, 25):                 # weak only ~15 s
        det.update([S(-75)], t)
    assert det.update([S(-44)], 30) == []         # avg -59.5 -> not near
    assert det.update([S(-44)], 35) == []         # armed? no -> silent


def test_timer_resets_if_signal_climbs_back_above_rearm_level():
    det = NearDetector()
    det.update([S(-45)], 0)
    det.update([S(-80)], 5)
    det.update([S(-80)], 10)                      # below -60 since t=10
    det.update([S(-55)], 15)
    det.update([S(-55)], 20)                      # avg -55 > -60 -> timer reset
    for t in (25, 30, 35, 40):
        det.update([S(-80)], t)                   # below again; only starts counting at t=30
    assert det.update([S(-44)], 45) == []         # not yet 30 s below since reset
    assert det.update([S(-44)], 50) == []         # still silent (never re-armed)


def test_leaving_the_node_rearms_immediately():
    det = NearDetector()
    assert det.update([S(-45)], 0)
    assert det.update([], 5) == []                # left
    assert det.update([S(-45)], 10)               # back and near -> alert again


def test_invalid_readings_ignored():
    det = NearDetector()
    assert det.update([S(0)], 0) == []
    assert det.update([S(None)], 5) == []
    assert det.update([S(-45)], 10)


def test_devices_are_independent():
    det = NearDetector()
    out = det.update([S(-45, "a"), S(-70, "b")], 0)
    assert [o[0].mac for o in out] == ["a"]
    assert det.update([S(-45, "a"), S(-60, "b")], 5) == []     # b: mean(-70,-60) = -65; a already alerted
    assert det.update([S(-45, "a"), S(-45, "b")], 10) == []    # b: mean(-60,-45) = -52.5, still not near
    out = det.update([S(-45, "a"), S(-45, "b")], 15)           # b: mean(-45,-45) = -45 -> fires
    assert [o[0].mac for o in out] == ["b"]
