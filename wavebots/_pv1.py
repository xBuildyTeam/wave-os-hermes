"""PV1 private cards (BrainVault card 80, rev 3), decrypt side, matching Wave Wallet Mint's pv1.js.

payload = "PV1." + base64url( ephPub 65 B uncompressed || nonce 12 B || AES-256-GCM ciphertext || tag 16 B )
key     = HKDF-SHA256(ikm = ECDH shared point, 65 B uncompressed; salt empty; info "brainvault-pv1"; 32 B)
Readers also try the 33 B compressed point and the 32 B x-only value (old cards).

Uses only `cryptography` (a core Hermes dependency). Its ECDH returns the x-coordinate only, so we
rebuild both possible y values and let the AES-GCM tag pick the right one (y is public data).
"""
from __future__ import annotations

import base64
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PREFIX = "PV1."
_INFO = b"brainvault-pv1"
_P = 2**256 - 2**32 - 977  # secp256k1 field prime
_B64URL = re.compile(r"^[A-Za-z0-9_-]*$")


class PV1Error(ValueError):
    pass


def is_pv1(text: object) -> bool:
    return isinstance(text, str) and text.startswith(PREFIX) and len(text) > 4 + 124


def _unb64url(s: str) -> bytes:
    if not _B64URL.match(s):
        raise PV1Error("Not base64url")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _hkdf(ikm: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(ikm)


def private_key_from_hex(hex_key: str) -> ec.EllipticCurvePrivateKey:
    h = hex_key[2:] if hex_key.startswith("0x") else hex_key
    if not re.fullmatch(r"[0-9a-fA-F]{64}", h):
        raise PV1Error("Private key must be 32 bytes of hex")
    return ec.derive_private_key(int(h, 16), ec.SECP256K1())


def public_key_hex(key: ec.EllipticCurvePrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return "0x" + raw.hex()


def new_transport_key() -> tuple[ec.EllipticCurvePrivateKey, str]:
    """A one-time keypair for pairing/restore. Returns (private key, 0x04… public key hex)."""
    k = ec.generate_private_key(ec.SECP256K1())
    return k, public_key_hex(k)


def private_key_hex(key: ec.EllipticCurvePrivateKey) -> str:
    return "0x" + key.private_numbers().private_value.to_bytes(32, "big").hex()


def _candidates(x: bytes) -> list[bytes]:
    xi = int.from_bytes(x, "big")
    y2 = (pow(xi, 3, _P) + 7) % _P
    y = pow(y2, (_P + 1) // 4, _P)
    out: list[bytes] = []
    for yy in (y, _P - y):
        point = b"\x04" + x + yy.to_bytes(32, "big")
        comp = bytes([3 if yy & 1 else 2]) + x
        out += [point, comp]
    out.append(x)
    return out


def decrypt(payload: str, key: ec.EllipticCurvePrivateKey | str) -> str:
    """Return the plaintext, or raise PV1Error if this key can't open it (wrong key or tampered)."""
    if isinstance(key, str):
        key = private_key_from_hex(key)
    if not is_pv1(payload):
        raise PV1Error("Not a PV1 card")
    raw = _unb64url(payload[4:])
    if len(raw) < 65 + 12 + 16 or raw[0] != 4:
        raise PV1Error("Bad PV1 envelope")
    eph, nonce, ct = raw[:65], raw[65:77], raw[77:]
    try:
        eph_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), eph)
    except ValueError as e:
        raise PV1Error("Bad PV1 ephemeral key") from e
    x = key.exchange(ec.ECDH(), eph_pub)
    for shared in _candidates(x):
        try:
            pt = AESGCM(_hkdf(shared)).decrypt(nonce, ct, None)
        except InvalidTag:
            continue
        try:
            return pt.decode("utf-8")
        except UnicodeDecodeError as e:
            raise PV1Error("PV1 plaintext isn't UTF-8") from e
    raise PV1Error("This key can't open that card")


def encrypt(plaintext: str, recipient_pub_hex: str) -> str:
    """PV1 encrypt (writer side, 65 B shared point). The plugin itself never mints; used in tests
    and for sealing local data to the agent key."""
    pub = bytes.fromhex(recipient_pub_hex[2:] if recipient_pub_hex.startswith("0x") else recipient_pub_hex)
    rpub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pub)
    eph = ec.generate_private_key(ec.SECP256K1())
    x = eph.exchange(ec.ECDH(), rpub)
    # the true shared point = eph * R; recover its y by matching against a second, independent derivation
    # is impossible without point math, so compute it directly:
    point = _mul_point(eph.private_numbers().private_value, rpub)
    if point[1:33] != x:
        raise PV1Error("Key agreement self-check failed")
    nonce = os.urandom(12)
    ct = AESGCM(_hkdf(point)).encrypt(nonce, plaintext.encode("utf-8"), None)
    eph_raw = eph.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return PREFIX + _b64url(eph_raw + nonce + ct)


# --- minimal secp256k1 point multiply (writer side only; the decrypt path never uses it) ---
def _mul_point(k: int, pub: ec.EllipticCurvePublicKey) -> bytes:
    nums = pub.public_numbers()
    rx, ry = nums.x, nums.y

    def add(p1, p2):
        if p1 is None:
            return p2
        if p2 is None:
            return p1
        (x1, y1), (x2, y2) = p1, p2
        if x1 == x2 and (y1 + y2) % _P == 0:
            return None
        if p1 == p2:
            lam = (3 * x1 * x1) * pow(2 * y1, -1, _P) % _P
        else:
            lam = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
        x3 = (lam * lam - x1 - x2) % _P
        return (x3, (lam * (x1 - x3) - y1) % _P)

    r, q = None, (rx, ry)
    while k:
        if k & 1:
            r = add(r, q)
        q = add(q, q)
        k >>= 1
    return b"\x04" + r[0].to_bytes(32, "big") + r[1].to_bytes(32, "big")
