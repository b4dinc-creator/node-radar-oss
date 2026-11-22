"""Read the association list of one AiMesh node over SSH (fallback: the router's AiMesh client table).

Verified on a ZenWiFi XT8 (RT-AX95Q, fw 3.0.0.4.388): client-facing BSSes are the virtual
interfaces wl0.1 / wl1.1 / wl2.1, NOT eth4/5/6 (those are the backhaul radios and report empty lists).
"""
from __future__ import annotations

import json
import re

import asyncssh

from .config import Settings
from .detector import Station

# One round trip per poll: every wlX.Y interface -> its channel -> each associated MAC and its RSSI.
NODE_SCRIPT = r"""
for i in $(ls /sys/class/net | grep -E '^wl[0-9]+\.[0-9]+$'); do
  c=$(wl -i $i chanspec 2>/dev/null | awk '{print $1}')
  for m in $(wl -i $i assoclist 2>/dev/null | awk '{print $2}'); do
    echo "STA $i $c $m $(wl -i $i rssi $m 2>/dev/null)"
  done
done
"""

_STA = re.compile(r"^STA\s+(\S+)\s+(\d+)(?:/\d+)?\s+((?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s*(-?\d+)?\s*$")


def band_of(channel: int) -> str:
    return "2.4 GHz" if channel <= 14 else "5 GHz"


def parse_node_output(text: str) -> list[Station]:
    out = []
    for line in text.splitlines():
        m = _STA.match(line.strip())
        if m:
            _iface, chan, mac, rssi = m.groups()
            out.append(Station(mac.lower(), band_of(int(chan)), int(rssi) if rssi else None))
    return out


_BAND_KEYS = {"2G": "2.4 GHz", "5G": "5 GHz", "5G1": "5 GHz", "5G2": "5 GHz", "6G": "6 GHz"}


def parse_router_clientlist(text: str, node_mac: str) -> list[Station]:
    """Fallback: /tmp/clientlist.json on the main router maps node MAC -> band -> client -> {rssi}."""
    data = json.loads(text).get(node_mac.upper(), {})
    out = []
    for band_key, clients in data.items():
        if band_key not in _BAND_KEYS:  # skips "wired_mac"
            continue
        for mac, info in clients.items():
            rssi = info.get("rssi")
            out.append(Station(mac.lower(), _BAND_KEYS[band_key], int(rssi) if rssi else None))
    return out


def parse_router_all_multi(text: str, labels: dict[str, str]) -> dict[str, dict[str, Station]]:
    """client MAC -> {node label: Station}; keeps every node a client is listed on."""
    out: dict[str, dict[str, Station]] = {}
    for node_mac, bands in json.loads(text).items():
        label = labels.get(node_mac.upper(), node_mac.upper())
        for band_key, clients in bands.items():
            if band_key not in _BAND_KEYS:
                continue
            for mac, info in clients.items():
                rssi = info.get("rssi")
                out.setdefault(mac.lower(), {})[label] = Station(
                    mac.lower(), _BAND_KEYS[band_key], int(rssi) if rssi else None)
    return out


_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def parse_device_list(raw: str) -> dict[str, str]:
    """nvram cfg_device_list: '<name>IP>MAC>flag<name>IP>MAC>flag...' -> {ip: MAC}."""
    out = {}
    for entry in raw.strip().split("<"):
        p = entry.split(">")
        if len(p) >= 3 and _IPV4.match(p[1]) and len(p[2]) == 17:
            out[p[1]] = p[2].upper()
    return out


def resolve_node_labels(entries: dict[str, str], device_list_raw: str) -> dict[str, str]:
    """{MAC-or-IP: label} -> {node MAC: label}. IPs are looked up in the router's AiMesh node list."""
    ip_to_mac = parse_device_list(device_list_raw)
    out = {}
    for key, label in entries.items():
        mac = ip_to_mac.get(key) if _IPV4.match(key) else key.upper()
        if mac:
            out[mac.upper()] = label
    return out


class Collector:
    def __init__(self, s: Settings):
        self.s = s
        self._node: asyncssh.SSHClientConnection | None = None
        self._router: asyncssh.SSHClientConnection | None = None

    async def _connect(self, host: str) -> asyncssh.SSHClientConnection:
        return await asyncssh.connect(
            host, port=self.s.ssh_port, username=self.s.ssh_user,
            client_keys=[str(__import__("pathlib").Path(self.s.ssh_key).expanduser())],
            known_hosts=None, connect_timeout=8, keepalive_interval=15,
        )

    async def router(self) -> asyncssh.SSHClientConnection:
        if self._router is None or self._router.is_closed():
            self._router = await self._connect(self.s.router_host)
        return self._router

    async def poll_house(self, entries: dict[str, str]) -> dict[str, dict[str, Station]]:
        """One router call: every client on every node (client MAC -> {node label: Station})."""
        r = await (await self.router()).run(
            "cat /tmp/clientlist.json; echo '@@@'; nvram get cfg_device_list", check=True, timeout=10)
        clients, _, devices = r.stdout.partition("@@@")
        return parse_router_all_multi(clients, resolve_node_labels(entries, devices))

    async def poll(self) -> tuple[list[Station], str]:
        """Return (stations, source) where source is 'node' or 'router-fallback'."""
        try:
            if self._node is None or self._node.is_closed():
                self._node = await self._connect(self.s.node_host)
            r = await self._node.run(NODE_SCRIPT, check=True, timeout=10)
            return parse_node_output(r.stdout), "node"
        except (OSError, asyncssh.Error, TimeoutError):
            self._node = None
        r = await (await self.router()).run("cat /tmp/clientlist.json", check=True, timeout=10)
        return parse_router_clientlist(r.stdout, self.s.node_mac), "router-fallback"
