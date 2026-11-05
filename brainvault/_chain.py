"""Read BrainVault v3 straight from Theta mainnet. Read-only: no keys, no signing, no sends.

Every card is hash-checked: keccak256(content) must equal the contentHash the contract logged.
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Iterator

from ._keccak import keccak256

RPC_URL = "https://eth-rpc-api.thetatoken.org/rpc"
BRAINVAULT_V3 = "0xdb8230f5a2859fca29e0ae6c8521784c1a34dc90"
CHAIN_ID = 361
MAX_LOG_RANGE = 5000  # Theta caps eth_getLogs at 5,000 blocks per query
TOPIC_CARD_MINTED = "0x" + keccak256(
    b"CardMinted(uint256,address,bytes32,bytes32,uint256,bool,bytes32,string[],bytes)").hex()
SEL_CARDS = "0x" + keccak256(b"cards(uint256)").hex()[:8]
_UA = {"content-type": "application/json", "user-agent": "hermes-brainvault/0.1"}


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

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)


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
    recipient_id = "0x" + _word(data, 3).hex()
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
        "block": int(log["blockNumber"], 16), "tx": log.get("transactionHash"),
        "isPrivate": is_private, "recipientId": recipient_id.lower(), "supersedes": supersedes,
        "tags": tags, "contentHash": content_hash.lower(),
        "text": content.decode("utf-8", "replace"),
        "sha_ok": "0x" + keccak256(content).hex() == content_hash.lower(),
        "size": len(content),
    }


def recipient_id_for(address: str) -> str:
    a = address.lower().removeprefix("0x")
    if len(a) != 40:
        raise ValueError("Not an address")
    return "0x" + "0" * 24 + a


def card_info(rpc: Rpc, card_id: int) -> dict | None:
    res = rpc.call("eth_call", [{"to": BRAINVAULT_V3, "data": SEL_CARDS + card_id.to_bytes(32, "big").hex()}, "latest"])
    d = bytes.fromhex(res[2:])
    creator = "0x" + _word(d, 0)[-20:].hex()
    if int(creator, 16) == 0:
        return None
    return {"creator": creator, "mintedAt": _uint(_word(d, 1)), "mintBlock": _uint(_word(d, 2)),
            "isPrivate": bool(_uint(_word(d, 3))), "contentHash": "0x" + _word(d, 4).hex()}


def read_card(rpc: Rpc, ref: str) -> dict:
    if not ref.startswith("v3:") or not ref[3:].isdigit():
        raise ValueError("Use a v3 card ref like v3:12")
    cid = int(ref[3:])
    info = card_info(rpc, cid)
    if not info:
        raise ChainError(f"{ref} doesn't exist")
    blk = hex(info["mintBlock"])
    logs = rpc.call("eth_getLogs", [{"address": BRAINVAULT_V3, "fromBlock": blk, "toBlock": blk,
                                     "topics": [TOPIC_CARD_MINTED, "0x" + cid.to_bytes(32, "big").hex()]}])
    if not logs:
        raise ChainError(f"No mint log for {ref}")
    card = decode_card_log(logs[0])
    card["sha_ok"] = card["sha_ok"] and card["contentHash"] == info["contentHash"].lower()
    card["mintedAt"] = info["mintedAt"]
    return card


def first_block(rpc: Rpc) -> int:
    """BrainVault v3's first card block: nothing older is worth scanning."""
    info = card_info(rpc, 1)
    return info["mintBlock"] if info else 0


def scan_creator(rpc: Rpc, creator: str, from_block: int, to_block: int) -> Iterator[dict]:
    """Every card minted by `creator` in [from_block, to_block], in 5,000-block pages."""
    topic = "0x" + "0" * 24 + creator.lower().removeprefix("0x")
    b = from_block
    while b <= to_block:
        e = min(b + MAX_LOG_RANGE - 1, to_block)
        logs = rpc.call("eth_getLogs", [{"address": BRAINVAULT_V3, "fromBlock": hex(b), "toBlock": hex(e),
                                         "topics": [TOPIC_CARD_MINTED, [], topic]}])  # Theta: [] is the wildcard, null matches nothing
        for lg in logs:
            yield decode_card_log(lg)
        b = e + 1
