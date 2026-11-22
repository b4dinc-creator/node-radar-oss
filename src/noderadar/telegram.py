from __future__ import annotations

import httpx

from .config import Settings, telegram_credentials


async def send(text: str, settings: Settings | None = None) -> None:
    s = settings or Settings()
    token, chat = telegram_credentials(s)
    # sendMessage only; we never call getUpdates, so we cannot steal updates from Hermes' polling.
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text})
    if r.status_code != 200:
        # Never include the URL (it contains the token) in the error.
        raise RuntimeError(f"Telegram send failed: HTTP {r.status_code} {r.json().get('description', '')}")
