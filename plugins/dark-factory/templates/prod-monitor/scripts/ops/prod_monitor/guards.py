"""What the monitor agent's output may reach — checked in code, not trusted to the model.

The agent reads hosting logs and DB rows, and those can carry text an attacker wrote (a request path, a user name).
Two ways out of the loop are steered by the agent's output, so both are pinned here:
  - `probe_url`: http_probe goes only to the prod host (a path like "@attacker.example/?d=…" would otherwise
    turn PROD_URL + path into a request to another host carrying whatever the agent put in the query);
  - `group_text`: message_for_group is posted to the client's group — capped, URLs and secret-like strings removed.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

PATH_RE = re.compile(r"^/[^@\s\\]*$")
DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port or DEFAULT_PORTS.get(parts.scheme.lower())


def probe_url(base: str, path: object) -> str:
    """PROD_URL + path, or ValueError when the result would leave PROD_URL's scheme, host and port."""
    if not isinstance(path, str) or not PATH_RE.match(path):
        raise ValueError("path must start with / and contain no @, whitespace or backslash")
    url = base.rstrip("/") + path
    parts = urlsplit(url)
    if parts.username is not None or parts.password is not None or _origin(url) != _origin(base):
        raise ValueError("the probe must stay on the prod host")
    return url


GROUP_MAX_CHARS = 600
GROUP_MAX_LINES = 6
# A URL of any kind (the group does not need links from the monitor; a link is the easiest exfiltration
# channel), a long opaque token, a known key prefix, or `name=value` / `name: value` for a secret-looking name.
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+|\bwww\.\S+|\b(?:[\w-]+\.)+[a-z]{2,}(?::\d+)?/\S*"
                  r"|\S+:\S+@\S+", re.I)
_KEY_PREFIX = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|xox[a-z]-\S+|AKIA[0-9A-Z]{12,}"
                         r"|eyJ[A-Za-z0-9_-]{8,}\.\S*|\d{6,}:[A-Za-z0-9_-]{20,})|(?i:\bbearer\s+\S+)")
_ASSIGN = re.compile(r"(?i)\b([\w-]*(?:token|secret|passw(?:or)?d|pwd|api[_-]?key|authorization|cookie)[\w-]*)"
                     r"(\s*[:=]\s*)(?:bearer\s+)?\S+")
# a long run of token characters with both letters and digits (a plain long word is left alone)
_OPAQUE = re.compile(r"(?<![\w+/=.-])(?=[\w+/=.-]*\d)(?=[\w+/=.-]*[A-Za-z])[\w+/=.-]{24,}")
REDACTED = "[removed]"


def group_text(text: object) -> str:
    """message_for_group made safe for the client's group: no URLs or secret-like strings, at most
    GROUP_MAX_LINES lines and GROUP_MAX_CHARS characters, no control characters."""
    if not isinstance(text, str):
        return ""
    text = "".join(c for c in text if c in "\n" or c.isprintable())
    text = _URL.sub(REDACTED, text)
    text = _KEY_PREFIX.sub(REDACTED, text)
    text = _ASSIGN.sub(lambda m: m.group(1) + m.group(2) + REDACTED, text)
    text = _OPAQUE.sub(REDACTED, text)
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()][:GROUP_MAX_LINES]
    text = "\n".join(lines)
    return text if len(text) <= GROUP_MAX_CHARS else text[: GROUP_MAX_CHARS - 1].rstrip() + "…"
