"""Structured JSONL logger with PII redaction.

One line per event, written to transcripts/events.log. Each line carries
a timestamp, optional session id, a phase tag, and arbitrary fields.
Phone numbers and email addresses in any string field are masked.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).resolve().parent.parent / "transcripts"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "events.log"

_lock = threading.Lock()

# Match Indian / international phone numbers but avoid catching dates like 15-Mar-2026.
# Require either a leading + OR ≥10 digits in a row (with optional spaces), and only
# match when the run is mostly digits.
_PHONE_RE = re.compile(
    r"\+\d[\d\s\-]{7,}\d"     # international form: +91 98765 43210
    r"|"
    r"(?<!\w)\d{10,}(?!\w)"    # bare 10+ digit run, not part of a word
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        v = _EMAIL_RE.sub("<email>", value)
        v = _PHONE_RE.sub("<phone>", v)
        return v
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def log_event(event: str, *, phase: str = "-", session_id: str | None = None, **fields: Any) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": session_id,
        "phase": phase,
        "event": event,
        **{k: _redact(v) for k, v in fields.items()},
    }
    line = json.dumps(record, default=str, ensure_ascii=False)
    with _lock:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
