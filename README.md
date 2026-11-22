# Node Radar (roam-in alerts)

A small background service on the Mac mini. It watches **all** ASUS AiMesh nodes and sends a Telegram message when a device **roams onto the Guest Room node from another node**. That is the only alert.
Only devices associated to your own network are seen (the router's own AiMesh client table). No monitor mode, no sniffing of other people's devices.

Example alert: `Guest Room: My iPhone roamed in from Kitchen (-58 dBm) 14:52`

## Rule
- Every 5 s the service reads the main router's AiMesh client table (`/tmp/clientlist.json`: every client, which node it is on, its RSSI) and keeps a map MAC -> current node.
- **Alert** when a MAC's node changes from any other node **to Guest Room**.
- **No alert** when a device leaves Guest Room, moves between other nodes, or joins the network fresh on Guest Room (turn the last one on with `ALERT_FRESH_JOIN=true`; text: `Guest Room: <name> joined (-58 dBm) 14:52`).
- **Debounce:** the same MAC alerting again within 60 s of its last alert (`DEBOUNCE_SECONDS`) is silent.
- A new node must be seen on 2 polls in a row to count (filters the moment a device is listed on two nodes mid-roam). A device that disappears for under 60 s and returns on a different node still counts as a roam from where it was last seen.
- The first poll after a (re)start is a baseline: no alerts.
- Name = router nickname, else DHCP hostname, else the vendor name the router stores, else the MAC. Phones using a private Wi-Fi address often show only a MAC.
- RSSI in the alert comes from the router's table, which can lag the node by a few seconds.
- `NEAR_ALERT=true` re-enables the older "is close" alert (`NEAR_DBM`, `REARM_DBM`, `REARM_SECONDS`); it reads the Guest Room node directly over SSH. Off by default.

## Logging
`data/events.jsonl` records every roam between any nodes (`event: "roam"`, `from`, `to`, `rssi`, `alerted`) and every join (`event: "join"`), whether or not it alerted. Leaves are not logged. History is kept for `LOG_MINUTES` (default 30; raise to e.g. 1440 for a day).

## Telegram and models
Alerts are one direct HTTPS call to the Telegram Bot API (`api.telegram.org/bot<token>/sendMessage`). No Hermes agent, no LLM, no other network service is called at runtime. The bot token and chat id are read from `~/.hermes/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_HOME_CHANNEL`) when sending; nothing is copied into this repo.

## Setup
1. **Router**: Administration → System → Enable SSH = **LAN only**, port 22. Paste `~/.ssh/node_radar_ed25519.pub` into *Authorized Keys*, Apply. Set *Allow Password Login* to No. Only the router needs SSH for the roam rule.
2. **Key**: `ssh-keygen -t ed25519 -N "" -f ~/.ssh/node_radar_ed25519 -C node-radar@mac-mini`
3. **Config** (`.env`, untracked; see `.env.example`): `SSH_USER` (the router UI login name), `ROUTER_HOST`, `NODE_LABEL` (the watched node), and **`NODE_NAMES`**: `KEY=Label` pairs for the router and 4 nodes, where KEY is the node's MAC (stable) or LAN IP (resolved to a MAC through the router's node list). Find them on the AiMesh page.
4. **Install**: `uv sync`, then `./scripts/install_launchd.sh` (starts at login, restarts if it dies).

## One-line test
```
uv run python -m noderadar.test_alert
```
Sends a test Telegram message through the same path as real alerts.

## Operations
- Logs: `~/Library/Logs/node-radar/service.log` (quiet; HTTP and SSH library logs are muted because the HTTP URL contains the bot token).
- Recent movement: `cat data/events.jsonl`
- Stop: `launchctl bootout gui/$UID/com.noderadar`. Start: `./scripts/install_launchd.sh`
- Tests: `uv run pytest`
- Probe a node (read-only): `uv run python scripts/probe.py <ip> <user>`

## Known limits
- Wired clients are not tracked (the router table only gives a node for Wi-Fi clients).
- Detection granularity is the 5 s poll plus the 2-poll confirmation (about 10 s) and the router table's own lag.
- If a node's MAC is not in `NODE_NAMES`, its devices show the raw node MAC instead of a name.

## Phase 2 (not started, nothing to buy now)
ESP32 sensors could add independent presence/signal readings if per-room accuracy is ever needed.

## License

MIT. See [LICENSE](LICENSE).
