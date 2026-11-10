"""Read-only Theta mainnet access for Wave | Bots: BrainVault v3 cards and .theta names.

No keys, no signing, no sends. Every card is hash-checked (keccak256(content) == the logged and
stored contentHash) and every name is read straight from the TNS registry and its resolver.
"""
from __future__ import annotations

import json
import time
import urllib.request

from ._keccak import keccak256

RPC_URL = "https://eth-rpc-api.thetatoken.org/rpc"
BRAINVAULT_V3 = "0xdb8230f5a2859fca29e0ae6c8521784c1a34dc90"
TNS_REGISTRY = "0xffc49362fb293bc063fda33e537be608b357e787"
BOT_TEXT_KEY = "wave.bot"  # the resolver text record a bot name points at its listing with
TOPIC_CARD_MINTED = "0x" + keccak256(
    b"CardMinted(uint256,address,bytes32,bytes32,uint256,bool,bytes32,string[],bytes)").hex()
_UA = {"content-type": "application/json", "user-agent": "hermes-wavebots/0.1"}


def _sel(sig: str) -> str:
    return keccak256(sig.encode()).hex()[:8]


SEL_CARDS = "0x" + _sel("cards(uint256)")
SEL_RESOLVER = _sel("resolver(bytes32)")
SEL_OWNER = _sel("owner(bytes32)")
SEL_TEXT = _sel("text(bytes32,string)")


class ChainError(RuntimeError):
    pass


class Rpc:
    def __init__(self, url: str = RPC_URL, timeout: float = 20.0):
        self.url, self.timeout, self._id = url, timeout, 0

    def call(self, method: str, params: list):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}).encode()
        last = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(self.url, body, _UA)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.load(r)
                if "error" in out:
                    raise ChainError(f"{method}: {out['error'].get('message', out['error'])}")
                return out["result"]
            except ChainError:
                raise
            except Exception as e:  # network / 429 / 5xx: back off and retry
                last = e
                time.sleep(0.6 * (2 ** attempt))
        raise ChainError(f"{method} failed: {last}")


def _word(data: bytes, i: int) -> bytes:
    return data[32 * i:32 * i + 32]


def _uint(b: bytes) -> int:
    return int.from_bytes(b, "big")


def decode_card_log(log: dict) -> dict:
    t = log["topics"]
    data = bytes.fromhex(log["data"][2:])
    content_hash = "0x" + _word(data, 0).hex()
    supersedes = _uint(_word(data, 1))
    is_private = bool(_uint(_word(data, 2)))
    tags_off, content_off = _uint(_word(data, 4)), _uint(_word(data, 5))
    n_tags = _uint(data[tags_off:tags_off + 32])
    tags = []
    for i in range(n_tags):
        so = _uint(data[tags_off + 32 + 32 * i:tags_off + 64 + 32 * i])
        base = tags_off + 32 + so
        ln = _uint(data[base:base + 32])
        tags.append(data[base + 32:base + 32 + ln].decode("utf-8", "replace"))
    cl = _uint(data[content_off:content_off + 32])
    content = data[content_off + 32:content_off + 32 + cl]
    card_id = _uint(bytes.fromhex(t[1][2:]))
    return {
        "ref": f"v3:{card_id}", "id": card_id,
        "creator": "0x" + t[2][-40:].lower(),
        "block": int(log["blockNumber"], 16),
        "isPrivate": is_private, "supersedes": supersedes, "tags": tags,
        "contentHash": content_hash.lower(),
        "text": content.decode("utf-8", "replace"),
        "sha_ok": "0x" + keccak256(content).hex() == content_hash.lower(),
    }


def read_card(rpc: Rpc, ref: str) -> dict:
    """One card by ref, hash-checked against both the mint log and the contract's stored hash."""
    if not isinstance(ref, str) or not ref.startswith("v3:") or not ref[3:].isdigit():
        raise ChainError(f"Not a v3 card ref: {ref!r}")
    cid = int(ref[3:])
    res = rpc.call("eth_call", [{"to": BRAINVAULT_V3, "data": SEL_CARDS + cid.to_bytes(32, "big").hex()}, "latest"])
    d = bytes.fromhex(res[2:])
    if len(d) < 160 or _uint(_word(d, 0)[-20:]) == 0:
        raise ChainError(f"{ref} doesn't exist")
    mint_block, stored_hash = _uint(_word(d, 2)), "0x" + _word(d, 4).hex()
    logs = rpc.call("eth_getLogs", [{"address": BRAINVAULT_V3, "fromBlock": hex(mint_block), "toBlock": hex(mint_block),
                                     "topics": [TOPIC_CARD_MINTED, "0x" + cid.to_bytes(32, "big").hex()]}])
    if not logs:
        raise ChainError(f"No mint log for {ref}")
    card = decode_card_log(logs[0])
    card["sha_ok"] = card["sha_ok"] and card["contentHash"] == stored_hash.lower()
    return card


# ----------------------------------------------------------------------------- .theta names --
def namehash(name: str) -> bytes:
    node = b"\0" * 32
    for label in reversed(name.split(".")):
        node = keccak256(node + keccak256(label.encode()))
    return node


def _addr(hexres) -> str:
    return ("0x" + hexres[-40:]).lower() if isinstance(hexres, str) and len(hexres) >= 42 else "0x" + "0" * 40


def _abi_string_arg(key: str) -> str:
    b = key.encode()
    pad = (len(b) + 31) // 32 * 32
    return (64).to_bytes(32, "big").hex() + len(b).to_bytes(32, "big").hex() + b.ljust(pad, b"\0").hex()


def resolve_bot_name(rpc: Rpc, name: str) -> dict:
    """name.bots.theta → {ref, resolver, owner}. Reads the TNS registry and the resolver's `wave.bot`
    text record directly from Theta; nothing comes from Wave's servers."""
    node = namehash(name)
    resolver = _addr(rpc.call("eth_call", [{"to": TNS_REGISTRY, "data": "0x" + SEL_RESOLVER + node.hex()}, "latest"]))
    owner = _addr(rpc.call("eth_call", [{"to": TNS_REGISTRY, "data": "0x" + SEL_OWNER + node.hex()}, "latest"]))
    if int(resolver, 16) == 0:
        raise ChainError(f"{name} has no resolver on Theta")
    data = "0x" + SEL_TEXT + node.hex() + _abi_string_arg(BOT_TEXT_KEY)
    out = bytes.fromhex(str(rpc.call("eth_call", [{"to": resolver, "data": data}, "latest"]))[2:])
    ref = ""
    if len(out) >= 64:
        off = _uint(out[:32])
        ln = _uint(out[off:off + 32])
        ref = out[off + 32:off + 32 + ln].decode("utf-8", "replace").strip()
    if not ref:
        raise ChainError(f"{name} doesn't point to a bot listing")
    return {"ref": ref, "resolver": resolver, "owner": owner}
