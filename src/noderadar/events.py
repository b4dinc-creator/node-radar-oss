from __future__ import annotations

import json
import time
from pathlib import Path


def append(path: Path, event: dict, keep_minutes: int = 30, now: float | None = None) -> None:
    """Append one JSON line and drop lines older than keep_minutes."""
    now = now or time.time()
    event = {**event, "ts": now}
    path.parent.mkdir(parents=True, exist_ok=True)
    cutoff = now - keep_minutes * 60
    kept = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                if json.loads(line)["ts"] >= cutoff:
                    kept.append(line)
            except (ValueError, KeyError):
                pass
    kept.append(json.dumps(event))
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(kept) + "\n")
    tmp.replace(path)
