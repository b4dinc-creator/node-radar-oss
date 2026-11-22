"""Settings from the untracked .env plus Telegram credentials borrowed from Hermes at runtime."""
from __future__ import annotations

import re
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    node_label: str = "Guest Room"
    node_host: str = ""            # Guest Room XT8 LAN IP
    node_mac: str = ""             # node LAN MAC, only used by the router fallback
    router_host: str = "192.168.50.1"
    ssh_user: str = "admin"
    ssh_key: str = "~/.ssh/node_radar_ed25519"
    ssh_port: int = 22
    poll_seconds: float = 5.0
    near_dbm: int = -50                # alert when the smoothed RSSI is this strong or stronger
    rearm_dbm: int = -60               # re-arm once it has stayed weaker than this ...
    rearm_seconds: float = 30.0        # ... for this long (or the device leaves the node)
    near_alert: bool = False           # proximity ("is close") alerts; code kept, off by default
    alert_fresh_join: bool = False     # also alert when a device joins the network fresh on the watched node
    # KEY=Label pairs for every AP (router + nodes). KEY is the node's MAC (stable) or its LAN IP
    # (resolved to a MAC through the router's AiMesh node list at runtime).
    node_names: str = ("02:00:00:00:00:01=Router,02:00:00:00:00:02=Top kitchen,"
                       "02:00:00:00:00:03=Hallway,02:00:00:00:00:04=Kitchen,02:00:00:00:00:05=Guest Room")
    confirm_polls: int = 2             # a new node must be seen this many polls in a row to count as a roam
    debounce_seconds: float = 60.0     # same MAC alerting again for the watched node within this: silent
    log_minutes: int = 30
    events_path: Path = ROOT / "data" / "events.jsonl"
    hermes_env: Path = Path("~/.hermes/.env").expanduser()
    # Optional explicit overrides; normally left empty so Hermes' values are reused.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


def node_entries(s: Settings) -> dict[str, str]:
    """NODE_NAMES as {MAC-or-IP: label}. Keys are resolved to MACs by collector.resolve_node_labels."""
    out = {}
    for pair in s.node_names.split(","):
        key, _, label = pair.partition("=")
        if key.strip() and label.strip():
            out[key.strip().upper()] = label.strip()
    return out


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip("'\"")
    return out


def telegram_credentials(s: Settings) -> tuple[str, str]:
    """Return (token, chat_id). Hermes' own .env is read at call time; nothing is copied into this repo."""
    h = _read_env_file(s.hermes_env)
    token = s.telegram_bot_token or h.get("TELEGRAM_BOT_TOKEN", "")
    chat = s.telegram_chat_id or h.get("TELEGRAM_HOME_CHANNEL", "")
    if not token or not chat:
        raise RuntimeError(f"Telegram token/chat id not found (looked in {s.hermes_env} and .env)")
    return token, chat
