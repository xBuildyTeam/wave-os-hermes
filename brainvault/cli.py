"""`hermes brainvault …` commands (wired by Hermes only while BrainVault is the active memory provider)."""
from __future__ import annotations

import json
import sys
import webbrowser


def _vault():
    from hermes_constants import get_hermes_home
    from ._core import Vault
    return Vault(get_hermes_home())


def register_cli(sub) -> None:
    sp = sub.add_subparsers(dest="bv_cmd")
    sp.add_parser("status", help="Wallet, pairing, memory counts")
    w = sp.add_parser("wallet", help="Set your Wave wallet address")
    w.add_argument("address")
    p = sp.add_parser("pair", help="Pair this Hermes with your wallet (opens Wave Web)")
    p.add_argument("--no-browser", action="store_true", help="Print the link instead of opening it")
    sp.add_parser("unpair", help="Delete this install's agent key (revoke it in Wave Wallet Mint too)")
    sp.add_parser("sync", help="Read new cards from your Wave vault now")
    sp.add_parser("doctor", help="Check the setup and explain how to fix anything wrong")
    s = sp.add_parser("search", help="Search memories")
    s.add_argument("query", nargs="+")
    sp.add_parser("list", help="List local memories")
    f = sp.add_parser("forget", help="Remove a local memory by id")
    f.add_argument("id")
    e = sp.add_parser("export", help="Write new memories to a Wave migration file")
    e.add_argument("--all", action="store_true", help="Include memories already exported")
    e.add_argument("--file", action="store_true", help="Write a migration file instead of a one-time review link")
    e.add_argument("--no-browser", action="store_true")


def brainvault_command(args) -> int:
    from ._core import VaultError, format_recall
    cmd = getattr(args, "bv_cmd", None) or "status"
    v = _vault()
    try:
        if cmd == "status":
            print(json.dumps(v.status(), indent=2))
        elif cmd == "wallet":
            v.set_wallet(args.address)
            print(f"Wallet set: {v.cfg['wallet']}")
        elif cmd == "pair":
            pend = v.start_pair()
            print("Open this link in the browser where Wave Wallet Mint is installed, then approve in the wallet:\n")
            print("  " + pend["url"] + "\n")
            if not args.no_browser:
                webbrowser.open(pend["url"])
            print("Waiting for the wallet (up to 10 minutes)…")
            r = v.pair_wait(pend)
            a = r["agent"]
            print(f"Paired as \"{a['label']}\" ({a['address'] or a['id']}). Key stored in your {r['key_store']}.")
            if not v.cfg.get("wallet"):
                print("Next: hermes brainvault wallet 0x…  (your Wave Wallet Mint address)")
        elif cmd == "unpair":
            v.unpair()
            print("Agent key deleted here. Also revoke it in Wave Wallet Mint › Settings › Agent keys.")
        elif cmd == "doctor":
            from ._core import format_doctor
            r = v.doctor()
            print(format_doctor(r))
            return 0 if r["ok"] else 1
        elif cmd == "sync":
            print(json.dumps(v.sync(), indent=2))
        elif cmd == "search":
            print(format_recall(v.recall(" ".join(args.query), 10)) or "No matches.")
        elif cmd == "list":
            for m in v.store.memories():
                print(f"{m['fp']}  [{m['state']}{', private' if m['private'] else ''}]  {m['title']}")
        elif cmd == "forget":
            print("Removed." if v.forget(args.id) else "No such memory.")
        elif cmd == "export":
            r = v.export_pack(include_exported=args.all, to_file=args.file)
            if "path" in r:
                if r.get("drop_error"):
                    print(f"Couldn't make a review link ({r['drop_error']}), so the cards went to a file instead.")
                print(f"{r['cards']} cards → {r['path']}")
                print(f"In Wave Web choose Paste, paste the file, review, then mint with Wave Wallet Mint: {r['review_url']}")
            else:
                print(f"{r['cards']} cards ready to review ({r['private']} private). The link works once, for 10 minutes:\n")
                print("  " + r["review_url"] + "\n")
            if not args.no_browser:
                webbrowser.open(r["review_url"])
        return 0
    except VaultError as e:
        print(f"brainvault: {e}", file=sys.stderr)
        return 1
    finally:
        v.store.close()
