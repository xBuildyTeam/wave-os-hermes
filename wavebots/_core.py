"""Shared actions behind the tool, the /bots command, the CLI and the Bots tab."""
from __future__ import annotations

import json
import threading
import time

from . import _profile as A
from ._bots import BotError, catalog, summary, verify

VERSION = "0.3.2"
CATALOG_TTL = 3600
RECHECK_AFTER = 24 * 3600
_lock = threading.Lock()


def _cache_path():
    return A._state_dir() / "catalog.json"


def bots(refresh: bool = False) -> list[dict]:
    """The official bots from Theta, cached for an hour (a fresh check takes ~15 s). Each one has
    verified/status from the last check and `added` if it's already a Hermes bot."""
    with _lock:
        data = None
        try:
            data = json.loads(_cache_path().read_text(encoding="utf-8"))
        except Exception:
            pass
        if refresh or not data or time.time() - data.get("at", 0) > CATALOG_TTL:
            fresh = catalog()
            if fresh:
                data = {"at": int(time.time()), "bots": fresh}
                A._write_text(_cache_path(), json.dumps(data))
        out = list((data or {}).get("bots") or [])
    have = {r["tns"]: r for r in _safe_added()}
    for b in out:
        rec = have.get(b.get("tns"))
        b["added"] = bool(rec)
        b["profile"] = rec["profile"] if rec else None
        b["added_status"] = rec.get("status") if rec else None
    return out


def _safe_added() -> list[dict]:
    try:
        return A.added()
    except Exception:
        return []


def find(query: str = "", limit: int = 10) -> list[dict]:
    q = str(query or "").strip().lower()
    words = [w for w in q.split() if w]
    rows = []
    for b in bots():
        hay = " ".join([b.get("name", ""), b.get("slug", ""), b.get("pitch", ""), b.get("category", ""),
                        b.get("role", "")]).lower()
        score = sum(hay.count(w) for w in words) if words else 1
        if b.get("slug") == q or b.get("tns") == q:
            score += 100
        if score:
            rows.append((score + (5 if b.get("added") else 0), b))
    rows.sort(key=lambda x: -x[0])
    return [_card(b) for _, b in rows[:limit]]


def _card(b: dict) -> dict:
    return {k: b.get(k) for k in ("name", "slug", "tns", "ref", "pitch", "category", "official", "verified", "status",
                                  "price_tfuel", "free_per_day", "answer_mode", "added", "profile", "role")}


def info(q: str) -> dict:
    v = verify(q)
    b = v.get("bot") or {}
    rec = A.find_added(b.get("tns") or q) if b else None
    return {"ok": v["ok"], "status": v["status"], "summary": summary(v), "checks": v["checks"],
            "bot": {**_card(b), "knowledge": [{"ref": k["ref"], "title": k["title"]} for k in b.get("knowledge") or []],
                    "rules_ref": b.get("rules_ref"), "design_ref": b.get("design_ref"),
                    "creator": b.get("creator"), "design": b.get("design")} if b else None,
            "added": bool(rec), "profile": rec["profile"] if rec else None}


def recheck_due(force: bool = False) -> list[dict]:
    """Re-check every added bot whose last check is older than a day (or all, with force)."""
    out = []
    for rec in _safe_added():
        if force or time.time() - (rec.get("checked_at") or 0) > RECHECK_AFTER:
            try:
                out.append(A.check(rec["profile"]))
            except Exception as e:
                out.append({"profile": rec["profile"], "status": "error", "note": str(e)})
    return out


def fmt_list(rows: list[dict]) -> str:
    if not rows:
        return "No bots matched."
    lines = []
    for b in rows:
        tag = "Added" if b.get("added") else ("Free" if not b.get("price_tfuel") else f"{b['price_tfuel']} TFUEL")
        ok = "✓" if b.get("verified") else "✗"
        lines.append(f"{ok} {b['name']:<8} {b['tns']:<22} {tag:<6} {b.get('pitch', '')}")
    return "\n".join(lines)


__all__ = ["VERSION", "bots", "find", "info", "recheck_due", "fmt_list", "BotError"]
