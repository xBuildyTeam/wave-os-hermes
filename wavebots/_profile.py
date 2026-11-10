"""Add a Wave bot to Hermes as its own bot (a Hermes profile in the sidebar Bots list).

The profile is created with Hermes's own `create_profile` (empty: no cloned config, skills,
channels or keys; it gets only the user's launch model so it runs on their AI and login), then
locked down: every tool family that can touch the computer or the outside world is disabled,
MCP servers are off and nothing is scheduled. Its SOUL.md is built from the bot's verified cards.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from ._avatar import mascot_png
from ._bots import BotError, normalize_name, verify
from ._soul import blocked_soul, build_soul

MARKER = "wavebot.json"
# Tool families an added bot never gets. It answers from its cards; it doesn't run things.
DISABLED_TOOLSETS = ["terminal", "file", "browser", "computer_use", "code_execution", "cronjob", "delegation",
                     "kanban", "skills", "web", "search", "x_search", "image_gen", "video_gen", "connections",
                     "discord", "discord_admin", "feishu_doc", "feishu_drive", "debugging", "memory",
                     "session_search", "tts", "vision", "video"]


class AddError(RuntimeError):
    pass


# --------------------------------------------------------------------------- hermes plumbing --
def _P():
    from hermes_cli import profiles as P  # inside Hermes only (tests swap in a fake)
    return P


def _home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _state_dir() -> Path:
    d = _home() / "wavebots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _yaml_load(p: Path) -> dict:
    if not p.is_file():
        return {}
    txt = p.read_text(encoding="utf-8")
    try:
        import hermes_yaml
        v = hermes_yaml.safe_load(txt)
    except ImportError:
        import yaml
        v = yaml.safe_load(txt)
    return v if isinstance(v, dict) else {}


def _yaml_write(p: Path, data: dict) -> None:
    try:
        from utils import atomic_yaml_write
        atomic_yaml_write(p, data, sort_keys=False)
        return
    except ImportError:
        pass
    import yaml
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    os.replace(tmp, p)


def _write_text(p: Path, text: str) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def profile_name_for(slug: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", (slug or "bot").lower()).strip("-")[:40] or "bot"
    return f"wave-{s}"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------- state --
def _load_index() -> dict:
    try:
        v = json.loads((_state_dir() / "added.json").read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _save_index(idx: dict) -> None:
    _write_text(_state_dir() / "added.json", json.dumps(idx, indent=1, sort_keys=True))


def added() -> list[dict]:
    """Every Wave bot added to Hermes, with its last check. Forgets entries whose profile was
    deleted in Hermes itself."""
    idx, P, out, changed = _load_index(), _P(), [], False
    for prof, rec in sorted(idx.items()):
        if not P.profile_exists(prof):
            idx.pop(prof)
            changed = True
            continue
        out.append({"profile": prof, **rec})
    if changed:
        _save_index(idx)
    return out


def find_added(q: str) -> Optional[dict]:
    q = str(q or "").strip().lower()
    try:
        name = normalize_name(q)
    except BotError:
        name = q
    for rec in added():
        if q in (rec["profile"], rec.get("slug")) or name in (rec.get("tns"), rec.get("ref")):
            return rec
    return None


# --------------------------------------------------------------------------------- the work --
def preview(q: str) -> dict:
    """What Add to Hermes would create, after a full check on Theta. Writes nothing."""
    v = verify(q)
    b = v.get("bot")
    res = {"verify": v, "can_add": False, "reason": ""}
    if not b:
        res["reason"] = ("Couldn't reach Theta to check it. Try again in a moment." if v["status"] == "unreadable"
                         else "That isn't a Wave bot on Theta.")
        return res
    existing = find_added(b.get("tns") or b["ref"])
    res.update({"profile": existing["profile"] if existing else profile_name_for(b["slug"]),
                "already_added": bool(existing), "answer_mode": b["answer_mode"]})
    if not v["ok"]:
        res["reason"] = ("Couldn't reach Theta to check it. Try again in a moment." if v["status"] == "unreadable"
                         else "It didn't pass every check on Theta, so it can't be added.")
    elif b["answer_mode"] != "local":
        res["reason"] = ("This bot is paid or private, so it answers on Wave. That needs Connect to Wave OS, "
                         "which comes in the next version.")
    else:
        res["can_add"] = True
    return res


def add(q: str, _pv: Optional[dict] = None) -> dict:
    """Verify on Theta, then create (or refresh) the Hermes bot. Adding twice reuses the same bot."""
    pv = _pv or preview(q)
    if not pv["can_add"]:
        raise AddError(pv["reason"])
    v = pv["verify"]
    b = v["bot"]
    P, prof = _P(), pv["profile"]
    created = False
    if P.profile_exists(prof):
        pdir = Path(P.get_profile_dir(prof))
        if not (pdir / MARKER).is_file():
            raise AddError(f"You already have a Hermes bot called {prof} that Wave | Bots didn't make, so it won't be touched.")
    else:
        with contextlib.redirect_stdout(io.StringIO()):  # Hermes prints a summary; keep chat/CLI output clean
            P.create_profile(name=prof, no_alias=True, no_skills=True, description=b["pitch"][:200] or None)
        created = True
    try:
        _write_bot(Path(P.get_profile_dir(prof)), b, v["checked_at"])
    except Exception:
        if created:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    P.delete_profile(prof, yes=True)
            except Exception:
                pass
        raise
    idx = _load_index()
    idx[prof] = {"slug": b["slug"], "name": b["name"], "tns": b["tns"], "ref": b["ref"], "official": b["official"],
                 "answer_mode": "local", "added_at": idx.get(prof, {}).get("added_at") or int(time.time()),
                 "checked_at": v["checked_at"], "status": "verified", "update_ref": None, "edited": False}
    _save_index(idx)
    return {"ok": True, "profile": prof, "created": created,
            "bot": {k: b[k] for k in ("name", "tns", "ref", "official")}}


def _write_bot(pdir: Path, b: dict, checked_at: int) -> None:
    # 0. its face in the Bots list, first, so Hermes never lists the new bot without its mascot.
    #    Written to a temp file and swapped in, like Hermes's own profiles.set_asset.
    try:
        assets = pdir / "assets"
        assets.mkdir(exist_ok=True)
        tmp = assets / "avatar.png.tmp"
        tmp.write_bytes(mascot_png(b.get("design") or {}))
        tmp.replace(assets / "avatar.png")
    except ValueError:
        pass
    # 1. locked-down config: keep only the launch model block create_profile seeded
    cfg_path = pdir / "config.yaml"
    cfg = _yaml_load(cfg_path)
    locked = {k: cfg[k] for k in ("model", "_config_version") if k in cfg}
    locked["agent"] = {"disabled_toolsets": list(DISABLED_TOOLSETS)}
    locked["mcp_servers"] = {}
    _yaml_write(cfg_path, locked)
    # 2. who it is
    soul = build_soul(b, checked_at)
    _write_text(pdir / "SOUL.md", soul)
    # 4. roster title and description
    meta_path = pdir / "profile.yaml"
    meta = _yaml_load(meta_path)
    meta["display_name"] = b["name"]
    meta["description"] = b["pitch"][:200]
    ui = meta.setdefault("ui_meta", {}).setdefault("hermes-bots", {})
    ui["title"] = b["name"]
    ui["description"] = b["pitch"][:200]
    ui.setdefault("created", int(time.time() * 1000))
    meta["wavebot"] = {"tns": b["tns"], "ref": b["ref"], "official": b["official"]}
    _yaml_write(meta_path, meta)
    # 5. what we installed, so later checks can tell a local edit from an update
    _write_text(pdir / MARKER, json.dumps({
        "schema": "wave.hermes-bot/1", "tns": b["tns"], "ref": b["ref"], "slug": b["slug"], "name": b["name"],
        "creator": b["creator"], "official": b["official"], "rules_ref": b["rules_ref"], "design_ref": b["design_ref"],
        "knowledge_refs": b["knowledge_refs"], "soul_sha256": _sha(soul), "checked_at": checked_at,
        "answer_mode": "local"}, indent=1))


def check(q: str) -> dict:
    """Re-check an added bot on Theta. Same listing → verified. Name moved to a newer listing →
    update available (keeps answering as the version you added). Failed check → paused."""
    rec = find_added(q)
    if not rec:
        raise AddError(f"{q} isn't added to Hermes.")
    pdir = Path(_P().get_profile_dir(rec["profile"]))
    marker = json.loads((pdir / MARKER).read_text(encoding="utf-8"))
    v = verify(rec["tns"] or rec["ref"], with_knowledge=False)
    soul_now = (pdir / "SOUL.md").read_text(encoding="utf-8") if (pdir / "SOUL.md").is_file() else ""
    edited = _sha(soul_now) != marker.get("soul_sha256")
    idx = _load_index()
    entry = idx.get(rec["profile"], {})
    if v["status"] == "unreadable":
        status = entry.get("status") or "verified"
        note = "Couldn't reach Theta, so this shows the last check."
    elif not v["ok"]:
        status, note = "paused", "Failed a check on Theta, so it's paused until it passes again."
        reason = next((c["label"] + (": " + c["detail"] if c["detail"] else "") for c in v["checks"] if not c["ok"]), "")
        stub = blocked_soul(rec["name"], reason)
        _write_text(pdir / "SOUL.md", stub)
        marker["soul_sha256"] = _sha(stub)
        _write_text(pdir / MARKER, json.dumps(marker, indent=1))
        edited = False
    elif v["bot"]["ref"] != rec["ref"]:
        status, note = "update_available", f"{rec['name']} has an update ({rec['ref']} → {v['bot']['ref']})."
        entry["update_ref"] = v["bot"]["ref"]
    else:
        if entry.get("status") == "paused":  # passes again: rebuild from chain
            add(rec["tns"] or rec["ref"])
            return check(q)
        status, note = "verified", "Verified on Theta."
    if edited:
        note += " Its SOUL.md was edited in Hermes, so it's no longer exactly the verified version."
    entry.update({"status": status, "checked_at": v["checked_at"], "edited": edited})
    idx[rec["profile"]] = entry
    _save_index(idx)
    return {"profile": rec["profile"], "status": status, "note": note, "checks": v["checks"], "edited": edited}


def update(q: str) -> dict:
    """Move an added bot to the listing its name points at now (rebuilds SOUL, avatar and marker).
    Its Hermes chat is kept."""
    rec = find_added(q)
    if not rec:
        raise AddError(f"{q} isn't added to Hermes.")
    return add(rec["tns"] or rec["ref"])


def remove(q: str) -> dict:
    """Delete the Hermes bot (its profile and its chat). The Wave bot on Theta is untouched."""
    rec = find_added(q)
    if not rec:
        raise AddError(f"{q} isn't added to Hermes.")
    P = _P()
    pdir = Path(P.get_profile_dir(rec["profile"]))
    if not (pdir / MARKER).is_file():
        raise AddError(f"{rec['profile']} wasn't made by Wave | Bots, so it won't be deleted from here.")
    with contextlib.redirect_stdout(io.StringIO()):
        P.delete_profile(rec["profile"], yes=True)
    idx = _load_index()
    idx.pop(rec["profile"], None)
    _save_index(idx)
    return {"ok": True, "profile": rec["profile"]}
