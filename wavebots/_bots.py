"""Find and verify Wave bots straight from Theta.

A bot is a set of BrainVault v3 cards: a listing (wave.bot-listing/1) that names its rules
(wave.rules/1), its mascot (wave.avatar/1) and its knowledge cards, plus a `name.bots.theta`
name whose `wave.bot` text record points at the listing. `verify()` re-checks every link of that
chain on this computer and returns each check, so nothing is trusted because a server said so.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from ._chain import ChainError, Rpc, read_card, resolve_bot_name

OFFICIAL_SIGNER = "0x4e96028447b653e43ff359aaff9f79c0479386db"  # Wave's official bot signer (wave.theta)
OFFICIAL_NAMES = ["chief", "checker", "tally", "planner", "scribe", "clerk", "reader", "risk", "critic", "maker"]
NAME_RE = re.compile(r"^([a-z0-9-]+\.)*[a-z0-9-]+\.theta$")
REF_RE = re.compile(r"^v3:\d{1,9}$")
MAX_KNOWLEDGE = 24          # cards per bot
MAX_KNOWLEDGE_BYTES = 48_000  # total knowledge text put into a local bot


class BotError(RuntimeError):
    pass


def normalize_name(q: str) -> str:
    """'checker' → 'checker.bots.theta'; full .theta names and v3 refs pass through."""
    q = str(q or "").strip().lower()
    if REF_RE.match(q):
        return q
    if q.endswith(".theta"):
        if not NAME_RE.match(q):
            raise BotError(f"{q!r} isn't a valid .theta name")
        return q
    if re.fullmatch(r"[a-z0-9-]{1,40}", q):
        return f"{q}.bots.theta"
    raise BotError("Use a bot name like checker, checker.bots.theta or a listing ref like v3:154")


def _json(card: dict, schema: str) -> dict:
    try:
        obj = json.loads(card["text"])
    except Exception:
        raise BotError(f"{card['ref']} isn't valid JSON")
    if not isinstance(obj, dict) or obj.get("schema") != schema:
        raise BotError(f"{card['ref']} isn't a {schema} card")
    return obj


def _knowledge_body(text: str) -> tuple[str, str]:
    """Wave bot knowledge cards start with 'WAVE BOT CARD / BOT: / TITLE:' lines. Returns (title, body)."""
    title, lines, body_started = "", [], False
    for ln in text.splitlines():
        if not body_started and ln.startswith("TITLE:"):
            title = ln[6:].strip()
            continue
        if not body_started and (ln.strip() in ("WAVE BOT CARD", "") or ln.startswith("BOT:")):
            continue
        body_started = True
        lines.append(ln)
    return title, "\n".join(lines).strip()


def verify(q: str, rpc: Optional[Rpc] = None, *, with_knowledge: bool = True) -> dict:
    """Resolve and check one bot end to end. Never raises for a failed check: it returns ok=False
    with the failing step, so the UI can say exactly what didn't match."""
    rpc = rpc or Rpc()
    checks: list[dict] = []

    def check(cid: str, label: str, ok: bool, detail: str = "") -> bool:
        checks.append({"id": cid, "label": label, "ok": bool(ok), "detail": detail})
        return bool(ok)

    out: dict = {"query": q, "ok": False, "status": "failed", "checks": checks, "checked_at": int(time.time())}
    try:
        target = normalize_name(q)
        name, name_info = None, None
        if REF_RE.match(target):
            ref = target
        else:
            name = target
            name_info = resolve_bot_name(rpc, name)
            ref = name_info["ref"]
            check("name", f"{name} points to listing {ref}", REF_RE.match(ref) is not None, name_info["resolver"])
        listing_card = read_card(rpc, ref)
        if not check("listing_hash", f"Listing {ref} fingerprint matches", listing_card["sha_ok"]):
            return out
        listing = _json(listing_card, "wave.bot-listing/1")
        creator = listing_card["creator"]
        official = creator == OFFICIAL_SIGNER
        tns = str(listing.get("tns") or "").lower()
        if name:
            check("listing_name", f"Listing names itself {tns or '(none)'}", tns == name)
        else:
            name = tns if NAME_RE.match(tns) else None
            if name:  # a ref was given: the name must still point here for the bot to count as current
                try:
                    cur = resolve_bot_name(rpc, name)["ref"]
                    check("name", f"{name} points to listing {cur}", cur == ref,
                          "" if cur == ref else f"this is an older listing; current is {cur}")
                except ChainError as e:
                    check("name", f"{name} resolves", False, str(e))

        rules_ref, design_ref = listing.get("rules"), listing.get("design")
        know_refs = [r for r in (listing.get("knowledge") or []) if isinstance(r, str)][:MAX_KNOWLEDGE]
        refs = [r for r in [rules_ref, design_ref] if isinstance(r, str)] + (know_refs if with_knowledge else [])
        with ThreadPoolExecutor(max_workers=4) as ex:
            cards = dict(zip(refs, ex.map(lambda r: _safe_read(rpc, r), refs)))
        for r in [r for r, c in cards.items() if c is None]:  # a network blip is not a mismatch: retry once, slowly
            time.sleep(0.5)
            cards[r] = _safe_read(rpc, r)
        unreadable = [r for r, c in cards.items() if c is None]
        if unreadable:
            check("read", "Read every card from Theta", False, "couldn't reach Theta for " + ", ".join(unreadable))
            out["status"] = "unreadable"
            return out

        rules_card = cards.get(rules_ref)
        rules = {}
        if check("rules_hash", f"Rules {rules_ref} fingerprint matches", bool(rules_card and rules_card.get("sha_ok"))):
            rules = _json(rules_card, "wave.rules/1")
            want = str(listing.get("rulesHash") or "").lower().removeprefix("sha256:")
            got = hashlib.sha256(rules_card["text"].encode("utf-8")).hexdigest()
            check("rules_match", "Rules are the ones the listing was signed with", bool(want) and want == got)
            check("rules_creator", "Rules signed by the same creator", rules_card["creator"] == creator)
        design_card = cards.get(design_ref)
        design = {}
        if check("design_hash", f"Mascot {design_ref} fingerprint matches", bool(design_card and design_card.get("sha_ok"))):
            design = _json(design_card, "wave.avatar/1")

        knowledge, private_count = [], 0
        if with_knowledge:
            bad = [r for r in know_refs if not (cards.get(r) or {}).get("sha_ok")]
            check("knowledge_hash", f"All {len(know_refs)} knowledge cards' fingerprints match", not bad,
                  ", ".join(bad))
            for r in know_refs:
                c = cards.get(r) or {}
                if c.get("isPrivate"):
                    private_count += 1
                    continue
                if c.get("sha_ok"):
                    title, body = _knowledge_body(c["text"])
                    knowledge.append({"ref": r, "title": title or r, "text": body, "creator": c["creator"]})
        check("signer", "Signed by Wave's official signer" if official else f"Signed by {creator[:6]}…{creator[-4:]} (community)",
              True, creator)

        price = float(listing.get("priceTfuel") or 0)
        mode = str(rules.get("mode") or "public")
        local_ok = price == 0 and mode == "public" and private_count == 0
        ok = all(c["ok"] for c in checks)
        out.update({
            "ok": ok, "status": "verified" if ok else "failed",
            "bot": {
                "name": str(listing.get("name") or ""), "slug": str(listing.get("slug") or ""),
                "pitch": str(listing.get("pitch") or ""), "category": str(listing.get("category") or ""),
                "tns": name or "", "ref": ref, "creator": creator, "official": official,
                "price_tfuel": price, "mode": mode,
                "free_per_day": rules.get("freePerUserPerDay"),
                "role": str((rules.get("cascade") or {}).get("role") or ""),
                "supersedes": listing.get("supersedes"), "rules_ref": rules_ref, "design_ref": design_ref,
                "knowledge_refs": know_refs, "private_knowledge": private_count,
                "design": design, "rules": rules, "knowledge": knowledge,
                "answer_mode": "local" if local_ok else "wave",
            },
        })
    except BotError as e:
        checks.append({"id": "error", "label": "This isn't a valid Wave bot", "ok": False, "detail": str(e)})
        out["status"] = "failed"
    except ChainError as e:
        checks.append({"id": "error", "label": "Couldn't read this bot from Theta", "ok": False, "detail": str(e)})
        out["status"] = "failed" if "doesn't" in str(e) else "unreadable"
    return out


def _safe_read(rpc: Rpc, ref: str) -> Optional[dict]:
    try:
        return read_card(rpc, ref)
    except ChainError:
        return None


def catalog(rpc: Optional[Rpc] = None) -> list[dict]:
    """The official bots, verified (without knowledge text, so it stays fast). Browsing needs no
    Wave account: everything here is public chain data."""
    rpc = rpc or Rpc()
    with ThreadPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(lambda n: verify(n, rpc, with_knowledge=False), OFFICIAL_NAMES))
    out = []
    for r in res:
        b = r.get("bot")
        if b:
            b = {k: v for k, v in b.items() if k not in ("knowledge", "rules")}
            b["verified"] = r["ok"]
            b["status"] = r["status"]
            out.append(b)
    return out


def summary(v: dict) -> str:
    """Human summary of a verify() result."""
    b = v.get("bot") or {}
    head = f"{b.get('name') or v['query']} ({b.get('tns') or b.get('ref') or '?'})"
    lines = [head + (" · Verified on Theta" if v["ok"] else " · Couldn't verify on Theta")]
    for c in v["checks"]:
        lines.append(f"  {'✓' if c['ok'] else '✗'} {c['label']}" + (f": {c['detail']}" if not c["ok"] and c["detail"] else ""))
    return "\n".join(lines)
