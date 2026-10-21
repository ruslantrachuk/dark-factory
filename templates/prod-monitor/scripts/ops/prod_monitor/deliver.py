"""Verdict delivery: the "monitor" channel in the On-call session; if it did not accept — warn/crit/resolved straight to the group.

Direct means Bot API sendMessage only: getUpdates is never touched, the bot has a single reader (the On-call plugin).
The group, plugin directory and channel port come from the On-call config (desk.env is written by `prod-monitor.sh install`).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from . import project
from .envfile import read_env_file

CHANNEL_URL = f"http://127.0.0.1:{project.DESK.get('MONITOR_CHANNEL_PORT', '8790')}/event"
DIRECT_STATUSES = {"warn", "crit", "resolved"}


def post_channel(status: str, text: str, details: object = None) -> bool:
    body = json.dumps(
        {"status": status, "text": text, "details": details}, ensure_ascii=False, default=str
    )
    req = urllib.request.Request(
        CHANNEL_URL, data=body.encode(), method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.load(resp).get("delivered") is True
    except (OSError, ValueError):
        return False


def post_telegram_direct(text: str) -> bool:
    state_dir = Path(project.DESK.get("DESK_STATE_DIR", "~/.claude/channels/telegram")).expanduser()
    token = read_env_file(state_dir / ".env").get("TELEGRAM_BOT_TOKEN")
    group = project.DESK.get("DESK_GROUP_ID")
    if not token or not group:
        return False
    data = urllib.parse.urlencode({"chat_id": group, "text": text}).encode()
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10
        ) as resp:
            return json.load(resp).get("ok") is True
    except (OSError, ValueError):
        return False


def deliver(status: str, text: str, details: object = None) -> str:
    """Returns where it went: channel / direct / dropped / failed."""
    if post_channel(status, text, details):
        return "channel"
    if status not in DIRECT_STATUSES:
        return "dropped"
    return "direct" if post_telegram_direct(f"Monitor (On-call is not responding): {text}") else "failed"
