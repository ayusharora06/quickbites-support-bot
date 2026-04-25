"""Policy/FAQ retrieval. Tiny doc — section-level keyword scoring is enough."""

from __future__ import annotations

import re
from functools import lru_cache

from .config import POLICY_PATH


@lru_cache(maxsize=1)
def _sections() -> list[tuple[str, str]]:
    text = POLICY_PATH.read_text(encoding="utf-8")
    out: list[tuple[str, str]] = []

    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    for part in parts[1:]:
        lines = part.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if title.lower().startswith("common faq"):
            faq_blocks = re.split(r"^\*\*Q:", body, flags=re.MULTILINE)
            for q in faq_blocks[1:]:
                q = "Q:" + q.strip()
                if q.endswith("**"):
                    q = q[:-2]
                out.append(("FAQ", q))
        else:
            out.append((title, body))
    return out


def full_policy() -> str:
    """The whole doc, for the system prompt."""
    return POLICY_PATH.read_text(encoding="utf-8")


def search_policy(query: str, k: int = 3) -> list[dict[str, str]]:
    """Return top-k sections by keyword overlap with the query."""
    if not query.strip():
        return []
    terms = {t.lower() for t in re.findall(r"[a-zA-Z]{3,}", query)}
    if not terms:
        return []

    scored: list[tuple[int, str, str]] = []
    for title, body in _sections():
        haystack = f"{title}\n{body}".lower()
        score = sum(haystack.count(t) for t in terms)
        if score > 0:
            scored.append((score, title, body))

    scored.sort(key=lambda x: -x[0])
    return [{"section": t, "content": b} for _, t, b in scored[:k]]
