/**
 * Wave | BrainVault: Hermes dashboard tab.
 * Plain IIFE, no build step. React comes from window.__HERMES_PLUGIN_SDK__; styles are in style.css (scoped .bv).
 * Talks to the plugin's own API at /api/plugins/brainvault/. Nothing here signs or mints: "Send to Wave"
 * opens Wave Web, where the user mints with Wave Wallet Mint.
 */
(function () {
  "use strict";
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;
  var React = SDK.React, h = React.createElement;
  var useState = SDK.hooks.useState, useEffect = SDK.hooks.useEffect, useCallback = SDK.hooks.useCallback,
      useMemo = SDK.hooks.useMemo, useRef = SDK.hooks.useRef;
  var API = "/api/plugins/brainvault";

  function call(path, body) {
    var init = body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    return SDK.fetchJSON(API + path, init).catch(function (e) {
      var m = String((e && e.message) || e), i = m.indexOf("{");
      if (i >= 0) { try { var j = JSON.parse(m.slice(i)); if (j.detail) m = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) {} }
      throw new Error(m.replace(/^\d{3}:\s*/, ""));
    });
  }
  function ago(ts) {
    if (!ts) return "never";
    var s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 45) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " d ago";
  }
  function isoTs(iso) { var t = iso ? Date.parse(iso) : NaN; return isNaN(t) ? 0 : t / 1000; }
  function plural(n, w) { return n + " " + (n === 1 ? w : w.replace(/y$/, "ie") + "s"); }

  // ---- icons (inline SVG, lucide-style) ----
  function I(d, size) {
    return h("svg", { width: size || 15, height: size || 15, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" }, d.map(function (p, i) { return h("path", { key: i, d: p }); }));
  }
  var ic = {
    lock: function () { return I(["M7 11V7a5 5 0 0 1 10 0v4", "M5 11h14v10H5z"], 14); },
    globe: function () { return I(["M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20", "M2 12h20", "M12 2a15 15 0 0 1 0 20", "M12 2a15 15 0 0 0 0 20"], 14); },
    sync: function () { return I(["M21 12a9 9 0 1 1-3-6.7L21 8", "M21 3v5h-5"]); },
    send: function () { return I(["M22 2L11 13", "M22 2l-7 20-4-9-9-4z"]); },
    link: function () { return I(["M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1", "M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"]); },
    check: function () { return I(["M20 6L9 17l-5-5"], 14); },
    search: function () { return I(["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14", "M21 21l-4.3-4.3"]); },
    trash: function () { return I(["M3 6h18", "M8 6V4h8v2", "M6 6l1 14h10l1-14"], 14); },
    plus: function () { return I(["M12 5v14", "M5 12h14"]); },
    shield: function () { return I(["M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6z"], 14); },
    x: function () { return I(["M18 6L6 18", "M6 6l12 12"], 14); },
  };
  function Logo() {
    return h("div", { className: "bv-logo" }, h("svg", { width: 26, height: 26, viewBox: "0 0 32 32", fill: "none" },
      h("path", { d: "M3 19c3.5 0 3.5-6 7-6s3.5 6 7 6 3.5-6 7-6 3.5 6 5 6", stroke: "#04211b", strokeWidth: 2.6, strokeLinecap: "round" }),
      h("path", { d: "M3 12c3.5 0 3.5-5 7-5s3.5 5 7 5 3.5-5 7-5 3.5 5 5 5", stroke: "#04211b", strokeWidth: 2, strokeLinecap: "round", opacity: .55 })));
  }

  function Toast(props) {
    var t = props.toast;
    if (!t) return null;
    return h("div", { className: "bv-toast" + (t.err ? " err" : "") },
      h("div", { style: { display: "flex", gap: 10, alignItems: "flex-start" } },
        h("div", { style: { flex: 1 } }, t.msg, t.link ? h("div", { style: { marginTop: 6 } }, h("a", { href: t.link, target: "_blank", rel: "noopener noreferrer" }, t.linkLabel || "Open")) : null),
        h("button", { className: "bv-btn sm ghost", onClick: props.onClose, "aria-label": "Close" }, ic.x())));
  }

  function Flow(props) {
    var s = props.s, mem = (s && s.memories) || {};
    var local = (mem.local || 0) + (mem.exported || 0) + (mem.minted || 0);
    var steps = [
      { k: "Remember", d: plural(local, "memory"), lit: local > 0 },
      { k: "Review", d: (mem.exported || 0) + " in Wave Web", lit: (mem.exported || 0) + (mem.minted || 0) > 0 },
      { k: "Mint", d: "Wave Wallet Mint", lit: (mem.minted || 0) > 0 || (s && s.cards > 0) },
      { k: "On Theta", d: plural((s && s.cards) || 0, "card"), lit: s && s.cards > 0 },
      { k: "Recall anywhere", d: ((s && s.cards_opened) || 0) + " opened here", lit: s && s.cards_opened > 0 },
    ];
    return h("div", { className: "bv-flow" }, steps.map(function (st, i) {
      return h("div", { key: st.k, className: "bv-step" + (st.lit ? " lit" : "") },
        h("div", { className: "bv-node" }, st.lit ? ic.check() : i + 1), h("b", null, st.k), h("span", null, st.d));
    }));
  }

  function Stats(props) {
    var s = props.s || {}, m = s.memories || {}, mems = props.mems || [];
    var total = (m.local || 0) + (m.exported || 0) + (m.minted || 0);
    var priv = mems.filter(function (x) { return x.private; }).length;
    var tiles = [
      { n: total, l: "Memories in this Hermes" },
      { n: mems.length ? Math.round(100 * priv / mems.length) + "%" : "–", l: "Private (encrypted when minted)" },
      { n: s.cards || 0, l: "Cards from your vault", mint: true },
      { n: s.cards_opened || 0, l: "Opened with this agent's key" },
      { n: s.cards ? (s.cards_hash_failed ? s.cards_hash_failed + " failed" : "100%") : "–", l: "Fingerprint checks passed", mint: !s.cards_hash_failed },
    ];
    return h("div", { className: "bv-stats" }, tiles.map(function (t) {
      return h("div", { key: t.l, className: "bv-stat" }, h("div", { className: "n" + (t.mint ? " mint" : "") }, t.n), h("div", { className: "l" }, t.l));
    }));
  }

  function PairBanner(props) {
    var p = props.pairing || {}, waiting = p.state === "waiting";
    var left = waiting ? Math.max(0, Math.round((p.expires - Date.now() / 1000) / 60)) : 0;
    return h("div", { className: "bv-pair" },
      h("div", { style: { flex: 1, minWidth: 260 } },
        h("h3", null, waiting ? "Waiting for Wave Wallet Mint…" : "Pair this Hermes with your wallet"),
        h("div", { style: { color: "var(--bv-dim)" } }, waiting
          ? "Approve \u201cGive Hermes its own memory key\u201d in the wallet. This page updates by itself (" + left + " min left)."
          : "This Hermes gets its own decrypt-only key, so it can open the private cards you make readable by it. It can never spend or sign, and you can revoke it in the wallet."),
        !waiting ? h("ol", null, h("li", null, "Open Wave Web and sign in with Wave Wallet Mint"), h("li", null, "Approve the memory key"), h("li", null, "Come back here: you're paired")) : null),
      waiting ? h("div", { style: { display: "flex", gap: 8, alignItems: "center" } }, h("div", { className: "bv-spin" }),
          h("a", { className: "bv-btn", href: p.url, target: "_blank", rel: "noopener noreferrer" }, ic.link(), "Open pairing page"))
        : h("button", { className: "bv-btn pri", onClick: props.onPair, disabled: props.busy }, ic.link(), "Pair with Wave Wallet Mint"),
      p.state === "failed" ? h("div", { style: { width: "100%", color: "#ff9a9a" } }, p.error) : null);
  }

  function WalletBanner(props) {
    var _a = useState(""), addr = _a[0], setAddr = _a[1];
    return h("div", { className: "bv-pair" },
      h("div", { style: { flex: 1, minWidth: 260 } }, h("h3", null, "Add your Wave wallet address"),
        h("div", { style: { color: "var(--bv-dim)" } }, "Wave BrainVault finds your vault cards on Theta by the wallet that minted them. Your address is public; your key never leaves Wave Wallet Mint.")),
      h("input", { className: "bv-in", style: { maxWidth: 380 }, placeholder: "0x…", value: addr, onChange: function (e) { setAddr(e.target.value); } }),
      h("button", { className: "bv-btn pri", disabled: !/^0x[0-9a-fA-F]{40}$/.test(addr.trim()), onClick: function () { props.onSave(addr.trim()); } }, "Save"));
  }

  function Composer(props) {
    var _a = useState(""), text = _a[0], setText = _a[1];
    var _b = useState(true), priv = _b[0], setPriv = _b[1];
    useEffect(function () { setPriv(props.defaultPrivate !== false); }, [props.defaultPrivate]);
    function go() { if (!text.trim()) return; props.onRemember(text.trim(), priv).then(function (ok) { if (ok) setText(""); }); }
    return h("div", { className: "bv-compose" },
      h("textarea", { className: "bv-ta", rows: 2, placeholder: "Teach Hermes something worth keeping\u2026  (e.g. \u201cOur launch demo is due Nov 11 at 5 PM EST\u201d)",
        value: text, onChange: function (e) { setText(e.target.value); },
        onKeyDown: function (e) { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) go(); } }),
      h("div", { className: "bv-row-a" },
        h("div", { className: "bv-tog" },
          h("button", { className: priv ? "on" : "", onClick: function () { setPriv(true); } }, ic.lock(), " Private"),
          h("button", { className: !priv ? "on" : "", onClick: function () { setPriv(false); } }, ic.globe(), " Public")),
        h("span", { style: { color: "var(--bv-dim)", fontSize: 12 } }, priv ? "Encrypted to you and this Hermes when minted" : "Public cards are readable by anyone, forever"),
        h("div", { className: "bv-sp" }),
        h("button", { className: "bv-btn pri sm", disabled: !text.trim() || props.busy, onClick: go }, ic.plus(), "Remember")));
  }

  var STATE_LABEL = { local: "Only here", exported: "In review", minted: "On chain" };

  function Memories(props) {
    var _a = useState("all"), tab = _a[0], setTab = _a[1];
    var _b = useState(""), q = _b[0], setQ = _b[1];
    var _c = useState({}), sel = _c[0], setSel = _c[1];
    var _d = useState(null), open = _d[0], setOpen = _d[1];
    var mems = props.mems || [];
    var shown = mems.filter(function (m) {
      if (tab === "local" && m.state !== "local") return false;
      if (tab === "exported" && m.state !== "exported") return false;
      if (tab === "minted" && m.state !== "minted") return false;
      if (!q) return true;
      var t = (m.title + " " + m.body + " " + (m.tags || []).join(" ")).toLowerCase();
      return t.indexOf(q.toLowerCase()) >= 0;
    });
    var ids = Object.keys(sel).filter(function (k) { return sel[k]; });
    var localCount = mems.filter(function (m) { return m.state === "local"; }).length;
    function count(s) { return mems.filter(function (m) { return m.state === s; }).length; }
    var tabs = [["all", "All", mems.length], ["local", "Only here", count("local")], ["exported", "In review", count("exported")], ["minted", "On chain", count("minted")]];
    return h("div", { className: "bv-panel" },
      h("div", { className: "bv-ph" }, h("h3", null, "Memories"), h("span", { className: "c" }, "captured by Hermes, kept on this computer until you mint them"),
        h("div", { className: "bv-sp" }),
        h("div", { style: { position: "relative" } }, h("input", { className: "bv-in", style: { width: 170, height: 30, padding: "4px 10px" }, placeholder: "Filter\u2026", value: q, onChange: function (e) { setQ(e.target.value); } }))),
      h(Composer, { onRemember: props.onRemember, busy: props.busy, defaultPrivate: props.defaultPrivate }),
      h("div", { className: "bv-tabs" }, tabs.map(function (t) {
        return h("button", { key: t[0], className: "bv-tab" + (tab === t[0] ? " on" : ""), onClick: function () { setTab(t[0]); } }, t[1] + " \u00b7 " + t[2]);
      })),
      h("div", { className: "bv-list" }, shown.length ? shown.map(function (m) {
        var isOpen = open === m.id;
        return h("div", { key: m.id, className: "bv-item" + (props.fresh === m.id ? " new" : ""), onClick: function () { setOpen(isOpen ? null : m.id); } },
          h("input", { type: "checkbox", className: "bv-cb", checked: !!sel[m.id], disabled: m.state === "minted",
            onClick: function (e) { e.stopPropagation(); }, onChange: function (e) { var n = Object.assign({}, sel); n[m.id] = e.target.checked; setSel(n); } }),
          h("div", null,
            h("div", { className: "t" }, m.title),
            h("div", { className: "b" + (isOpen ? "" : " clip") }, m.body),
            h("div", { className: "bv-meta" },
              h("span", { className: "bv-tag" }, m.private ? ic.lock() : ic.globe(), " ", m.private ? "private" : "public"),
              (m.tags || []).slice(0, 3).map(function (t) { return h("span", { key: t, className: "bv-tag" }, "#" + t); }),
              h("span", { className: "bv-tag" }, m.trust === "operator" ? "you" : m.trust),
              h("span", { className: "bv-tag" }, ago(m.created)),
              m.ref ? h("a", { className: "bv-tag", href: props.waveWeb + "/card/" + m.ref, target: "_blank", rel: "noopener noreferrer", onClick: function (e) { e.stopPropagation(); } }, m.ref) : null,
              isOpen && m.state !== "minted" ? h("button", { className: "bv-btn sm ghost danger", onClick: function (e) { e.stopPropagation(); props.onForget(m.id); } }, ic.trash(), "Forget here") : null)),
          h("span", { className: "bv-st " + m.state }, STATE_LABEL[m.state] || m.state));
      }) : h("div", { className: "bv-empty" }, mems.length ? "Nothing matches." : "No memories yet. Chat with Hermes, or teach it something above.")),
      h("div", { className: "bv-sendbar" },
        h("span", { style: { color: "var(--bv-dim)", fontSize: 12 } }, ids.length ? plural(ids.length, "memory") + " selected" : localCount ? plural(localCount, "new memory") + " ready for Wave" : "Everything is sent"),
        h("div", { className: "bv-sp" }),
        ids.length ? h("button", { className: "bv-btn sm ghost", onClick: function () { setSel({}); } }, "Clear") : null,
        h("button", { className: "bv-btn pri sm", disabled: props.busy || (!ids.length && !localCount),
          onClick: function () { props.onSend(ids).then(function (ok) { if (ok) setSel({}); }); } }, ic.send(), ids.length ? "Send selected to Wave" : "Send new to Wave")));
  }

  function Recall(props) {
    var _a = useState(""), q = _a[0], setQ = _a[1];
    var _b = useState(null), res = _b[0], setRes = _b[1];
    var _c = useState(false), busy = _c[0], setBusy = _c[1];
    var timer = useRef(null);
    function run(v) {
      if (!v.trim()) { setRes(null); return; }
      setBusy(true);
      call("/recall?q=" + encodeURIComponent(v)).then(function (r) { setRes(r.results); }).catch(function () { setRes([]); }).finally(function () { setBusy(false); });
    }
    function onChange(e) { var v = e.target.value; setQ(v); clearTimeout(timer.current); timer.current = setTimeout(function () { run(v); }, 250); }
    return h("div", { className: "bv-panel" },
      h("div", { className: "bv-ph" }, h("h3", null, "Recall test"), h("span", { className: "c" }, "what Hermes would remember, right now"), h("div", { className: "bv-sp" }), busy ? h("div", { className: "bv-spin" }) : null),
      h("div", { className: "bv-pb" },
        h("div", { style: { position: "relative" } },
          h("input", { className: "bv-in", placeholder: "Ask anything\u2026  e.g. \u201cwhen is the demo due?\u201d", value: q, onChange: onChange })),
        res === null ? h("div", { style: { color: "var(--bv-dim)", fontSize: 12, marginTop: 8 } }, "Results come from this computer and from your vault cards on Theta. Recalled text is treated as notes, never as instructions.") :
          res.length ? res.map(function (r) {
            return h("div", { key: r.id, className: "bv-res" },
              h("div", { className: "w" },
                h("span", { className: "bv-src " + (r.where === "vault" ? "vault" : "local") }, r.where === "vault" ? "VAULT" : "LOCAL"),
                r.ref ? h("a", { className: "bv-ref", href: props.waveWeb + "/card/" + r.ref, target: "_blank", rel: "noopener noreferrer" }, r.ref) : null,
                r.private ? h("span", null, ic.lock(), " private") : h("span", null, ic.globe(), " public"),
                r.where === "vault" ? h("span", { style: { color: "var(--bv-mint)" } }, ic.shield(), " fingerprint verified") : null,
                h("div", { className: "bv-sp" }), h("span", null, "score " + r.score)),
              h("div", { style: { whiteSpace: "pre-wrap", wordBreak: "break-word" } },
                r.title && r.where !== "vault" && r.text.indexOf(r.title.replace(/\u2026$/, "")) !== 0 ? h("b", null, r.title + "\n") : null, r.text));
          }) : h("div", { className: "bv-empty" }, "Nothing recalled for that.")));
  }

  function Vault(props) {
    var cards = props.cards || [];
    return h("div", { className: "bv-panel", style: { marginTop: 16 } },
      h("div", { className: "bv-ph" }, h("h3", null, "Your vault on Theta"), h("span", { className: "c" }, plural(cards.length, "card") + " seen"),
        h("div", { className: "bv-sp" }),
        h("button", { className: "bv-btn sm", onClick: props.onSync, disabled: props.busy || !props.wallet }, props.syncing ? h("div", { className: "bv-spin" }) : ic.sync(), "Sync now")),
      h("div", { className: "bv-list", style: { maxHeight: 360 } }, cards.length ? cards.map(function (c) {
        var cls = !c.readable ? "no" : c.private ? "" : "pub";
        return h("div", { key: c.ref, className: "bv-card" },
          h("div", { className: "bv-ico " + cls }, c.private ? ic.lock() : ic.globe()),
          h("div", { style: { flex: 1, minWidth: 0 } },
            h("div", { style: { display: "flex", gap: 8, alignItems: "center" } },
              h("a", { className: "bv-ref", href: props.waveWeb + "/card/" + c.ref, target: "_blank", rel: "noopener noreferrer" }, c.ref),
              c.sha_ok ? h("span", { style: { color: "var(--bv-mint)", fontSize: 11.5 } }, ic.check(), " verified") : h("span", { style: { color: "#ff9a9a", fontSize: 11.5 } }, "hash failed"),
              c.private ? h("span", { style: { color: "var(--bv-dim)", fontSize: 11.5 } }, c.opened ? "opened with agent key" : "not readable by this Hermes") : null,
              c.superseded_by ? h("span", { className: "bv-tag" }, "replaced by " + c.superseded_by) : null),
            h("div", { style: { color: c.readable ? "var(--bv-ink)" : "var(--bv-dim)", fontSize: 12.5, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } },
              c.readable ? c.title : "Encrypted. Make it \u201cReadable by: Me + this Hermes\u201d to open it here.")));
      }) : h("div", { className: "bv-empty" }, props.wallet ? "No cards yet. Send memories to Wave, mint them, then Sync." : "Add your wallet address to see your vault.")));
  }

  function BrainVaultPage() {
    var _a = useState(null), data = _a[0], setData = _a[1];
    var _b = useState(null), err = _b[0], setErr = _b[1];
    var _c = useState(false), busy = _c[0], setBusy = _c[1];
    var _d = useState(false), syncing = _d[0], setSyncing = _d[1];
    var _e = useState(null), toast = _e[0], setToast = _e[1];
    var _f = useState(null), fresh = _f[0], setFresh = _f[1];
    var toastTimer = useRef(null);
    function say(msg, opts) {
      clearTimeout(toastTimer.current);
      setToast(Object.assign({ msg: msg }, opts || {}));
      toastTimer.current = setTimeout(function () { setToast(null); }, (opts && opts.link) ? 15000 : 5000);
    }
    var load = useCallback(function () {
      return call("/state").then(function (d) { setData(d); setErr(null); }).catch(function (e) { setErr(e.message); });
    }, []);
    useEffect(function () { load(); }, [load]);
    var waiting = data && data.pairing && data.pairing.state === "waiting";
    useEffect(function () {
      var t = setInterval(load, waiting ? 3000 : 15000);
      return function () { clearInterval(t); };
    }, [load, waiting]);
    var prevPair = useRef(null);
    useEffect(function () {
      var st = data && data.pairing && data.pairing.state;
      if (prevPair.current === "waiting" && st === "paired") say("Paired as \u201c" + data.pairing.agent + "\u201d. This Hermes can now open cards you make readable by it.");
      prevPair.current = st;
    }, [data]);

    function act(p, fn) {
      setBusy(true);
      return p.then(function (r) { var o = fn ? fn(r) : true; return load().then(function () { return o; }); })
        .catch(function (e) { say(e.message, { err: true }); return false; }).finally(function () { setBusy(false); });
    }
    function onRemember(text, priv) {
      return act(call("/remember", { text: text, private: priv }), function (r) {
        setFresh(r.id || null);
        say(r.created === false ? "Already remembered." : "Remembered" + (priv ? " (private)." : " (public)."));
        return true;
      });
    }
    function onSend(ids) {
      return act(call("/send", { ids: ids }), function (r) {
        var url = r.review_url;
        var w = url ? window.open(url, "_blank", "noopener") : null;
        say(plural(r.cards, "memory") + " sent to Wave Web for review" + (r.private ? " (" + r.private + " private)" : "") + ". Mint there with Wave Wallet Mint, then Sync."
          + (r.path ? " Wave Web's link service was busy, so they were saved to a file instead." : "") + (w ? "" : " Your browser blocked the new tab:"),
          { link: url, linkLabel: r.path ? "Open Wave Web migration" : "Open the review page (works once, 10 min)" });
        return true;
      });
    }
    function onSync() {
      setSyncing(true);
      return act(call("/sync", {}), function (r) {
        say(r.new ? "Synced: " + plural(r.new, "new card") + (r.opened ? ", " + r.opened + " opened with this Hermes's key" : "") + "." : "Your vault is up to date.");
        return true;
      }).finally(function () { setSyncing(false); });
    }
    function onForget(id) { return act(call("/forget", { id: id }), function () { say("Forgotten on this computer. Cards already on chain stay on chain."); return true; }); }
    function onPair() {
      return act(call("/pair", {}), function (r) { if (r.url) window.open(r.url, "_blank", "noopener"); return true; });
    }
    function onWallet(a) { return act(call("/wallet", { address: a }), function () { say("Wallet saved. Syncing your vault\u2026"); setTimeout(onSync, 300); return true; }); }

    if (err && !data) return h("div", { className: "bv" }, h("div", { className: "bv-pair" }, h("div", null, h("h3", null, "Wave | BrainVault couldn't load"), h("div", { style: { color: "var(--bv-dim)" } }, err))));
    if (!data) return h("div", { className: "bv" }, h("div", { className: "bv-empty" }, h("div", { className: "bv-spin", style: { margin: "0 auto 10px" } }), "Loading your memory\u2026"));

    var s = data.status, ww = data.wave_web || "https://web.oswave.io";
    var lastSync = isoTs(s.last_sync);
    return h("div", { className: "bv" },
      h("div", { className: "bv-hero" },
        h("div", { className: "bv-top" },
          h(Logo),
          h("div", null, h("h1", { className: "bv-title" }, h("span", { className: "bv-wave" }, "Wave"), h("span", { className: "bv-pipe" }, "|"), "BrainVault"), h("div", { className: "bv-sub" }, "Your Hermes memory, owned by your wallet, stored on Theta.")),
          h("div", { className: "bv-sp" }),
          h("button", { className: "bv-btn", onClick: onSync, disabled: busy || !s.wallet }, syncing ? h("div", { className: "bv-spin" }) : ic.sync(), "Sync"),
          h("a", { className: "bv-btn", href: ww, target: "_blank", rel: "noopener noreferrer" }, ic.link(), "Wave Web")),
        h("div", { className: "bv-chips" },
          h("span", { className: "bv-chip " + (s.wallet ? "ok" : "warn") }, h("span", { className: "bv-dot" + (s.wallet ? " on" : "") }), "Wallet ", h("b", null, data.wallet_short || "not set")),
          h("span", { className: "bv-chip " + (s.paired ? "ok" : "warn") }, h("span", { className: "bv-dot" + (s.paired ? " on" : waiting ? " wait" : "") }),
            s.paired ? h("span", null, "Paired as ", h("b", null, (s.agent && s.agent.label) || "Hermes")) : waiting ? "Pairing\u2026" : "Not paired"),
          h("span", { className: "bv-chip" }, h("span", { className: "bv-dot" + (lastSync ? " on" : "") }), "Synced ", h("b", null, ago(lastSync))),
          h("span", { className: "bv-chip" }, ic.lock(), s.default_private ? "Private by default" : "Public by default"),
          h("span", { className: "bv-chip" }, ic.shield(), "Never signs, never mints, never sees your wallet key")),
        h(Flow, { s: s })),
      !s.wallet ? h(WalletBanner, { onSave: onWallet }) : null,
      s.wallet && !s.paired ? h(PairBanner, { pairing: data.pairing, onPair: onPair, busy: busy }) : null,
      h(Stats, { s: s, mems: data.memories }),
      h("div", { className: "bv-grid" },
        h(Memories, { mems: data.memories, onRemember: onRemember, onSend: onSend, onForget: onForget, busy: busy, fresh: fresh, waveWeb: ww, defaultPrivate: s.default_private }),
        h("div", null,
          h(Recall, { waveWeb: ww }),
          h(Vault, { cards: data.cards, onSync: onSync, busy: busy, syncing: syncing, wallet: s.wallet, waveWeb: ww }))),
      h("div", { className: "bv-foot" },
        h("span", null, ic.shield(), "Private cards are encrypted in Wave Wallet Mint, not here"),
        h("span", null, ic.check(), "Every card read from Theta is fingerprint-checked"),
        h("span", null, "Wave | BrainVault " + (s.version || "") + " \u00b7 a Wave OS product")),
      h(Toast, { toast: toast, onClose: function () { setToast(null); } }));
  }

  window.__HERMES_PLUGINS__.register("brainvault", BrainVaultPage);
})();
