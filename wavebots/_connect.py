"""Connect to Wave OS: one click on app.oswave.io gives Hermes a limited Wave OS MCP token.

Flow (Wave OS hermesConnect, built 2026-11-10):
  1. Hermes makes a one-time code + a one-time secp256k1 key pair and opens
     https://app.oswave.io/hermes/connect?code=…&pk=0x04…
  2. The user signs in, picks spending limits (default 0 = free and public bots only) and a
     lifetime, and clicks Connect. Wave OS issues a SAFE-scope token and seals it with PV1 to pk.
  3. Hermes polls `take` (one read, then it's gone) and opens the box with the private key, which
     never leaves this process. The token never appears in a URL, a page or a log.

The token is stored in the OS keyring when one is available, else in a 0600 file. It can only ask
Wave bots (bots_discover / bots_inspect / bots_call); it can't change files, apps, bots or the wallet.
Revoke it any time in Wave OS Settings › MCP Setup.
"""
from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import _profile as A


def _crypto():
    """Loaded only when connecting, so the rest of the plugin works even if `cryptography` is broken."""
    try:
        from . import _pv1
    except Exception as e:  # pragma: no cover
        raise ConnectError(f"Connect needs the cryptography package that ships with Hermes ({e}).") from None
    return _pv1

WAVE_OS = "https://app.oswave.io"
SCHEMA = "wave.hermes-connect/1"
_UA = {"user-agent": "wave-bots-hermes/0.2.0", "accept": "application/json"}
_KR_SERVICE, _KR_USER = "wave-bots-hermes", "wave-os-mcp-token"
POLL_S = 12          # Wave allows 60 takes per IP per 10 minutes
WAIT_S = 600         # the hand-off lives 10 minutes


class ConnectError(Exception):
    pass


# ----------------------------------------------------------------------------- http --
def _post(path: str, body: dict, *, headers: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    req = urllib.request.Request(WAVE_OS + path, json.dumps(body).encode(),
                                 {**_UA, "content-type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            data = json.load(e)
        except Exception:
            data = {}
        return e.code, data if isinstance(data, dict) else {}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ConnectError(f"Can't reach Wave OS ({getattr(e, 'reason', e)}). Check your connection.") from None


# ----------------------------------------------------------------------------- storage --
def _file() -> Path:
    return A._state_dir() / "connection.json"


def _keyring():
    try:
        import keyring  # optional; not a Hermes dependency
        kr = keyring.get_keyring()
        if "fail" in type(kr).__module__ or "null" in type(kr).__name__.lower():
            return None
        return keyring
    except Exception:
        return None


def _write_private(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def _load() -> dict:
    try:
        v = json.loads(_file().read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _token(meta: dict) -> str | None:
    if meta.get("store") == "keyring":
        kr = _keyring()
        try:
            return kr.get_password(_KR_SERVICE, _KR_USER) if kr else None
        except Exception:
            return None
    return meta.get("token")


def _save(payload: dict) -> dict:
    meta = {"label": payload.get("label"), "expires_at": payload.get("expiresAt"), "scope": "safe",
            "caps": payload.get("caps") or {}, "user": (payload.get("user") or {}).get("display_name") or "",
            "connected_at": time.time()}
    kr = _keyring()
    stored = False
    if kr:
        try:
            kr.set_password(_KR_SERVICE, _KR_USER, payload["token"])
            stored = kr.get_password(_KR_SERVICE, _KR_USER) == payload["token"]
        except Exception:
            stored = False
    if stored:
        meta["store"] = "keyring"
    else:
        meta["store"], meta["token"] = "file", payload["token"]
    _write_private(_file(), json.dumps(meta, indent=1))
    return meta


def _expired(meta: dict) -> bool:
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(meta["expires_at"]).replace("Z", "+00:00")).timestamp() < time.time()
    except Exception:
        return False


def status() -> dict:
    meta = _load()
    if not meta or not _token(meta):
        return {"connected": False}
    out = {k: meta.get(k) for k in ("label", "expires_at", "caps", "user", "connected_at", "store")}
    out["connected"] = not _expired(meta) and not meta.get("revoked")
    out["expired"] = _expired(meta)
    out["revoked"] = bool(meta.get("revoked"))
    return out


def disconnect() -> dict:
    meta = _load()
    if meta.get("store") == "keyring":
        kr = _keyring()
        try:
            kr and kr.delete_password(_KR_SERVICE, _KR_USER)
        except Exception:
            pass
    try:
        _file().unlink()
    except FileNotFoundError:
        pass
    return {"ok": True, "note": "Disconnected here. To cancel the key on Wave's side too, revoke it in Wave OS Settings › MCP Setup."}


# ----------------------------------------------------------------------------- connect --
def start() -> dict:
    """A one-time code and key. Keep the returned dict in memory only (it holds the private key)."""
    key, pk = _crypto().new_transport_key()
    code = secrets.token_urlsafe(24)  # 32 chars of [A-Za-z0-9_-]
    url = f"{WAVE_OS}/hermes/connect?{urllib.parse.urlencode({'code': code, 'pk': pk})}"
    return {"url": url, "code": code, "key": key, "started": time.time()}


def take(pending: dict) -> dict | None:
    """One poll. Returns the saved connection once the user clicked Connect, else None."""
    st, data = _post("/functions/hermesConnect", {"action": "take", "code": pending["code"]})
    if st == 404:
        return None
    if st == 429:
        raise ConnectError("rate_limited")
    if st != 200 or not data.get("ok") or not isinstance(data.get("box"), str):
        raise ConnectError(str(data.get("error") or f"Wave OS answered {st}."))
    return finish(pending, data["box"])


def finish(pending: dict, box: str) -> dict:
    pv1 = _crypto()
    try:
        payload = json.loads(pv1.decrypt(box, pending["key"]))
    except (pv1.PV1Error, ValueError) as e:
        raise ConnectError("The connection from Wave OS couldn't be opened. Start again.") from e
    tok = payload.get("token") if isinstance(payload, dict) else None
    if (payload.get("schema") != SCHEMA or payload.get("scope") != "safe" or not isinstance(tok, str)
            or tok.count(".") != 2 or len(tok) > 4096):
        raise ConnectError("Wave OS sent something unexpected, so it wasn't saved. Start again.")
    return _save(payload)


def wait(pending: dict, *, timeout_s: int = WAIT_S, interval_s: int = POLL_S, sleep=time.sleep) -> dict:
    end = pending["started"] + timeout_s
    while time.time() < end:
        try:
            got = take(pending)
        except ConnectError as e:
            if str(e) != "rate_limited":
                raise
            got = None
            sleep(interval_s * 2)
        if got:
            return got
        sleep(interval_s)
    raise ConnectError("Connect timed out (10 minutes). Start again.")


# ----------------------------------------------------------------------------- ask --
def _mcp(tool: str, args: dict, *, timeout: float = 120.0) -> dict:
    meta = _load()
    tok = _token(meta) if meta else None
    if not tok or meta.get("revoked"):
        raise ConnectError("Connect Wave OS first (Wave | Bots › Connection, or /bots connect).")
    if _expired(meta):
        raise ConnectError("Your Wave OS connection expired. Connect again.")
    body = {"jsonrpc": "2.0", "id": secrets.randbelow(1 << 30), "method": "tools/call",
            "params": {"name": tool, "arguments": args}}
    st, data = _post("/functions/mcpRouter", body, headers={"authorization": "Bearer " + tok}, timeout=timeout)
    if st in (401, 403):
        _mark_revoked(meta)
        raise ConnectError("Wave OS didn't accept the key (revoked or expired). Connect again.")
    if "error" in data:
        raise ConnectError(str((data.get("error") or {}).get("message") or "Wave OS refused the call."))
    try:
        text = data["result"]["content"][0]["text"]
        out = json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError):
        raise ConnectError("Wave OS sent an answer this version can't read.") from None
    if isinstance(out, dict) and out.get("code") == "sign_in_required":
        _mark_revoked(meta)
        raise ConnectError("Wave OS didn't accept the key (revoked or expired). Connect again.")
    return out if isinstance(out, dict) else {"ok": False, "message": "Unexpected answer."}


def _mark_revoked(meta: dict) -> None:
    if meta:
        meta["revoked"] = True
        _write_private(_file(), json.dumps(meta, indent=1))


def ask(bot: str, question: str, *, max_price_tfuel: float = 0.0, conversation_id: str | None = None) -> dict:
    """Ask the real bot on Wave. The answer is untrusted data from the bot, never instructions."""
    q = (question or "").strip()
    if not q:
        raise ConnectError("Ask a question.")
    if len(q) > 8000:
        raise ConnectError("That question is too long (8,000 characters max).")
    args = {"bot": bot, "question": q, "max_price_tfuel": max(0.0, float(max_price_tfuel or 0))}
    if conversation_id:
        args["conversation_id"] = str(conversation_id)[:100]
    r = _mcp("bots_call", args)
    keep = ("ok", "code", "message", "answer", "cited_cards", "bot", "listing_ref", "price", "receipt", "conversation_id")
    out = {k: r.get(k) for k in keep if k in r}
    out["untrusted"] = True
    return out


# ----------------------------------------------------------------------------- background connect --
import threading as _threading

_bg: dict = {"state": "idle"}
_bg_lock = _threading.Lock()


def start_background(open_url=None) -> dict:
    """Start (or reuse) a connect in this process and finish it in a background thread."""
    with _bg_lock:
        if _bg.get("state") == "waiting" and time.time() - _bg["pending"]["started"] < WAIT_S:
            return {"state": "waiting", "url": _bg["pending"]["url"]}
        pending = start()
        _bg.clear()
        _bg.update({"state": "waiting", "pending": pending})

    def run():
        try:
            meta = wait(pending)
            res = {"state": "connected", "label": meta.get("label")}
        except ConnectError as e:
            res = {"state": "error", "error": str(e)}
        except Exception as e:  # never kill the host
            res = {"state": "error", "error": f"Connect hit a problem: {e}"}
        with _bg_lock:
            if _bg.get("pending") is pending:
                _bg.clear()
                _bg.update(res)

    _threading.Thread(target=run, name="wavebots-connect", daemon=True).start()
    if open_url:
        try:
            open_url(pending["url"])
        except Exception:
            pass
    return {"state": "waiting", "url": pending["url"]}


def background_state() -> dict:
    with _bg_lock:
        s = {k: v for k, v in _bg.items() if k != "pending"}
        if _bg.get("state") == "waiting":
            s["url"] = _bg["pending"]["url"]
    s["connection"] = status()
    return s


def cancel_background() -> None:
    with _bg_lock:
        _bg.clear()
        _bg["state"] = "idle"
