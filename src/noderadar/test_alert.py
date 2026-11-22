"""python -m noderadar.test_alert  -> sends one test message through the same path as real alerts."""
import asyncio
from datetime import datetime

from . import telegram
from .config import Settings


def main() -> None:
    s = Settings()
    asyncio.run(telegram.send(f"{s.node_label}: Node Radar test alert {datetime.now():%H:%M}", s))
    print("sent")


if __name__ == "__main__":
    main()
