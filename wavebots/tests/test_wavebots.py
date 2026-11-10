"""Offline tests for Wave | Bots. Chain data is a recording of real Theta mainnet responses
(checker v3:154, tally v3:152, the older checker listing v3:138), replayed so tests need no network.

Run from the repo root:  python -m pytest wavebots/tests -q
"""
from __future__ import annotations

import json
import shutil
import struct
import sys
import types
import zlib
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

import wavebots  # noqa: E402
from wavebots import _bots, _chain, _core, _profile  # noqa: E402
from wavebots._avatar import mascot_png  # noqa: E402

FIXTURE = json.loads((HERE / "chain_fixture.json").read_text())


class Replay(_chain.Rpc):
    def __init__(self, *a, tamper=None, offline=False, **k):
        super().__init__()
        self.tamper, self.offline = tamper or (lambda key, res: res), offline

    def call(self, method, params):
        if self.offline:
            raise _chain.ChainError(f"{method} failed: offline")
        key = json.dumps([method, params], sort_keys=True)
        if key not in FIXTURE:
            raise _chain.ChainError(f"{method} failed: not in fixture")
        return self.tamper(key, FIXTURE[key])


# ------------------------------------------------------------------------------ fake Hermes --
class FakeProfiles(types.ModuleType):
    def __init__(self, root: Path):
        super().__init__("hermes_cli.profiles")
        self.root = root

    def get_profile_dir(self, name):
        return self.root / "profiles" / name

    def profile_exists(self, name):
        return self.get_profile_dir(name).is_dir()

    def create_profile(self, name, no_alias=False, no_skills=False, description=None, **_):
        d = self.get_profile_dir(name)
        d.mkdir(parents=True)
        (d / "config.yaml").write_text("model:\n  default: my/model\n  provider: openrouter\n_config_version: 53\n"
                                       "mcp_servers:\n  evil:\n    url: http://x\n")
        (d / "profile.yaml").write_text(f"description: {description}\n")
        return d

    def delete_profile(self, name, yes=False):
        assert yes
        shutil.rmtree(self.get_profile_dir(name))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    fake = FakeProfiles(tmp_path)
    pkg = types.ModuleType("hermes_cli")
    pkg.profiles = fake
    monkeypatch.setitem(sys.modules, "hermes_cli", pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.profiles", fake)
    monkeypatch.setattr(_bots, "Rpc", Replay)
    return fake


def _tamper_card(ref_id: int):
    """Flip one byte of a card's content inside its mint log."""
    topic = "0x" + ref_id.to_bytes(32, "big").hex()

    def t(key, res):
        if '"eth_getLogs"' in key and topic in key and res:
            lg = dict(res[0])
            d = lg["data"]
            lg["data"] = d[:-80] + ("0" if d[-80] != "0" else "1") + d[-79:]
            return [lg]
        return res
    return t


# -------------------------------------------------------------------------------- verifying --
def test_verify_checker_passes_every_check(env):
    v = _bots.verify("checker")
    assert v["ok"] and v["status"] == "verified"
    ids = {c["id"] for c in v["checks"]}
    assert {"name", "listing_hash", "listing_name", "rules_hash", "rules_match", "design_hash", "knowledge_hash",
            "signer"} <= ids
    b = v["bot"]
    assert b["ref"] == "v3:154" and b["official"] and b["answer_mode"] == "local"
    assert [k["ref"] for k in b["knowledge"]] == ["v3:134", "v3:135"]


def test_older_listing_is_not_current(env):
    v = _bots.verify("v3:138")
    assert not v["ok"]
    bad = [c for c in v["checks"] if not c["ok"]]
    assert bad[0]["id"] == "name" and "v3:154" in bad[0]["detail"]


def test_tampered_listing_fails(env, monkeypatch):
    monkeypatch.setattr(_bots, "Rpc", lambda: Replay(tamper=_tamper_card(154)))
    v = _bots.verify("checker")
    assert not v["ok"] and v["status"] == "failed"
    assert [c for c in v["checks"] if c["id"] == "listing_hash"][0]["ok"] is False


def test_tampered_knowledge_card_fails(env, monkeypatch):
    monkeypatch.setattr(_bots, "Rpc", lambda: Replay(tamper=_tamper_card(134)))
    v = _bots.verify("checker")
    assert not v["ok"]
    k = [c for c in v["checks"] if c["id"] == "knowledge_hash"][0]
    assert not k["ok"] and "v3:134" in k["detail"]


def test_offline_is_unreadable_not_failed(env, monkeypatch):
    monkeypatch.setattr(_bots, "Rpc", lambda: Replay(offline=True))
    monkeypatch.setattr(_chain.time, "sleep", lambda s: None)
    v = _bots.verify("checker")
    assert not v["ok"] and v["status"] == "unreadable"


def test_normalize_name():
    assert _bots.normalize_name("Checker") == "checker.bots.theta"
    assert _bots.normalize_name("v3:154") == "v3:154"
    assert _bots.normalize_name("xbuildy.theta") == "xbuildy.theta"
    with pytest.raises(_bots.BotError):
        _bots.normalize_name("../etc/passwd")


# ---------------------------------------------------------------------------- adding to Hermes --
def test_add_creates_locked_down_hermes_bot(env):
    r = _profile.add("checker")
    assert r["ok"] and r["created"] and r["profile"] == "wave-checker"
    d = env.get_profile_dir("wave-checker")
    import yaml
    cfg = yaml.safe_load((d / "config.yaml").read_text())
    assert cfg["model"]["default"] == "my/model"                 # runs on the user's AI
    assert cfg["mcp_servers"] == {}                               # MCP off
    for ts in ("terminal", "file", "browser", "code_execution", "cronjob", "delegation", "web", "memory"):
        assert ts in cfg["agent"]["disabled_toolsets"]
    soul = (d / "SOUL.md").read_text()
    assert "Checker" in soul and "v3:154" in soul and "(card v3:134)" in soul and "(card v3:135)" in soul
    meta = yaml.safe_load((d / "profile.yaml").read_text())
    assert meta["display_name"] == "Checker" and meta["ui_meta"]["hermes-bots"]["title"] == "Checker"
    png = (d / "assets" / "avatar.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (256, 256)
    marker = json.loads((d / "wavebot.json").read_text())
    assert marker["ref"] == "v3:154" and marker["knowledge_refs"] == ["v3:134", "v3:135"]
    # adding again reuses the same bot
    assert _profile.add("checker.bots.theta")["created"] is False
    assert len(_profile.added()) == 1


def test_add_wont_touch_a_profile_it_didnt_make(env):
    env.create_profile("wave-checker")
    with pytest.raises(_profile.AddError, match="didn't make"):
        _profile.add("checker")


def test_paid_or_private_bots_wait_for_connect(env, monkeypatch):
    real = _bots.verify

    def paid(q, rpc=None, **k):
        v = real(q, rpc, **k)
        v["bot"]["answer_mode"] = "wave"
        return v
    monkeypatch.setattr(_profile, "verify", paid)
    pv = _profile.preview("checker")
    assert not pv["can_add"] and "Connect" in pv["reason"]
    with pytest.raises(_profile.AddError):
        _profile.add("checker")


def test_failed_add_leaves_no_half_bot(env, monkeypatch):
    monkeypatch.setattr(_profile, "_write_bot", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        _profile.add("checker")
    assert not env.profile_exists("wave-checker") and _profile.added() == []


# ------------------------------------------------------------------------------- re-checking --
def test_check_verified_then_edited(env):
    _profile.add("checker")
    assert _profile.check("checker")["status"] == "verified"
    d = env.get_profile_dir("wave-checker")
    (d / "SOUL.md").write_text((d / "SOUL.md").read_text() + "\nmy own note\n")
    r = _profile.check("checker")
    assert r["status"] == "verified" and r["edited"] and "edited" in r["note"]


def test_check_update_available(env, monkeypatch):
    _profile.add("checker")
    real = _bots.verify

    def moved(q, rpc=None, **k):
        v = real(q, rpc, **k)
        v["bot"]["ref"] = "v3:999"
        return v
    monkeypatch.setattr(_profile, "verify", moved)
    r = _profile.check("checker")
    assert r["status"] == "update_available" and "v3:999" in r["note"]


def test_failed_check_pauses_then_recovers(env, monkeypatch):
    _profile.add("checker")
    d = env.get_profile_dir("wave-checker")
    monkeypatch.setattr(_bots, "Rpc", lambda: Replay(tamper=_tamper_card(154)))
    r = _profile.check("checker")
    assert r["status"] == "paused"
    assert "paused" in (d / "SOUL.md").read_text() and "v3:134" not in (d / "SOUL.md").read_text()
    monkeypatch.setattr(_bots, "Rpc", Replay)
    r = _profile.check("checker")
    assert r["status"] == "verified" and "(card v3:134)" in (d / "SOUL.md").read_text()


def test_offline_check_keeps_last_status(env, monkeypatch):
    _profile.add("checker")
    monkeypatch.setattr(_bots, "Rpc", lambda: Replay(offline=True))
    monkeypatch.setattr(_chain.time, "sleep", lambda s: None)
    r = _profile.check("checker")
    assert r["status"] == "verified" and "Couldn't reach Theta" in r["note"]
    assert "(card v3:134)" in (env.get_profile_dir("wave-checker") / "SOUL.md").read_text()


# ------------------------------------------------------------------------------ removing etc --
def test_remove_and_hermes_side_delete(env):
    _profile.add("checker")
    _profile.add("tally")
    assert _profile.remove("checker")["ok"] and not env.profile_exists("wave-checker")
    env.delete_profile("wave-tally", yes=True)  # deleted in Hermes itself
    assert _profile.added() == []
    with pytest.raises(_profile.AddError):
        _profile.remove("tally")


def test_slash_remove_needs_yes(env):
    _profile.add("checker")
    out = wavebots._slash("remove checker")
    assert "yes" in out and env.profile_exists("wave-checker")
    assert "Removed" in wavebots._slash("remove checker yes") and not env.profile_exists("wave-checker")


def test_slash_add_and_info(env):
    assert "Added Checker" in wavebots._slash("add checker")
    assert "Verified on Theta" in wavebots._slash("info tally")


# ------------------------------------------------------------------------------- guard rails --
def test_approval_hook_covers_changes_only():
    for act in ("add", "update", "remove"):
        h = wavebots._require_approval("wave_bots", {"action": act, "bot": "checker"})
        assert h and h["action"] == "approve" and "checker" in h["rule_key"]
    for act in ("find", "info", "check", "list_added"):
        assert wavebots._require_approval("wave_bots", {"action": act}) is None
    assert wavebots._require_approval("other_tool", {"action": "add"}) is None


def test_tool_refuses_changes_in_cron(env):
    agent = types.SimpleNamespace(platform="cron")
    out = json.loads(wavebots._tool({"action": "add", "bot": "checker"}, parent_agent=agent))
    assert "approve" in out["error"] and not env.profile_exists("wave-checker")


def test_tool_find_prefers_matches(env, monkeypatch):
    monkeypatch.setattr(_core, "catalog", lambda: [
        {"name": "Checker", "slug": "checker", "tns": "checker.bots.theta", "pitch": "Checks a draft", "verified": True},
        {"name": "Tally", "slug": "tally", "tns": "tally.bots.theta", "pitch": "Budgets and numbers", "verified": True}])
    out = json.loads(wavebots._tool({"action": "find", "query": "numbers"}))
    assert [b["slug"] for b in out["bots"]] == ["tally"]


def test_register_wires_everything():
    seen = {}

    class Ctx:
        def register_tool(self, **k): seen["tool"] = k["name"]
        def register_hook(self, name, fn): seen["hook"] = name
        def register_command(self, name, fn, **k): seen["cmd"] = name
        def register_cli_command(self, **k): seen["cli"] = k["name"]
    wavebots.register(Ctx())
    assert seen == {"tool": "wave_bots", "hook": "pre_tool_call", "cmd": "bots", "cli": "wavebots"}


def test_mascot_png_draws_the_design():
    design = {"kind": "pixel20", "palette": ["#000000", "#ff0000"], "pixels": "", "profileColor": "#00ff00"}
    import base64
    design["pixels"] = base64.b64encode(bytes([2] * 400)).decode()
    png = mascot_png(design, size=64)
    # decode the first row's middle pixel: should be the palette red, not the tint
    idat = png[png.index(b"IDAT") + 4:png.index(b"IEND") - 8]
    raw = zlib.decompress(idat)
    stride = 1 + 64 * 4
    mid = raw[32 * stride + 1 + 32 * 4: 32 * stride + 1 + 32 * 4 + 4]
    assert mid == b"\xff\x00\x00\xff"
    with pytest.raises(ValueError):
        mascot_png({"kind": "svg"})


# ----------------------------------------------------------------------------- dashboard API --
def test_dashboard_api_add_check_remove(env):
    fastapi = pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    import importlib.util
    from fastapi.testclient import TestClient
    spec = importlib.util.spec_from_file_location("wb_api_test", HERE.parent / "dashboard" / "plugin_api.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    api._m("_bots").Rpc = Replay  # the API loads its own copy of the package
    app = fastapi.FastAPI()
    app.include_router(api.router, prefix="/x")
    c = TestClient(app)
    pv = c.post("/x/preview", json={"bot": "checker"}).json()
    assert pv["can_add"] and pv["profile"] == "wave-checker" and "terminal" in pv["disabled_toolsets"]
    r = c.post("/x/add", json={"bot": "checker"})
    assert r.status_code == 200 and r.json()["created"]
    assert c.get("/x/added").json()["added"][0]["profile"] == "wave-checker"
    assert c.post("/x/check", json={"bot": "wave-checker"}).json()["status"] == "verified"
    assert c.post("/x/add", json={"bot": "v3:138"}).status_code == 400
    assert c.post("/x/remove", json={"bot": "wave-checker"}).json()["ok"]
    assert c.post("/x/remove", json={"bot": "wave-checker"}).status_code == 400
    assert c.post("/x/add", json={"bot": ""}).status_code == 422
    b = c.get("/x/banner").json()["data"]
    assert b.startswith("data:image/jpeg;base64,")


# ----------------------------------------------------------------------------- Connect to Wave OS --
from wavebots import _connect, _pv1  # noqa: E402

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1In0.c2ln"


class FakeWaveOS:
    """Stands in for app.oswave.io hermesConnect + mcpRouter."""
    def __init__(self):
        self.drops, self.calls, self.revoked = {}, [], False

    def approve(self, code, pk, payload=None):
        body = payload or {"schema": "wave.hermes-connect/1", "token": JWT, "expiresAt": "2099-01-01T00:00:00.000Z",
                           "label": "Hermes (Wave | Bots) · 2026-11-10", "scope": "safe",
                           "caps": {"per_call": 0, "per_day": 0}, "user": {"display_name": "Eddie"}}
        self.drops[code] = _pv1.encrypt(json.dumps(body), pk)

    def __call__(self, path, body, headers=None, timeout=30.0):
        self.calls.append((path, body, headers or {}))
        if path == "/functions/hermesConnect":
            box = self.drops.pop(body["code"], None)
            return (200, {"ok": True, "box": box}) if box else (404, {"ok": False, "error": "not found or expired"})
        if path == "/functions/mcpRouter":
            if self.revoked or (headers or {}).get("authorization") != "Bearer " + JWT:
                inner = {"ok": False, "code": "sign_in_required", "message": "revoked", "price": None}
            else:
                a = body["params"]["arguments"]
                inner = {"ok": True, "answer": f"Checked: {a['question']}", "cited_cards": [{"ref": "v3:134"}],
                         "bot": "checker.bots.theta", "listing_ref": "v3:154", "untrusted": True,
                         "price": {"charged_tfuel": 0}, "receipt": {"id": "r1", "hash": "ab" * 32}, "secret_field": "x"}
            return 200, {"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": json.dumps(inner)}]}}
        raise AssertionError(path)


@pytest.fixture
def wave(env, monkeypatch):
    fake = FakeWaveOS()
    monkeypatch.setattr(_connect, "_post", fake)
    monkeypatch.setattr(_connect, "_keyring", lambda: None)
    return fake


def test_connect_link_and_finish(wave):
    p = _connect.start()
    assert p["url"].startswith("https://app.oswave.io/hermes/connect?code=")
    assert len(p["code"]) >= 22 and "pk=0x04" in p["url"] and JWT not in p["url"]
    assert _connect.take(p) is None                       # not approved yet
    wave.approve(p["code"], _pv1.public_key_hex(p["key"]))
    meta = _connect.take(p)
    assert meta["label"].startswith("Hermes (Wave | Bots)") and meta["store"] == "file"
    f = _connect._file()
    assert (f.stat().st_mode & 0o777) == 0o600
    st = _connect.status()
    assert st["connected"] and "token" not in st
    assert _connect.take(p) is None                       # one read only


def test_connect_rejects_wrong_key_and_bad_payload(wave):
    p, other = _connect.start(), _connect.start()
    wave.approve(p["code"], _pv1.public_key_hex(other["key"]))       # sealed to someone else
    with pytest.raises(_connect.ConnectError):
        _connect.take(p)
    q = _connect.start()
    wave.approve(q["code"], _pv1.public_key_hex(q["key"]),
                 {"schema": "wave.hermes-connect/1", "token": JWT, "scope": "full", "expiresAt": "2099-01-01T00:00:00Z"})
    with pytest.raises(_connect.ConnectError):                        # never accept a full-scope token
        _connect.take(q)
    assert not _connect.status()["connected"]


def test_wait_polls_then_connects(wave):
    p = _connect.start()
    n = {"i": 0}

    def sleep(_s):
        n["i"] += 1
        if n["i"] == 2:
            wave.approve(p["code"], _pv1.public_key_hex(p["key"]))
    assert _connect.wait(p, interval_s=0, sleep=sleep)["label"]
    polls = [c for c in wave.calls if c[0] == "/functions/hermesConnect"]
    assert len(polls) == 3


def test_ask_needs_connect_then_works_and_handles_revoke(wave):
    with pytest.raises(_connect.ConnectError, match="Connect Wave OS first"):
        _connect.ask("checker", "is 2+2=4?")
    p = _connect.start()
    wave.approve(p["code"], _pv1.public_key_hex(p["key"]))
    _connect.take(p)
    r = _connect.ask("checker", "is 2+2=4?")
    assert r["ok"] and r["answer"].startswith("Checked") and r["untrusted"] and "secret_field" not in r
    sent = [c for c in wave.calls if c[0] == "/functions/mcpRouter"][-1]
    assert sent[1]["params"] == {"name": "bots_call", "arguments": {"bot": "checker", "question": "is 2+2=4?", "max_price_tfuel": 0.0}}
    assert sent[2]["authorization"] == "Bearer " + JWT
    wave.revoked = True
    with pytest.raises(_connect.ConnectError, match="revoked"):
        _connect.ask("checker", "again?")
    assert _connect.status()["revoked"] and not _connect.status()["connected"]
    assert _connect.disconnect()["ok"] and not _connect._file().exists()


def test_ask_wave_tool_asks_for_approval_and_slash(wave):
    hook = wavebots._require_approval
    a = hook("wave_bots", {"action": "ask_wave", "bot": "checker", "question": "q"})
    assert a and a["action"] == "approve" and "free bots cost nothing" in a["message"]
    a = hook("wave_bots", {"action": "ask_wave", "bot": "tally", "max_price_tfuel": 0.5})
    assert "0.5 TFUEL" in a["message"]
    assert hook("wave_bots", {"action": "connection"}) is None
    cron = types.SimpleNamespace(platform="cron")
    assert "approve" in json.loads(wavebots._tool({"action": "ask_wave", "bot": "checker", "question": "q"}, parent_agent=cron))["error"]
    assert "Connect Wave OS first" in json.loads(wavebots._tool({"action": "ask_wave", "bot": "checker", "question": "q"}))["error"]
    p = _connect.start()
    wave.approve(p["code"], _pv1.public_key_hex(p["key"]))
    _connect.take(p)
    out = wavebots._slash("ask checker is this right?")
    assert "Checked: is this right?" in out and "free" in out and "v3:134" in out
