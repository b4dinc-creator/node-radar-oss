import json

from noderadar.collector import parse_node_output, parse_router_clientlist
from noderadar.names import parse_custom_clientlist, parse_leases
from noderadar.service import format_near
from datetime import datetime

# Shape captured from a real XT8 (MACs replaced).
NODE = """STA wl0.1 1 D8:00:00:00:00:01 -72
STA wl1.1 36/80 04:00:00:00:00:02 -42
STA wl2.1 153 86:00:00:00:00:03 -29
garbage line
"""


def test_node_output():
    s = parse_node_output(NODE)
    assert [(x.mac, x.band, x.rssi) for x in s] == [
        ("d8:00:00:00:00:01", "2.4 GHz", -72),
        ("04:00:00:00:00:02", "5 GHz", -42),
        ("86:00:00:00:00:03", "5 GHz", -29)]


def test_router_fallback():
    raw = json.dumps({"02:00:00:00:00:05": {"2G": {"D8:00:00:00:00:01": {"rssi": "-74"}},
                                            "5G1": {"86:00:00:00:00:03": {"rssi": "-30"}},
                                            "wired_mac": {"D0:00:00:00:00:09": {"ip": "x"}}}})
    s = parse_router_clientlist(raw, "02:00:00:00:00:05")
    assert {(x.mac, x.band, x.rssi) for x in s} == {("d8:00:00:00:00:01", "2.4 GHz", -74),
                                                    ("86:00:00:00:00:03", "5 GHz", -30)}


def test_names():
    assert parse_custom_clientlist("<Phone>AA:BB:CC:DD:EE:01>0>10>>>><Acme Corp>AA:BB:CC:DD:EE:02>0>0>>>>") == {
        "aa:bb:cc:dd:ee:01": "Phone", "aa:bb:cc:dd:ee:02": "Acme Corp"}
    assert parse_leases("1 aa:bb:cc:dd:ee:01 1.2.3.4 * 01:x\n2 aa:bb:cc:dd:ee:02 1.2.3.5 mac-mini 01:y") == {
        "aa:bb:cc:dd:ee:02": "mac-mini"}


def test_alert_text():
    assert format_near("Guest Room", "My iPhone", -47, datetime(2026, 1, 1, 21, 58)) == \
        "Guest Room: My iPhone is close (-47 dBm) 21:58"


def test_node_names_resolve_by_mac_or_ip():
    from noderadar.collector import parse_device_list, resolve_node_labels
    raw = ("<GT-AX6000>192.168.50.1>02:00:00:00:00:01>1<ZenWiFi_XT8>192.168.50.200>02:00:00:00:00:05>0"
           "<ZenWiFi_XT8>192.168.50.108>02:00:00:00:00:04>0")
    assert parse_device_list(raw)["192.168.50.108"] == "02:00:00:00:00:04"
    labels = resolve_node_labels({"192.168.50.200": "Guest Room", "02:00:00:00:00:04": "Kitchen",
                                  "192.168.50.1": "Router", "192.168.50.99": "Ghost"}, raw)
    assert labels == {"02:00:00:00:00:05": "Guest Room", "02:00:00:00:00:04": "Kitchen",
                      "02:00:00:00:00:01": "Router"}          # unknown IP is skipped, not guessed


def test_roam_text():
    from noderadar.service import format_roam_in
    assert format_roam_in("Guest Room", "My iPhone", "Kitchen", -58, datetime(2026, 1, 1, 14, 52)) == \
        "Guest Room: My iPhone roamed in from Kitchen (-58 dBm) 14:52"
