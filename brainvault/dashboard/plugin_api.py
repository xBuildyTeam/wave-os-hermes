"""Wave OS BrainVault: Hermes dashboard API, mounted at /api/plugins/brainvault/.

Thin wrappers around the same Vault the memory provider and CLI use, so the three surfaces can't drift.
The dashboard never signs or mints: "Send to Wave" opens Wave Web, where the user mints with Wave Wallet Mint.
"""

import importlib.util
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


_ROOT = Path(__file__).resolve().parent.parent


def _installed_version() -> str:
    """The version on disk right now (plugin.yaml), so an update shows up without a restart."""
    try:
        for ln in (_ROOT / "plugin.yaml").read_text(encoding="utf-8").splitlines():
            if ln.startswith("version:"):
                return ln.split(":", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


_PAGE_VERSION = _installed_version()  # what this page's routes were loaded from


def _api_hash() -> str:
    import hashlib
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        return ""


_API_HASH = _api_hash()  # routes only change when this file does


def _code_sig() -> float:
    try:
        return max(p.stat().st_mtime for p in _ROOT.glob("*.py"))
    except ValueError:
        return 0.0


def _pkg():
    """Load this plugin's package (the folder above dashboard/) under a private name.

    Reloads it when the plugin's files change on disk (an update), so the page uses new code without a
    Hermes restart. New page routes still need one; the page says so."""
    name = "_wave_brainvault_dashboard"
    sig = _code_sig()
    mod = sys.modules.get(name)
    if mod is not None and getattr(mod, "_bv_sig", None) == sig:
        return mod
    for k in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[k]
    root = _ROOT
    spec = importlib.util.spec_from_file_location(name, root / "__init__.py", submodule_search_locations=[str(root)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    mod._bv_sig = sig
    return mod


def _home() -> str:
    from hermes_constants import get_hermes_home
    return str(get_hermes_home())


def _vault():
    _pkg()
    core = sys.modules["_wave_brainvault_dashboard._core"]
    return core.Vault(_home()), core


_pair: dict[str, Any] = {"state": "idle"}
_pair_lock = threading.Lock()


def _short(a: Optional[str]) -> Optional[str]:
    return f"{a[:6]}…{a[-4:]}" if a and len(a) > 12 else a


def _mem_out(m: dict) -> dict:
    return {"id": m["fp"], "title": m["title"], "body": m["body"], "tags": m["tags"], "private": m["private"],
            "trust": m["trust"], "state": m["state"], "ref": m.get("card_ref"), "created": m["created"],
            "exported_at": m.get("exported_at")}


def _card_out(c: dict) -> dict:
    text = c.get("text") or ""
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return {"ref": c["ref"], "id": c["id"], "private": bool(c["is_private"]), "opened": bool(c["opened"]),
            "sha_ok": bool(c["sha_ok"]), "readable": c.get("text") is not None, "title": first[:90],
            "text": text[:1200], "tags": c["tags"], "superseded_by": c.get("superseded_by"), "block": c.get("minted_block")}


@router.get("/state")
def state():
    v, core = _vault()
    try:
        st = v.status()
        mems = [_mem_out(m) for m in v.store.memories(limit=300)]
        cards = [_card_out(c) for c in v.store.cards(readable_only=False, limit=300)]
        with _pair_lock:
            pairing = dict(_pair)
        installed = _installed_version()
        chat = v.store.get_meta("provider_version", "") or ""
        versions = {"installed": installed, "page": _PAGE_VERSION, "code": getattr(core, "VERSION", ""), "chat": chat,
                    "restart_needed": bool(installed and ((_api_hash() != _API_HASH) or (chat and chat != installed)))}
        return {"versions": versions, "status": st, "wallet_short": _short(st.get("wallet")), "memories": mems, "cards": cards,
                "pairing": pairing, "wave_web": v.cfg.get("wave_web"), "now": time.time()}
    finally:
        v.store.close()


class RememberIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    title: str = ""
    private: Optional[bool] = None


@router.post("/remember")
def remember(body: RememberIn):
    v, core = _vault()
    try:
        return v.remember(body.text, title=body.title, private=body.private, trust="operator",
                          source={"session": "dashboard"})
    except core.VaultError as e:
        raise HTTPException(400, str(e))
    finally:
        v.store.close()


class IdIn(BaseModel):
    id: str


@router.post("/forget")
def forget(body: IdIn):
    v, _ = _vault()
    try:
        return {"removed": v.forget(body.id)}
    finally:
        v.store.close()


class EditIn(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=4000)
    title: str = ""
    tags: list[str] = []
    private: bool = True


@router.post("/edit")
def edit(body: EditIn):
    v, core = _vault()
    try:
        return v.edit(body.id, text=body.text, title=body.title, tags=body.tags, private=body.private)
    except core.VaultError as e:
        raise HTTPException(400, str(e))
    finally:
        v.store.close()


class EstimateIn(BaseModel):
    ids: list[str] = []


@router.post("/estimate")
def estimate(body: EstimateIn):
    v, _ = _vault()
    try:
        return v.estimate(body.ids or None)
    finally:
        v.store.close()


class SendIn(BaseModel):
    ids: list[str] = []


@router.post("/send")
def send(body: SendIn):
    v, core = _vault()
    try:
        return v.export_pack(fps=body.ids or None)
    except core.VaultError as e:
        raise HTTPException(400, str(e))
    finally:
        v.store.close()


@router.post("/sync")
def sync():
    v, core = _vault()
    try:
        return v.sync()
    except core.VaultError as e:
        raise HTTPException(400, str(e))
    finally:
        v.store.close()


class WalletIn(BaseModel):
    address: str


@router.post("/wallet")
def wallet(body: WalletIn):
    v, core = _vault()
    try:
        v.set_wallet(body.address.strip())
        return {"wallet": v.cfg["wallet"]}
    except core.VaultError as e:
        raise HTTPException(400, str(e))
    finally:
        v.store.close()


@router.get("/recall")
def recall(q: str = "", k: int = 6):
    v, _ = _vault()
    try:
        hits = v.recall(q, max(1, min(int(k), 12))) if q.strip() else []
        return {"results": [{"id": h["id"], "where": h["kind"], "ref": h.get("ref"), "private": h.get("private"),
                             "trust": h["trust"], "title": h.get("title", ""), "text": h["text"][:600],
                             "score": round(float(h.get("score", 0)), 2)} for h in hits]}
    finally:
        v.store.close()


@router.get("/guide")
def guide(q: str = ""):
    v, core = _vault()
    try:
        if not q.strip():
            return {"results": []}
        return v.ask_wavey(q[:300])
    except core.VaultError as e:
        raise HTTPException(400, str(e))
    finally:
        v.store.close()


@router.get("/doctor")
def doctor():
    v, _ = _vault()
    try:
        return v.doctor()
    finally:
        v.store.close()


@router.post("/pair")
def pair():
    with _pair_lock:
        if _pair.get("state") == "waiting" and time.time() < _pair.get("expires", 0):
            return dict(_pair)
    v, core = _vault()
    pend = v.start_pair()
    v.store.close()
    with _pair_lock:
        _pair.clear()
        _pair.update({"state": "waiting", "url": pend["url"], "started": time.time(), "expires": time.time() + 600})

    def wait():
        w, _c = _vault()
        try:
            r = w.pair_wait(pend)
            out = {"state": "paired", "agent": r["agent"]["label"], "key_store": r["key_store"]}
        except Exception as e:  # report, never raise from the thread
            out = {"state": "failed", "error": str(e)}
        finally:
            w.store.close()
        with _pair_lock:
            _pair.clear()
            _pair.update(out)

    threading.Thread(target=wait, name="brainvault-dashboard-pair", daemon=True).start()
    with _pair_lock:
        return dict(_pair)
