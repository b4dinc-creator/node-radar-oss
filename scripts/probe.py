"""Read-only discovery of wireless commands on a router/node over SSH.

Usage: uv run python scripts/probe.py <host> [user] [keyfile]
Runs only read commands (nvram get, wl assoclist/rssi/sta_info/status). Saves raw output
to tests/fixtures/raw/<host>/ (untracked, may contain MACs).
"""
import asyncio, pathlib, re, sys
import asyncssh

HOST = sys.argv[1]
USER = sys.argv[2] if len(sys.argv) > 2 else "admin"
KEY = str(pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else "~/.ssh/node_radar_ed25519").expanduser())
OUT = pathlib.Path(__file__).resolve().parent.parent / "tests/fixtures/raw" / HOST
OUT.mkdir(parents=True, exist_ok=True)


async def run(conn, cmd):
    r = await conn.run(cmd, check=False, timeout=15)
    text = f"$ {cmd}\n[exit {r.exit_status}]\n{r.stdout}{('STDERR: ' + r.stderr) if r.stderr else ''}"
    (OUT / (re.sub(r"\W+", "_", cmd)[:80] + ".txt")).write_text(text)
    print(text)
    return r.stdout


async def main():
    async with asyncssh.connect(HOST, username=USER, client_keys=[KEY], known_hosts=None, connect_timeout=8) as c:
        await run(c, "nvram get productid; nvram get model; nvram get firmver; nvram get buildno; nvram get extendno")
        await run(c, "nvram get wl_ifnames; nvram get wl0_ifname; nvram get wl1_ifname; nvram get wl2_ifname; nvram get wl0_nband; nvram get wl1_nband; nvram get wl2_nband")
        ifs = (await run(c, "nvram get wl_ifnames")).split()
        for i in ifs:
            await run(c, f"wl -i {i} status | head -5")
            out = await run(c, f"wl -i {i} assoclist")
            for mac in re.findall(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", out):
                await run(c, f"wl -i {i} rssi {mac}")
                await run(c, f"wl -i {i} sta_info {mac}")
        await run(c, "nvram get custom_clientlist | head -c 600")
        await run(c, "ls /tmp | head -50")

asyncio.run(main())
