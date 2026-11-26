"""Read the gate verdict out of an agent's final message.

The prompts ask for JSON, and ``--output-schema`` usually gets it, but a real
run also produces prose, fenced blocks and the occasional truncated object.
This module is the single place that decides what the orchestrator believes,
so the rules cannot drift between stages.
"""

from __future__ import annotations

import json
import re
from typing import Iterator, Optional

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"

GATE_VALUES = (PASS, FAIL)

# Fallback for a model that ignored the JSON instruction but still answered.
_MARKER = re.compile(
    r"^\s*(?:VERDICT|REVIEW[_ ]VERDICT|TEST[_ ]VERDICT)\s*:\s*(PASS|FAIL)\b",
    re.IGNORECASE | re.MULTILINE,
)

_SEVERITY_ORDER = {"blocker": 0, "major": 1, "minor": 2, "nit": 3}


def parse(text: Optional[str]) -> dict:
    """Return ``{'verdict', 'source', 'payload'}`` for one message."""
    text = text or ""

    for obj in _objects(text):
        verdict = str(obj.get("verdict", "")).strip().lower()
        if verdict in GATE_VALUES:
            return {"verdict": verdict, "source": "json", "payload": obj}

    marker = _MARKER.search(text)
    if marker:
        return {"verdict": marker.group(1).lower(), "source": "marker", "payload": None}

    return {"verdict": UNKNOWN, "source": "none", "payload": None}


def _objects(text: str) -> Iterator[dict]:
    """Yield every JSON object embedded anywhere in ``text``."""
    decoder = json.JSONDecoder()
    index = text.find("{")
    while index >= 0:
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            index = text.find("{", index + 1)
            continue
        if isinstance(value, dict):
            yield value
        index = text.find("{", end)


def summary(payload: Optional[dict]) -> str:
    """One line for the manifest, never empty for a parsed payload."""
    if not payload:
        return ""
    text = str(payload.get("summary") or payload.get("goal") or "").strip()
    if text:
        return " ".join(text.split())
    findings = payload.get("findings")
    if isinstance(findings, list) and findings:
        first = findings[0]
        if isinstance(first, dict):
            return str(first.get("issue") or "").strip()
    return ""


def findings(payload: Optional[dict]) -> list:
    """Normalised findings, worst first, ready for the debug prompt."""
    if not payload:
        return []
    raw = payload.get("findings")
    if not isinstance(raw, list):
        return []
    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cleaned.append({
            "severity": str(item.get("severity") or "minor").strip().lower(),
            "file": str(item.get("file") or "").strip(),
            "line": item.get("line"),
            "issue": str(item.get("issue") or "").strip(),
            "suggestion": str(item.get("suggestion") or "").strip(),
        })
    cleaned.sort(key=lambda f: _SEVERITY_ORDER.get(f["severity"], 9))
    return cleaned


def blocking(payload: Optional[dict]) -> bool:
    """True when a passing verdict is contradicted by a blocker/major finding."""
    return any(f["severity"] in ("blocker", "major") for f in findings(payload))


def describe(payload: Optional[dict], limit: int = 8) -> str:
    """Render findings as a short list for the debug stage's prompt."""
    items = findings(payload)
    if not items:
        return ""
    lines = []
    for item in items[:limit]:
        where = item["file"] or "?"
        if item["line"] not in (None, ""):
            where = "%s:%s" % (where, item["line"])
        line = "- [%s] %s: %s" % (item["severity"], where, item["issue"])
        if item["suggestion"]:
            line += " (suggested: %s)" % item["suggestion"]
        lines.append(line)
    if len(items) > limit:
        lines.append("- ... and %d more" % (len(items) - limit))
    return "\n".join(lines)
