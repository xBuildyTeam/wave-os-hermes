"""Local BrainVault store: one SQLite file per Hermes profile ($HERMES_HOME/brainvault/brainvault.db).

memories  what Hermes learned on this install (instant recall, the queue for Wave)
cards     cards read from the user's Wave vault on Theta (public text, or private text opened with the agent key)
meta      small key/value state (last synced block, etc.)
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  fp TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
  target TEXT NOT NULL DEFAULT 'memory', trust TEXT NOT NULL DEFAULT 'agent', private INTEGER NOT NULL DEFAULT 1,
  source TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL, updated REAL NOT NULL,
  state TEXT NOT NULL DEFAULT 'local', exported_at REAL, card_ref TEXT
);
CREATE TABLE IF NOT EXISTS cards (
  ref TEXT PRIMARY KEY, id INTEGER NOT NULL, creator TEXT NOT NULL, is_private INTEGER NOT NULL,
  recipient_id TEXT, tags TEXT NOT NULL DEFAULT '[]', content_hash TEXT NOT NULL, text TEXT,
  opened INTEGER NOT NULL DEFAULT 0, sha_ok INTEGER NOT NULL DEFAULT 0, minted_block INTEGER,
  supersedes TEXT, superseded_by TEXT, fetched REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE INDEX IF NOT EXISTS memories_state ON memories(state);
"""
_WORD = re.compile(r"[a-z0-9][a-z0-9'_-]{1,}")
_STOP = frozenset("the a an and or but of to in on for with is are was were be been it this that these those i you he she we they "
                  "my your our their me him her us them at by from as about into over after before not no do does did have has had "
                  "can could should would will just so if then than there here what which who whom how why when where".split())


def fingerprint(body: str) -> str:
    norm = re.sub(r"\s+", " ", body.strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP]


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.commit()
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- meta --
    def get_meta(self, k: str, default: str | None = None) -> str | None:
        with self._lock:
            r = self._db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r["v"] if r else default

    def set_meta(self, k: str, v: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
            self._db.commit()

    # -- memories --
    def add_memory(self, *, title: str, body: str, tags: list[str], target: str = "memory", trust: str = "agent",
                   private: bool = True, source: dict | None = None) -> tuple[str, bool]:
        fp = fingerprint(body)
        now = time.time()
        with self._lock:
            row = self._db.execute("SELECT state FROM memories WHERE fp=?", (fp,)).fetchone()
            if row and row["state"] != "removed":
                return fp, False
            self._db.execute(
                "INSERT INTO memories(fp,title,body,tags,target,trust,private,source,created,updated,state) "
                "VALUES(?,?,?,?,?,?,?,?,?,?, 'local') ON CONFLICT(fp) DO UPDATE SET title=excluded.title, body=excluded.body, "
                "tags=excluded.tags, target=excluded.target, trust=excluded.trust, private=excluded.private, "
                "source=excluded.source, updated=excluded.updated, state='local', exported_at=NULL",
                (fp, title, body, json.dumps(tags), target, trust, int(private), json.dumps(source or {}), now, now))
            self._db.commit()
        return fp, True

    def remove_memory(self, *, fp: str | None = None, body: str | None = None) -> int:
        if not fp and body is not None:
            fp = fingerprint(body)
        if not fp:
            return 0
        with self._lock:
            cur = self._db.execute("UPDATE memories SET state='removed', updated=? WHERE fp=? AND state!='removed'",
                                   (time.time(), fp))
            self._db.commit()
            return cur.rowcount

    def memory(self, fp: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM memories WHERE fp=?", (fp,)).fetchone()
        return self._mem(r) if r else None

    def memories(self, *, states: tuple[str, ...] = ("local", "exported", "minted"), limit: int = 500) -> list[dict]:
        q = f"SELECT * FROM memories WHERE state IN ({','.join('?' * len(states))}) ORDER BY created DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(q, (*states, limit)).fetchall()
        return [self._mem(r) for r in rows]

    def mark_exported(self, fps: list[str]) -> None:
        now = time.time()
        with self._lock:
            self._db.executemany("UPDATE memories SET state='exported', exported_at=? WHERE fp=? AND state='local'",
                                 [(now, f) for f in fps])
            self._db.commit()

    def mark_minted(self, fp: str, ref: str) -> None:
        with self._lock:
            self._db.execute("UPDATE memories SET state='minted', card_ref=? WHERE fp=? AND state!='removed'", (ref, fp))
            self._db.commit()

    @staticmethod
    def _mem(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["tags"] = json.loads(d["tags"])
        d["source"] = json.loads(d["source"])
        d["private"] = bool(d["private"])
        return d

    # -- cards --
    def upsert_card(self, c: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO cards(ref,id,creator,is_private,recipient_id,tags,content_hash,text,opened,sha_ok,minted_block,"
                "supersedes,superseded_by,fetched) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ref) DO UPDATE SET "
                "text=excluded.text, opened=excluded.opened, sha_ok=excluded.sha_ok, superseded_by=excluded.superseded_by, "
                "tags=excluded.tags, fetched=excluded.fetched",
                (c["ref"], c["id"], c["creator"], int(c["isPrivate"]), c.get("recipientId"), json.dumps(c.get("tags", [])),
                 c["contentHash"], c.get("plain"), int(bool(c.get("opened"))), int(bool(c.get("sha_ok"))), c.get("block"),
                 c.get("supersedes_ref"), c.get("superseded_by"), time.time()))
            self._db.commit()

    def has_card(self, ref: str, content_hash: str) -> bool:
        with self._lock:
            r = self._db.execute("SELECT content_hash FROM cards WHERE ref=?", (ref,)).fetchone()
        return bool(r and r["content_hash"] == content_hash)

    def set_superseded(self, ref: str, by: str | None) -> None:
        with self._lock:
            self._db.execute("UPDATE cards SET superseded_by=? WHERE ref=?", (by, ref))
            self._db.commit()

    def cards(self, *, readable_only: bool = True, limit: int = 2000) -> list[dict]:
        q = "SELECT * FROM cards" + (" WHERE text IS NOT NULL AND sha_ok=1" if readable_only else "") + " ORDER BY id DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(q, (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"])
            out.append(d)
        return out

    def counts(self) -> dict:
        with self._lock:
            m = {r["state"]: r["n"] for r in self._db.execute("SELECT state, COUNT(*) n FROM memories GROUP BY state")}
            c = self._db.execute("SELECT COUNT(*) n, SUM(opened) o, SUM(is_private) p, SUM(sha_ok=0) bad FROM cards").fetchone()
        return {"memories": m, "cards": c["n"] or 0, "cards_private": c["p"] or 0, "cards_opened": c["o"] or 0,
                "cards_hash_failed": c["bad"] or 0}

    # -- recall --
    def search(self, query: str, k: int = 5) -> list[dict]:
        """Small BM25 over local memories + readable vault cards. Fast, local, no network."""
        q = list(dict.fromkeys(_tokens(query)))
        if not q:
            return []
        docs: list[dict] = []
        for m in self.memories(states=("local", "exported", "minted")):
            docs.append({"kind": "local", "id": m["fp"], "title": m["title"], "text": m["body"], "tags": m["tags"],
                         "trust": m["trust"], "ref": m.get("card_ref"), "private": m["private"]})
        minted_refs = {d["ref"] for d in docs if d["ref"]}
        for c in self.cards():
            if c["superseded_by"] or c["ref"] in minted_refs:
                continue
            docs.append({"kind": "vault", "id": c["ref"], "title": "", "text": c["text"], "tags": c["tags"],
                         "trust": "vault", "ref": c["ref"], "private": bool(c["is_private"]), "sha": c["content_hash"]})
        if not docs:
            return []
        toks = [_tokens(d["title"] + " " + d["text"] + " " + " ".join(d["tags"])) for d in docs]
        n = len(docs)
        avg = sum(len(t) for t in toks) / n or 1.0
        df = {w: sum(1 for t in toks if w in t) for w in q}
        scored = []
        for d, t in zip(docs, toks):
            if not t:
                continue
            s = 0.0
            for w in q:
                f = t.count(w)
                if not f:
                    continue
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(t) / avg))
            if s > 0:
                scored.append((s, d))
        scored.sort(key=lambda x: -x[0])
        return [dict(d, score=round(s, 3)) for s, d in scored[:k]]
