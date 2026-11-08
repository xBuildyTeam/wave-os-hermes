"""Wave | BrainVault Mint card rules: the guide Hermes follows, and a safety net that enforces it in code.

The model splits a pasted page into cards using CARD_GUIDE. Whatever it sends, normalize() makes the result
valid anyway: long cards are split at paragraph/sentence boundaries, titles and tags are cleaned, and a raw
page with no cards at all is split here. So a weak or local model still produces good cards.
"""

import re

CARD_MAX_BYTES = 1500   # target per card (private limit is 1,800; leaves room for provenance + encryption)
CARD_MIN_BYTES = 120    # shorter pieces merge with a neighbour (each card costs a network fee)
MAX_CARDS = 40
KINDS = ("fact", "decision", "lesson", "person", "project", "how-to", "preference", "link")
RESERVED = ("user:", "wave:", "bots:", "bot:", "hermes:", "official", "lib:")

CARD_GUIDE = (
    "Wave BrainVault Mint card rules (follow them when making cards):\n"
    "1. One idea per card. A card must make sense on its own months later, with no 'as above' or 'this'. "
    "Name the subject in the first sentence.\n"
    "2. Size: 1-6 sentences, ideally 200-1,200 characters, never over 1,500. Merge tiny related points; split long ones.\n"
    "3. Keep facts exact: names, numbers, dates, amounts, links and quotes as written. Don't add facts or opinions.\n"
    "4. Title: 3-8 words, specific (\"Private cards are encrypted to owner and Hermes\"), no trailing period.\n"
    "5. Tags: up to 3, lowercase, hyphenated topics (e.g. pairing, privacy, theta). The first may be a kind: "
    + ", ".join(KINDS) + ". Never use user:, wave:, bot:, bots: or hermes: tags (Wave adds those).\n"
    "6. Private by default. Only make cards public if the user explicitly asks. Public cards are readable by anyone, forever.\n"
    "7. Never put keys, passwords, tokens, recovery phrases or one-time codes on a card.\n"
    "8. Skip filler, greetings, the user's instruction line, and anything already on another card.\n"
    "9. Order cards the way the source reads. Typical page: 5-15 cards."
)

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_STOPWORDS = set("""a an and are as at be been but by can do does for from has have how if in into is it its
of on or so than that the their then there these they this to was were what when where which who will with
you your our we us not no yes also just only more most very any all each every one two may might should would could
never always about after before over under them those here than like make makes made using used uses user users
wave hermes brainvault mint card cards memory memories""".split())


def _b(s: str) -> int:
    return len(s.encode("utf-8"))


def _split_long(text: str, limit: int = CARD_MAX_BYTES) -> list[str]:
    if _b(text) <= limit:
        return [text]
    parts, cur = [], ""
    for s in _SENT.split(text):
        if _b(s) > limit:  # one giant sentence: cut on words
            for w in s.split(" "):
                if cur and _b(cur + " " + w) > limit:
                    parts.append(cur.strip())
                    cur = w
                else:
                    cur = (cur + " " + w).strip()
            continue
        if cur and _b(cur + " " + s) > limit:
            parts.append(cur.strip())
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur.strip():
        parts.append(cur.strip())
    return parts


def clean_title(title: str, body: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip()).strip(" .:-#*")
    if not t:
        m = re.match(r"^([A-Z][^.!?\n]{2,60})\.\s", body)  # "Pairing. Hermes pairs with..." -> "Pairing"
        first = m.group(1) if m else re.split(r"(?<=[.!?])\s|\n", body.strip(), maxsplit=1)[0]
        t = first.strip(" .")
    return t if len(t) <= 80 else t[:77].rstrip() + "..."


def clean_tags(tags) -> list[str]:
    out = []
    for t in tags or []:
        t = str(t).strip().lower().lstrip("#")
        if any(t.startswith(r) for r in RESERVED if r.endswith(":")) or t in ("official", "lib"):
            continue  # Wave's own system tags: never set by a card's author
        t = re.sub(r"[\s_]+", "-", t)
        t = re.sub(r"[^a-z0-9.-]", "", t).strip("-.")[:32]
        if t and t not in out:
            out.append(t)
    return out[:3]


def guess_tags(body: str, k: int = 2) -> list[str]:
    words = [w for w in re.findall(r"[a-z][a-z0-9-]{3,}", body.lower()) if w not in _STOPWORDS]
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return [w for w, n in sorted(freq.items(), key=lambda x: (-x[1], words.index(x[0]))) if n >= 2][:k]


def split_page(text: str) -> list[dict]:
    """Split a raw pasted page into cards by paragraph, merging tiny ones and splitting long ones."""
    lines = [ln for ln in (text or "").replace("\r\n", "\n").split("\n")]
    if lines and re.match(r"^\s*(please\s+)?(turn|make|convert|split)\b.*\bcards?\b.*:?\s*$", lines[0], re.I):
        lines = lines[1:]  # drop the instruction line
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", "\n".join(lines)) if p.strip()]
    merged: list[str] = []
    for p in paras:
        if merged and (_b(merged[-1]) < CARD_MIN_BYTES or _b(p) < CARD_MIN_BYTES) and _b(merged[-1] + " " + p) <= CARD_MAX_BYTES:
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    out = []
    for p in merged:
        out.extend({"title": "", "text": piece} for piece in _split_long(p))
    return out


def normalize(cards=None, text: str | None = None) -> list[dict]:
    """Return valid cards (title, text, tags) whatever the model sent."""
    raw = list(cards or [])
    if not raw and text:
        raw = split_page(text)
    out: list[dict] = []
    for c in raw:
        c = c if isinstance(c, dict) else {"text": str(c)}
        body = re.sub(r"[ \t]+\n", "\n", str(c.get("text") or c.get("body") or "")).strip()
        if not body:
            continue
        pieces = _split_long(body)
        base = clean_title(str(c.get("title") or ""), pieces[0])
        tags = clean_tags(c.get("tags")) or guess_tags(body)
        for i, piece in enumerate(pieces):
            title = base if len(pieces) == 1 else f"{base} ({i + 1}/{len(pieces)})"
            out.append({"title": title, "text": piece, "tags": tags})
    return out[:MAX_CARDS]
