"""MAC -> display name using the router's own data (nickname, DHCP hostname, vendor)."""
from __future__ import annotations

import time

from .collector import Collector


def parse_custom_clientlist(raw: str) -> dict[str, str]:
    """nvram custom_clientlist: '<name>MAC>group>type>...' entries. Name is the nickname, or the vendor if unnamed."""
    out = {}
    for entry in raw.strip().split("<"):
        parts = entry.split(">")
        if len(parts) >= 2 and parts[0] and len(parts[1]) == 17:
            out[parts[1].lower()] = parts[0]
    return out


def parse_leases(raw: str) -> dict[str, str]:
    """dnsmasq.leases: 'expiry mac ip hostname clientid'; hostname '*' means none."""
    out = {}
    for line in raw.splitlines():
        p = line.split()
        if len(p) >= 4 and p[3] != "*":
            out[p[1].lower()] = p[3]
    return out


class NameResolver:
    def __init__(self, collector: Collector, ttl: float = 30.0):
        self.c, self.ttl = collector, ttl
        self._custom: dict[str, str] = {}
        self._leases: dict[str, str] = {}
        self._at = 0.0

    async def refresh(self, force: bool = False) -> None:
        if not force and time.time() - self._at < self.ttl:
            return
        try:
            r = await (await self.c.router()).run(
                "nvram get custom_clientlist; echo '@@@'; cat /var/lib/misc/dnsmasq.leases", check=True, timeout=10)
            custom, _, leases = r.stdout.partition("@@@")
            self._custom, self._leases = parse_custom_clientlist(custom), parse_leases(leases)
            self._at = time.time()
        except Exception:  # names are best-effort; never block an alert
            self._at = time.time()

    def name(self, mac: str) -> str:
        mac = mac.lower()
        return self._custom.get(mac) or self._leases.get(mac) or mac.upper()
