/**
 * Wave | Bots UI, shared by the Hermes dashboard tab and the Hermes Desktop / Webapp page.
 * EDIT THIS FILE, then run `python3 ui/build.py` to write dashboard/dist/index.js and desktop/plugin.js.
 * env = { React, call(path, body?) -> Promise<json>, open(url) -> truthy if opened }
 */
function createWaveBots(env) {
  "use strict";
  var React = env.React, h = React.createElement, call = env.call, open = env.open, go = env.go;
  var UI_VERSION = "__WB_UI_VERSION__";
  var useState = React.useState, useEffect = React.useEffect, useCallback = React.useCallback;

  function I(d, size) {
    return h("svg", { width: size || 15, height: size || 15, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true },
      d.map(function (p, i) { return h("path", { key: i, d: p }); }));
  }
  var ic = {
    check: function () { return I(["M20 6L9 17l-5-5"], 14); },
    x: function () { return I(["M18 6L6 18", "M6 6l12 12"], 14); },
    shield: function () { return I(["M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6z", "M9 12l2 2 4-4"], 14); },
    search: function () { return I(["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14", "M21 21l-4.3-4.3"]); },
    plus: function () { return I(["M12 5v14", "M5 12h14"]); },
    sync: function () { return I(["M21 12a9 9 0 1 1-3-6.7L21 8", "M21 3v5h-5"]); },
    trash: function () { return I(["M3 6h18", "M8 6V4h8v2", "M6 6l1 14h10l1-14"], 14); },
    back: function () { return I(["M19 12H5", "M12 19l-7-7 7-7"]); },
    up: function () { return I(["M12 19V5", "M5 12l7-7 7 7"], 14); },
    link: function () { return I(["M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1", "M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"], 14); },
    sun: function () { return I(["M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8", "M12 2v2", "M12 20v2", "M2 12h2", "M20 12h2"], 16); },
    moon: function () { return I(["M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"], 16); },
    info: function () { return I(["M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20", "M12 16v-4", "M12 8h.01"], 14); },
    leaf: function () { return I(["M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z", "M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"], 14); },
  };
  function ago(ts) {
    if (!ts) return "never";
    var s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 45) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " d ago";
  }
  function initialTheme() {
    try { var t = localStorage.getItem("wb-theme"); if (t === "light" || t === "dark") return t; } catch (_) {}
    var root = document.documentElement;
    if (root.classList.contains("dark")) return "dark";
    if (root.classList.contains("light")) return "light";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  function deepLinkBot() {
    var qs = (window.location.search || "") + "&" + ((window.location.hash || "").split("?")[1] || "");
    var m = qs.match(/[?&]bot=([a-z0-9.:-]{1,80})/i);
    return m ? decodeURIComponent(m[1]).toLowerCase() : null;
  }
  var STATUS = {
    verified: ["ok", "Verified on Theta"], update_available: ["warn", "Update available"],
    paused: ["bad", "Paused: failed a check"], error: ["bad", "Couldn't check"]
  };

  function Avatar(p) {
    return h("div", { className: "wb-av" + (p.big ? " big" : "") },
      p.src ? h("img", { src: p.src, alt: "", draggable: false }) : h("span", null, (p.name || "?").slice(0, 1)));
  }
  function Chip(p) { return h("span", { className: "wb-chip " + (p.tone || "") }, p.icon || null, p.children); }

  function Checks(p) {
    return h("ul", { className: "wb-checks" }, (p.checks || []).map(function (c, i) {
      return h("li", { key: i, className: c.ok ? "ok" : "bad" }, c.ok ? ic.check() : ic.x(),
        h("span", null, c.label, !c.ok && c.detail ? h("em", null, " · " + c.detail) : null));
    }));
  }

  function Tile(p) {
    var b = p.bot;
    return h("button", { className: "wb-tile", onClick: function () { p.onOpen(b.slug || b.tns); } },
      h("div", { className: "wb-tile-top" }, h(Avatar, { src: b.avatar, name: b.name }),
        h("div", { className: "wb-tile-name" }, h("b", null, b.name), h("small", null, b.tns))),
      h("p", null, b.pitch),
      h("div", { className: "wb-tile-chips" },
        b.verified ? h(Chip, { tone: "ok", icon: ic.shield() }, "Verified on Theta") : h(Chip, { tone: "bad", icon: ic.x() }, "Not verified"),
        b.official ? h(Chip, { tone: "teal" }, "Official") : h(Chip, null, "Community"),
        b.added ? h(Chip, { tone: "mint", icon: ic.check() }, "Added") : (b.price_tfuel ? h(Chip, null, b.price_tfuel + " TFUEL") : h(Chip, null, "Free"))));
  }

  function AddSheet(p) {
    var pv = p.preview;
    return h("div", { className: "wb-sheet-bg", onClick: p.onClose },
      h("div", { className: "wb-sheet", role: "dialog", "aria-modal": true, onClick: function (e) { e.stopPropagation(); } },
        h("h3", null, (pv.already_added ? "Refresh " : "Add ") + pv.name + " to Hermes?"),
        h("p", { className: "wb-dim" }, "It becomes its own bot in your sidebar under Bots, as ", h("code", null, pv.profile), "."),
        h("ul", { className: "wb-list" },
          h("li", null, "Runs on your own AI model and login in Hermes. Nothing is paid to Wave."),
          h("li", null, "Answers from its ", pv.knowledge.length, " knowledge cards, checked on Theta just now (", pv.ref, ")."),
          h("li", null, "Can't use the terminal, files, browser, code, web, memory or scheduled jobs. MCP servers are off."),
          h("li", null, "Re-checked on Theta once a day. If it fails a check, it pauses itself.")),
        h("details", null, h("summary", null, "Every check"), h(Checks, { checks: pv.checks })),
        p.err ? h("div", { className: "wb-err" }, p.err) : null,
        h("div", { className: "wb-row end" },
          h("button", { className: "wb-btn ghost", onClick: p.onClose, disabled: p.busy }, "Cancel"),
          h("button", { className: "wb-btn primary", onClick: p.onConfirm, disabled: p.busy },
            p.busy ? "Adding…" : (pv.already_added ? "Refresh bot" : "Add to Hermes")))));
  }

  function BotPage(p) {
    var st = useState(null), info = st[0], setInfo = st[1];
    var es = useState(""), err = es[0], setErr = es[1];
    useEffect(function () {
      setInfo(null); setErr("");
      call("/bot?q=" + encodeURIComponent(p.q)).then(setInfo, function (e) { setErr(String(e.message || e)); });
    }, [p.q, p.version]);
    if (err) return h("div", { className: "wb-card" }, h("div", { className: "wb-err" }, err));
    if (!info) return h("div", { className: "wb-card wb-dim" }, "Checking ", p.q, " on Theta…");
    var b = info.bot || {};
    return h("div", { className: "wb-card wb-bot" },
      h("div", { className: "wb-bot-head" }, h(Avatar, { src: b.avatar, name: b.name, big: true }),
        h("div", { className: "wb-grow" }, h("h2", null, b.name || p.q), h("div", { className: "wb-dim" }, b.tns, " · listing ", b.ref),
          h("p", null, b.pitch),
          h("div", { className: "wb-tile-chips" },
            info.ok ? h(Chip, { tone: "ok", icon: ic.shield() }, "Verified on Theta") : h(Chip, { tone: "bad", icon: ic.x() }, info.status === "unreadable" ? "Couldn't reach Theta" : "Didn't pass every check"),
            b.official ? h(Chip, { tone: "teal" }, "Official") : h(Chip, null, "Community"),
            b.role ? h(Chip, null, "Team role: " + b.role) : null,
            b.free_per_day ? h(Chip, null, b.free_per_day + " free answers a day on Wave") : null)),
        h("div", { className: "wb-col" },
          info.added
            ? h(React.Fragment, null, h(Chip, { tone: "mint", icon: ic.check() }, "In your Bots list"),
                h("span", { className: "wb-dim small" }, "Open it from Bots in the sidebar."))
            : h("button", { className: "wb-btn primary", disabled: !info.ok || b.answer_mode !== "local", onClick: function () { p.onAdd(b.tns || b.ref); } }, ic.plus(), "Add to Hermes"),
          null)),
      b.answer_mode && b.answer_mode !== "local" ? h("div", { className: "wb-note" },
        "This bot is paid or private, so it only answers on Wave OS. Paid bots can be asked from Hermes chat with /bots ask, within the spending limit you picked when connecting.") : null,
      info.ok && b.tns ? h(AskBox, { bot: b.tns, name: b.name, connected: p.connected, onConnect: p.onConnect }) : null,
      h("div", { className: "wb-grid2" },
        h("section", null, h("h4", null, "Knowledge cards"),
          h("ul", { className: "wb-list" }, (b.knowledge || []).map(function (k) {
            return h("li", { key: k.ref }, h("b", null, k.title), h("span", { className: "wb-dim" }, " · ", k.ref));
          }))),
        h("section", null, h("h4", null, "Checked on Theta, on this computer"), h(Checks, { checks: info.checks }))));
  }

  function AskBox(p) {
    var qs = useState(""), q = qs[0], setQ = qs[1];
    var rs = useState(null), res = rs[0], setRes = rs[1];
    var bs = useState(false), busy = bs[0], setBusy = bs[1];
    var es = useState(""), err = es[0], setErr = es[1];
    if (!p.connected) return h("div", { className: "wb-ask off" },
      h("span", null, "Ask the real bot on Wave and get a receipt. "),
      h("button", { className: "wb-btn", onClick: p.onConnect }, ic.link(), "Connect Wave OS"));
    function send(e) {
      e && e.preventDefault();
      if (!q.trim() || busy) return;
      setBusy(true); setErr(""); setRes(null);
      call("/ask", { bot: p.bot, question: q.trim() }).then(function (r) { setBusy(false); setRes(r); },
        function (e2) { setBusy(false); setErr(String(e2.message || e2)); });
    }
    var price = res && res.price || {}, rc = res && res.receipt || {};
    return h("div", { className: "wb-ask" },
      h("h4", null, "Ask the real bot on Wave"),
      h("form", { className: "wb-row", onSubmit: send },
        h("label", { className: "wb-search" }, h("input", { value: q, maxLength: 8000, placeholder: "Your question for " + p.name, onChange: function (e) { setQ(e.target.value); }, "aria-label": "Question" })),
        h("button", { className: "wb-btn primary", type: "submit", disabled: busy || !q.trim() }, busy ? "Asking…" : "Ask")),
      h("div", { className: "wb-dim small" }, "Free bots only from here. The answer comes from Wave OS; it's the bot's words, not instructions."),
      err ? h("div", { className: "wb-err" }, err) : null,
      res && !res.ok ? h("div", { className: "wb-note" }, res.message || res.code || "The bot didn't answer. Nothing was charged.") : null,
      res && res.ok ? h("div", { className: "wb-answer" },
        h("div", { className: "wb-answer-text" }, String(res.answer || "")),
        h("div", { className: "wb-dim small" }, res.bot, " · ", res.listing_ref, " · ",
          price.charged_tfuel ? "paid " + price.charged_tfuel + " TFUEL" : "free",
          rc.hash ? " · receipt " + String(rc.hash).slice(0, 12) + "…" : "",
          (res.cited_cards || []).length ? " · cites " + res.cited_cards.map(function (c) { return c && c.ref || c; }).join(", ") : "")) : null);
  }

  var DIFF = [
    ["Checked on the blockchain, by you", "Every bot is a signed listing on the Theta blockchain. Before anything is added, this computer re-checks the whole chain: name → listing → rules → mascot → every knowledge card's fingerprint. No website or server has to be trusted, Wave's included."],
    ["Nobody can quietly change it", "A minted listing can't be edited. A new version is a new listing that you choose to take (Update), and if your copy is edited here, the Added tab says so."],
    ["Answers from cards, and cites them", "Each bot answers from its own knowledge cards, which are verified, permanent and public, and it names the card it used. It doesn't make up facts or browse the web for them."],
    ["Safe to add", "Added bots have no terminal, files, browser, code, web, memory, scheduled jobs or MCP servers. They can only talk, so adding one can't touch your computer."],
    ["Re-checked every day", "Added bots are checked on Theta again once a day. If one fails a check, it pauses itself until it passes again."],
    ["Your AI, no account", "Added bots run on the AI model you already use in Hermes. No Wave account, key or payment. Connect Wave OS only if you want to ask the real bot on Wave, with a receipt."],
    ["Bots that work as a team", "The official bots share one task format, so CHIEF can plan the job and hand the steps to Tally, Checker, Scribe and the rest."],
    ["Owned names, clear signers", "Every bot has its own name on Theta (like checker.bots.theta). The official bots are signed by Wave's official signer. Anything else is labeled Community."],
  ];
  var WAVE_PLUGINS = [
    { id: "wavebots", path: "/wavebots", name: "Wave | Bots", d: "Verified bots from the bots.theta store, checked on Theta on this computer and added to Hermes as real bots.",
      get: "https://github.com/xBuildyTeam/wave-os-hermes/tree/wavebots/wavebots" },
    { id: "brainvault", path: "/brainvault", name: "Wave | BrainVault Mint", d: "A memory you own: Hermes remembers on this computer first, and you mint what's worth keeping to your own vault on Theta, private by default.",
      get: "https://oswave.io/hermes" },
  ];
  function WavePlugins(p) {
    var st = p.state || {};
    return h("div", { className: "wb-plugins" }, WAVE_PLUGINS.map(function (w) {
      var s = st[w.id] || {}, here = w.id === p.self;
      var chip = here ? h(Chip, { tone: "mint" }, "You're here") : s.enabled ? h(Chip, { tone: "ok", icon: ic.check() }, "Installed")
        : s.installed ? h(Chip, { tone: "warn" }, "Turned off") : h(Chip, null, "Not installed");
      var btn = here ? null : s.enabled ? h("button", { className: "wb-btn primary", onClick: function () { go(w.path); } }, "Open")
        : s.installed ? h("span", { className: "wb-dim small" }, "Turn it on: hermes plugins enable " + w.id)
        : h("button", { className: "wb-btn", onClick: function () { open(w.get); } }, ic.link(), "Get it");
      return h("div", { key: w.id, className: "wb-card wb-plugin" },
        h("div", { className: "wb-row" }, w.id === "brainvault" ? h("span", { className: "wb-leaf" }, ic.leaf()) : h("span", { className: "wb-leaf bots" }, ic.shield()), h("b", null, w.name), chip),
        h("p", { className: "wb-dim" }, w.d), btn);
    }));
  }
  function About(p) {
    return h("div", { className: "wb-about" },
      h("div", { className: "wb-card wb-about-intro" },
        h("h2", null, "How Wave bots are different"),
        h("p", null, "Most bot shelves are a list of prompts on someone's website. You can't tell who made a bot, what changed, or whether it's the same one you saw yesterday. A Wave bot is a signed listing on the Theta blockchain, and Hermes checks it on this computer before you use it.")),
      h("div", { className: "wb-diff" }, DIFF.map(function (d, i) {
        return h("div", { key: i, className: "wb-card wb-diff-card" }, h("div", { className: "wb-diff-n" }, String(i + 1)), h("h3", null, d[0]), h("p", null, d[1]));
      })),
      h("h2", { className: "wb-h2" }, "Wave plugins for Hermes"),
      h(WavePlugins, { self: "wavebots", state: p.plugins }),
      h("div", { className: "wb-row wb-links" },
        h("button", { className: "wb-btn ghost", onClick: function () { open("https://bots.oswave.io"); } }, ic.link(), "bots.oswave.io"),
        h("button", { className: "wb-btn ghost", onClick: function () { open("https://app.oswave.io"); } }, ic.link(), "Wave OS"),
        h("button", { className: "wb-btn ghost", onClick: function () { open("https://web.oswave.io"); } }, ic.link(), "Wave Web"),
        h("button", { className: "wb-btn ghost", onClick: function () { open("https://www.thetatoken.org"); } }, ic.link(), "Theta Network")),
      h("p", { className: "wb-dim small" }, "Links open in your browser. Theta Network and Hermes (Nous Research) are independent projects; Wave OS isn't affiliated with them."));
  }

  function Added(p) {
    var rows = p.rows;
    if (!rows.length) return h("div", { className: "wb-card wb-empty" }, h("b", null, "No Wave bots added yet."),
      h("p", { className: "wb-dim" }, "Pick a bot in the Store and click Add to Hermes. It shows up in your sidebar under Bots."));
    return h("div", { className: "wb-card wb-table" }, rows.map(function (r) {
      var s = STATUS[r.status] || ["", r.status || "Not checked"];
      return h("div", { className: "wb-tr", key: r.profile },
        h(Avatar, { src: p.avatars[r.tns], name: r.name }),
        h("div", { className: "wb-grow" }, h("b", null, r.name), h("div", { className: "wb-dim small" }, r.tns, " · ", r.ref, " · checked ", ago(r.checked_at)),
          r.edited ? h("div", { className: "wb-dim small" }, "Its SOUL.md was edited in Hermes, so it's no longer exactly the verified version.") : null),
        h(Chip, { tone: s[0] }, s[1]),
        r.status === "update_available" ? h("button", { className: "wb-btn", onClick: function () { p.onAct("update", r.profile); }, disabled: p.busy }, ic.up(), "Update") : null,
        h("button", { className: "wb-btn ghost", onClick: function () { p.onAct("check", r.profile); }, disabled: p.busy }, ic.sync(), "Check"),
        h("button", { className: "wb-btn ghost danger", onClick: function () { p.onAct("remove", r.profile, r.name); }, disabled: p.busy, title: "Remove from Hermes" }, ic.trash()));
    }));
  }

  function Connection(p) {
    var c = p.state || {}, conn = c.connection || {};
    var caps = conn.caps || {};
    var body;
    if (conn.connected) body = h(React.Fragment, null,
      h("div", { className: "wb-row" }, h(Chip, { tone: "ok", icon: ic.check() }, "Connected"), h("b", null, conn.label)),
      h("ul", { className: "wb-list" },
        h("li", null, "Spending limit: ", caps.per_call ? caps.per_call + " TFUEL per answer, " + caps.per_day + " a day" : "free and public bots only"),
        h("li", null, "Until ", String(conn.expires_at || "").slice(0, 10)),
        h("li", null, "Key kept in ", conn.store === "keyring" ? "your system keychain" : "a private file in your Hermes folder")),
      h("p", { className: "wb-dim" }, "It can only ask Wave bots. It can't change your files, apps, bots or wallet. Revoke it any time in Wave OS Settings › MCP Setup."),
      h("button", { className: "wb-btn ghost danger", onClick: p.onDisconnect, disabled: p.busy }, ic.x(), "Disconnect here"));
    else if (c.state === "waiting") body = h(React.Fragment, null,
      h("p", null, "Finish on app.oswave.io: sign in, pick your limits and click Connect. This page updates on its own."),
      h("div", { className: "wb-row" },
        h("button", { className: "wb-btn", onClick: function () { open(c.url); } }, ic.link(), "Open the page again"),
        h("button", { className: "wb-btn ghost", onClick: p.onCancel }, "Cancel")));
    else body = h(React.Fragment, null,
      conn.expired || conn.revoked ? h("div", { className: "wb-note" }, "Your Wave OS key expired or was revoked. Connect again.") : null,
      c.state === "error" ? h("div", { className: "wb-err" }, c.error) : null,
      h("p", null, "Everything else on this page works without an account. Connect adds one thing: asking the real bot on Wave OS, with a receipt."),
      h("p", { className: "wb-dim" }, "One click on app.oswave.io gives Hermes a limited key. You pick the spending limit (default: free and public bots only) and how long it lasts. It never shows on screen or in a link."),
      h("button", { className: "wb-btn primary", onClick: p.onConnect, disabled: p.busy }, ic.link(), "Connect Wave OS"));
    return h("div", { className: "wb-card wb-conn" }, h("h3", null, "Connect to Wave OS"), body);
  }

  return function WaveBots() {
    var th = useState(initialTheme), theme = th[0], setTheme = th[1];
    var ts = useState(function () { return /[?&]connected=1/.test((window.location.search || "") + (window.location.hash || "")) ? "connect" : "store"; }), tab = ts[0], setTab = ts[1];
    var bs = useState(null), bots = bs[0], setBots = bs[1];
    var as = useState([]), added = as[0], setAdded = as[1];
    var qs = useState(""), q = qs[0], setQ = qs[1];
    var os = useState(deepLinkBot), openQ = os[0], setOpenQ = os[1];
    var bn = useState(null), banner = bn[0], setBanner = bn[1];
    var pvs = useState(null), preview = pvs[0], setPreview = pvs[1];
    var bus = useState(false), busy = bus[0], setBusy = bus[1];
    var ers = useState(""), err = ers[0], setErr = ers[1];
    var tos = useState(""), toast = tos[0], setToast = tos[1];
    var vs = useState(0), version = vs[0], setVersion = vs[1];
    var cs = useState(null), conn = cs[0], setConn = cs[1];
    var fail = function (e) { setErr(String((e && e.message) || e)); };
    var loadConn = useCallback(function () { return call("/connect").then(setConn, function () {}); }, []);
    useEffect(function () { loadConn(); }, [loadConn]);
    useEffect(function () {
      if (!conn || conn.state !== "waiting") return;
      var t = setInterval(loadConn, 3000);
      return function () { clearInterval(t); };
    }, [conn && conn.state, loadConn]);
    useEffect(function () {
      if (conn && conn.state === "connected") setToast("Hermes is connected to Wave OS.");
    }, [conn && conn.state]);
    function connect() {
      setTab("connect"); setOpenQ(null);
      call("/connect/start", {}).then(function (r) { open(r.url); loadConn(); }, fail);
    }
    function disconnect() {
      if (!window.confirm("Forget the Wave OS key on this computer? To cancel it on Wave's side too, revoke it in Wave OS Settings › MCP Setup.")) return;
      call("/disconnect", {}).then(function (r) { setToast(r.note); loadConn(); }, fail);
    }
    function cancelConnect() { call("/connect/cancel", {}).then(loadConn, fail); }
    var connected = !!(conn && conn.connection && conn.connection.connected);
    var ps = useState(null), plugins = ps[0], setPlugins = ps[1];
    useEffect(function () { call("/wave-plugins").then(function (r) { setPlugins(r.plugins || {}); }, function () {}); }, []);
    var bv = plugins && plugins.brainvault && plugins.brainvault.enabled;

    var load = useCallback(function (refresh) {
      return Promise.all([call("/bots" + (refresh ? "?refresh=true" : "")), call("/added")]).then(function (r) {
        setBots(r[0].bots || []); setAdded(r[1].added || []); setErr("");
      }, fail);
    }, []);
    useEffect(function () { load(false); call("/banner").then(function (r) { setBanner(r.data); }, function () {}); }, [load]);
    useEffect(function () { try { localStorage.setItem("wb-theme", theme); } catch (_) {} }, [theme]);
    useEffect(function () { if (!toast) return; var t = setTimeout(function () { setToast(""); }, 5000); return function () { clearTimeout(t); }; }, [toast]);

    function startAdd(bot) {
      setBusy(true); setErr("");
      call("/preview", { bot: bot }).then(function (pv) {
        setBusy(false);
        if (!pv.can_add) { fail(pv.reason); return; }
        setPreview(pv);
      }, function (e) { setBusy(false); fail(e); });
    }
    function confirmAdd() {
      setBusy(true);
      call("/add", { bot: preview.tns || preview.ref }).then(function (r) {
        setBusy(false); setPreview(null);
        setToast(r.bot.name + (r.created ? " is in your Bots list. Open it from Bots in the sidebar (reload Hermes if it isn't there yet)." : " was refreshed from Theta."));
        load(false); setVersion(version + 1);
      }, function (e) { setBusy(false); setPreview(Object.assign({}, preview, { err: String(e.message || e) })); });
    }
    function act(kind, profile, name) {
      if (kind === "remove" && !window.confirm("Delete " + name + " and its chat from Hermes? The bot on Theta stays.")) return;
      setBusy(true); setErr("");
      call("/" + kind, { bot: profile }).then(function (r) {
        setBusy(false);
        setToast(kind === "remove" ? name + " was removed from Hermes." : kind === "update" ? "Updated to " + r.bot.ref + ". Its chat is kept." : (r.note || "Checked."));
        load(false);
      }, function (e) { setBusy(false); fail(e); });
    }

    var avatars = {};
    (bots || []).forEach(function (b) { avatars[b.tns] = b.avatar; });
    var words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    var shown = (bots || []).filter(function (b) {
      var hay = [b.name, b.slug, b.pitch, b.category, b.role].join(" ").toLowerCase();
      return words.every(function (w) { return hay.indexOf(w) >= 0; });
    });

    var body;
    if (openQ) body = h(BotPage, { q: openQ, version: version, onAdd: startAdd, connected: connected, onConnect: connect });
    else if (tab === "added") body = h(Added, { rows: added, avatars: avatars, busy: busy, onAct: act });
    else if (tab === "about") body = h(About, { plugins: plugins });
    else if (tab === "connect") body = h(Connection, { state: conn, busy: busy, onConnect: connect, onDisconnect: disconnect, onCancel: cancelConnect });
    else body = h(React.Fragment, null,
      h("div", { className: "wb-row" },
        h("label", { className: "wb-search" }, ic.search(), h("input", { value: q, placeholder: "What do you need done? e.g. check my numbers", onChange: function (e) { setQ(e.target.value); }, "aria-label": "Search bots" })),
        h("button", { className: "wb-btn ghost", onClick: function () { setBots(null); load(true); }, title: "Check every bot on Theta again" }, ic.sync(), "Refresh")),
      bots === null ? h("div", { className: "wb-card wb-dim" }, "Reading bots from Theta… (about 15 seconds the first time)")
        : shown.length ? h("div", { className: "wb-grid" }, shown.map(function (b) { return h(Tile, { key: b.tns, bot: b, onOpen: setOpenQ }); }))
        : h("div", { className: "wb-card wb-dim" }, "No bot matches that yet."));

    return h("div", { className: "wb", "data-wb-theme": theme },
      h("div", { className: "wb-wrap" },
        h("header", { className: "wb-hero", style: banner ? { backgroundImage: "linear-gradient(90deg,var(--wb-hero-fade) 30%,transparent 75%),url(" + banner + ")" } : null },
          h("div", { className: "wb-hero-text" },
            h("h1", null, h("span", { className: "wb-wave" }, "Wave"), " | Bots"),
            h("p", null, "Verified bots from the bots.theta store. Checked on the Theta blockchain, on this computer."),
            h("div", { className: "wb-tile-chips" }, h(Chip, { tone: "ok", icon: ic.shield() }, "Checked on Theta"), h(Chip, null, "Runs on your AI"), connected ? h(Chip, { tone: "mint", icon: ic.check() }, "Wave OS connected") : h(Chip, null, "No account needed"))),
          h("div", { className: "wb-hero-actions" },
            bv ? h("button", { className: "wb-btn", onClick: function () { go("/brainvault"); }, title: "Open Wave | BrainVault Mint" }, h("span", { className: "wb-leaf sm" }, ic.leaf()), "BrainVault Mint") : null,
            h("button", { className: "wb-icon", onClick: function () { setTheme(theme === "dark" ? "light" : "dark"); }, "aria-label": "Switch theme" }, theme === "dark" ? ic.sun() : ic.moon()))),
        h("nav", { className: "wb-tabs", role: "tablist" },
          openQ ? h("button", { className: "wb-tab", onClick: function () { setOpenQ(null); } }, ic.back(), "Back") : null,
          [["store", "Store"], ["added", "Added (" + added.length + ")"], ["connect", "Connection"], ["about", "About"]].map(function (t) {
            return h("button", { key: t[0], role: "tab", "aria-selected": !openQ && tab === t[0], className: "wb-tab" + (!openQ && tab === t[0] ? " on" : ""),
              onClick: function () { setOpenQ(null); setTab(t[0]); } }, t[1]);
          }),
          h("span", { className: "wb-sp" }), h("span", { className: "wb-dim small" }, "v" + UI_VERSION)),
        err ? h("div", { className: "wb-err", role: "alert" }, err, h("button", { className: "wb-x", onClick: function () { setErr(""); }, "aria-label": "Dismiss" }, ic.x())) : null,
        toast ? h("div", { className: "wb-toast", role: "status" }, toast) : null,
        body,
        preview ? h(AddSheet, { preview: preview, busy: busy, err: preview.err, onClose: function () { if (!busy) setPreview(null); }, onConfirm: confirmAdd }) : null));
  };
}
