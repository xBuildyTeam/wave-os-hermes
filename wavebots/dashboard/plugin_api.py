"""Wave | Bots: Hermes dashboard API, mounted at /api/plugins/wavebots/.

Thin wrappers around the same code the /bots command, CLI and tool use. Everything here reads
public chain data and the user's own Hermes profiles; nothing signs, pays or talks to Wave's servers.
Changes (add / update / remove) only happen from a click on the page.
"""

import base64
import importlib.util
import sys
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
_ROOT = Path(__file__).resolve().parent.parent
_lock = threading.Lock()


def _code_sig() -> float:
    try:
        return max(p.stat().st_mtime for p in _ROOT.glob("*.py"))
    except ValueError:
        return 0.0


def _pkg():
    """Load this plugin's package under a private name; reload when its files change (an update)."""
    name = "_wave_bots_dashboard"
    sig = _code_sig()
    mod = sys.modules.get(name)
    if mod is not None and getattr(mod, "_wb_sig", None) == sig:
        return mod
    for k in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[k]
    spec = importlib.util.spec_from_file_location(name, _ROOT / "__init__.py", submodule_search_locations=[str(_ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    mod._wb_sig = sig
    return mod


def _m(sub: str):
    _pkg()
    return sys.modules["_wave_bots_dashboard." + sub]


_avatars: dict = {}


def _avatar_uri(design: Optional[dict]) -> Optional[str]:
    if not isinstance(design, dict):
        return None
    key = (design.get("pixels"), tuple(design.get("palette") or []), design.get("profileColor"))
    if key not in _avatars:
        try:
            _avatars[key] = "data:image/png;base64," + base64.b64encode(_m("_avatar").mascot_png(design, 128)).decode()
        except Exception:
            _avatars[key] = None
    return _avatars[key]


def _errors():
    return (_m("_profile").AddError, _m("_bots").BotError)


def _bot_out(b: dict) -> dict:
    core = _m("_core")
    out = core._card(b)
    out["avatar"] = _avatar_uri(b.get("design"))
    out["added_status"] = b.get("added_status")
    return out


@router.get("/banner")
def banner():
    p = _ROOT / "assets" / "banner.jpg"
    return {"data": "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode() if p.is_file() else None}


@router.get("/bots")
def bots(refresh: bool = False):
    core = _m("_core")
    with _lock:
        rows = core.bots(refresh=refresh)
    return {"version": core.VERSION, "bots": [_bot_out(b) for b in rows]}


@router.get("/bot")
def bot(q: str):
    core = _m("_core")
    try:
        r = core.info(q)
    except _errors() as e:
        raise HTTPException(400, str(e))
    if r.get("bot"):
        r["bot"]["avatar"] = _avatar_uri(r["bot"].pop("design", None))
    return r


@router.get("/added")
def added():
    return {"added": _m("_profile").added()}


class BotIn(BaseModel):
    bot: str = Field(min_length=1, max_length=120)


@router.post("/preview")
def preview(body: BotIn):
    A = _m("_profile")
    pv = A.preview(body.bot)
    b = (pv.get("verify") or {}).get("bot") or {}
    return {"can_add": pv["can_add"], "reason": pv["reason"], "profile": pv.get("profile"),
            "already_added": pv.get("already_added", False), "status": pv["verify"]["status"],
            "checks": pv["verify"]["checks"], "name": b.get("name"), "tns": b.get("tns"), "ref": b.get("ref"),
            "knowledge": [{"ref": k["ref"], "title": k["title"]} for k in b.get("knowledge") or []],
            "disabled_toolsets": A.DISABLED_TOOLSETS}


@router.post("/add")
def add(body: BotIn):
    A = _m("_profile")
    try:
        with _lock:
            return A.add(body.bot)
    except _errors() as e:
        raise HTTPException(400, str(e))


@router.post("/check")
def check(body: BotIn):
    try:
        return _m("_profile").check(body.bot)
    except _errors() as e:
        raise HTTPException(400, str(e))


@router.post("/check_all")
def check_all():
    return {"results": _m("_core").recheck_due(force=True)}


@router.post("/update")
def update(body: BotIn):
    try:
        with _lock:
            return _m("_profile").update(body.bot)
    except _errors() as e:
        raise HTTPException(400, str(e))


@router.post("/remove")
def remove(body: BotIn):
    try:
        with _lock:
            return _m("_profile").remove(body.bot)
    except _errors() as e:
        raise HTTPException(400, str(e))


# ----------------------------------------------------------------------------- Connect to Wave OS --
@router.get("/connect")
def connect_state():
    return _m("_connect").background_state()


@router.post("/connect/start")
def connect_start():
    W = _m("_connect")
    try:
        return W.start_background()  # the page opens the link itself
    except W.ConnectError as e:
        raise HTTPException(502, str(e))


@router.post("/connect/cancel")
def connect_cancel():
    _m("_connect").cancel_background()
    return {"ok": True}


@router.post("/disconnect")
def disconnect():
    W = _m("_connect")
    W.cancel_background()
    return W.disconnect()


class AskIn(BaseModel):
    bot: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=8000)


@router.post("/ask")
def ask(body: AskIn):
    W = _m("_connect")
    try:
        return W.ask(body.bot, body.question)  # free bots only from the page (max price 0)
    except W.ConnectError as e:
        raise HTTPException(400, str(e))
