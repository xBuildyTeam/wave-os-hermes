"""Wave Web calls: the public card index (discovery only, the chain is the truth) and the one-time pairing drop."""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request

WAVE_WEB = "https://web.oswave.io"
_UA = {"user-agent": "wave-os-hermes-brainvault/0.1", "accept": "application/json"}


class WaveError(RuntimeError):
    def __init__(self, msg: str, status: int = 0, retry_after: int = 0):
        super().__init__(msg)
        self.status, self.retry_after = status, retry_after


def _get(base: str, path: str, params: dict, timeout: float = 20.0) -> dict:
    url = f"{base}{path}?{urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})}"
    return _send(urllib.request.Request(url, headers=_UA), timeout)


def _post(base: str, path: str, body: dict, timeout: float = 20.0) -> dict:
    req = urllib.request.Request(f"{base}{path}", json.dumps(body).encode(), {**_UA, "content-type": "application/json"})
    return _send(req, timeout)


def _send(req, timeout) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            data = json.load(e)
        except Exception:
            data = {}
        raise WaveError(str(data.get("error") or f"HTTP {e.code}"), e.code,
                        int(data.get("retry_after_seconds") or e.headers.get("Retry-After") or 0)) from None
    except urllib.error.URLError as e:
        raise WaveError(f"Can't reach Wave Web ({e.reason})") from None


def creator_cards(creator: str, since_block: int = 0, *, base: str = WAVE_WEB) -> tuple[list[dict], int]:
    """All cards a wallet minted after since_block (metadata only, private included). Returns (cards, indexed_to_block)."""
    out, cursor, indexed = [], None, since_block
    for _ in range(50):  # 50 x 500 cards is plenty; stops runaway paging
        r = _get(base, "/functions/waveApi", {"action": "creator_cards", "creator": creator.lower(),
                                              "since_block": since_block, "limit": 500, "cursor": cursor})
        out += r.get("cards", [])
        indexed = int(r.get("indexed_to_block") or indexed)
        cursor = r.get("next_cursor")
        if not cursor:
            break
    return out, indexed


def new_pair_code() -> str:
    return secrets.token_urlsafe(24)  # 32 chars, matches Wave Web's ^[A-Za-z0-9_-]{22,64}$


def pair_url(code: str, pk: str, *, base: str = WAVE_WEB) -> str:
    return f"{base}/hermes/pair?{urllib.parse.urlencode({'code': code, 'pk': pk})}"


def drop_take(code: str, *, base: str = WAVE_WEB) -> dict | None:
    """One read of the pairing drop. None = nothing there yet (or expired)."""
    try:
        return _post(base, "/functions/agentDrop", {"action": "take", "code": code})
    except WaveError as e:
        if e.status == 404:
            return None
        raise
