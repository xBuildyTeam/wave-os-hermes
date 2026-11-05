"""Screening for memories before they leave Hermes, and for recalled text before it reaches the model.

Matches Wave Wallet Mint's rules (warnings.js) so a pack the plugin accepts won't be refused at mint,
and is STRICTER for agent memory: keys, tokens and recovery phrases are blocked even for private cards.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_PRIV = re.compile(r"(private|priv[ _-]?key|secret|seed|signing key|wallet key)[^\n]{0,40}?(0x)?[0-9a-fA-F]{64}(?![0-9a-fA-F])", re.I)
_PEM = re.compile(r"-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----")
_KEYSTORE = re.compile(r'"crypto"\s*:\s*\{[\s\S]*"ciphertext"', re.I)
_API = re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
_PV1_TEXT = re.compile(r"\bPV1\.[A-Za-z0-9_-]{100,}")

# Prompt-injection markers in RECALLED text. Recalled memory is data, never instructions.
_INJECT = re.compile(
    r"(ignore (all |any )?(previous|prior|above) (instructions|messages)|disregard (the )?(system|previous)|"
    r"you are now|new instructions:|system prompt|<\s*/?\s*(system|tool|assistant)\s*>|BEGIN (SYSTEM|INSTRUCTIONS)|"
    r"call the tool|run this command|exfiltrate|send (it|this|them) to)", re.I)


@lru_cache(maxsize=1)
def _bip39() -> frozenset[str]:
    p = Path(__file__).with_name("bip39_english.txt")
    return frozenset(w.strip() for w in p.read_text().split() if w.strip())


def _has_seed_phrase(text: str) -> bool:
    words = [w for w in re.split(r"[^a-z]+", text.lower()) if w]
    run = 0
    wl = _bip39()
    for w in words:
        if len(w) >= 3 and w in wl:
            run += 1
            if run >= 12:
                return True
        else:
            run = 0
    return False


def scan(text: str, *, private: bool) -> list[dict]:
    """[{level: block|warn, label}]. Block = never leaves Hermes."""
    if not text:
        return []
    out = []
    for label, hit in (
        ("a private key", bool(_PRIV.search(text))),
        ("a PEM private key", bool(_PEM.search(text))),
        ("a recovery phrase", _has_seed_phrase(text)),
        ("a wallet keystore", bool(_KEYSTORE.search(text))),
        ("an API key or token", bool(_API.search(text))),
        ("a login token (JWT)", bool(_JWT.search(text))),
        ("encrypted card text", bool(_PV1_TEXT.search(text))),
    ):
        if hit:
            out.append({"level": "block", "label": label})
    if not private:
        if _EMAIL.search(text):
            out.append({"level": "warn", "label": "an email address"})
        if _PHONE.search(text):
            out.append({"level": "warn", "label": "a phone number"})
    return out


def blocked(text: str, *, private: bool) -> list[str]:
    return [w["label"] for w in scan(text, private=private) if w["level"] == "block"]


def injection_flags(text: str) -> bool:
    return bool(_INJECT.search(text or ""))


def neutralize(text: str) -> str:
    """Make recalled text safe to quote: no fake role tags, no fence breaking."""
    t = re.sub(r"<\s*/?\s*(system|tool|assistant|user)\s*>", "[tag]", text or "", flags=re.I)
    return t.replace("```", "'''")
