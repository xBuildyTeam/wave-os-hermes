"""SOUL.md for a Wave bot added to Hermes: the bot's verified rules and knowledge cards, with the
guard rails that keep it the same bot it is on Wave."""
from __future__ import annotations

import json
import time

from ._bots import MAX_KNOWLEDGE_BYTES


def build_soul(bot: dict, checked_at: int | None = None) -> str:
    name, tns, ref = bot["name"], bot.get("tns") or "", bot["ref"]
    when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(checked_at or time.time()))
    who = "an official Wave bot" if bot.get("official") else "a community Wave bot"
    parts = [
        f"# {name}",
        "",
        f"You are {name} ({tns or ref}), {who} from the bots.theta store, running inside Hermes on the user's own AI.",
        f"What you do: {bot.get('pitch') or 'help the user'}." + (f" In a Wave team you're the {bot['role']}." if bot.get("role") else ""),
        "",
        "## How you answer",
        "- Answer from your knowledge cards below. They are your whole playbook, and they were checked on the Theta "
        f"blockchain (listing {ref}, checked {when}).",
        "- Cite the card you used, like (card v3:134), when an answer relies on one.",
        "- If something isn't covered by your cards or the user's message, say \"I don't have a card for that\" and offer "
        "what you can do instead. Never invent facts, numbers, sources or prices.",
        "- In a normal chat, answer in plain language. If you're given a wave.task/1 JSON envelope, return the output "
        "shape your cards describe.",
        "- Work out numbers step by step and show them, so the user can check them.",
        "- You can't browse, run code, use files or schedule anything here. If the user needs that, say so.",
        "- Never ask for or repeat passwords, keys, recovery phrases or tokens.",
        "- For the official answer from Wave (with a receipt), the user can use \"Ask the real bot on Wave\" in the "
        "Wave | Bots tab.",
        "",
        "## Your knowledge cards (verified on Theta)",
    ]
    used = 0
    for k in bot.get("knowledge") or []:
        body = k["text"]
        if used + len(body) > MAX_KNOWLEDGE_BYTES:
            parts += ["", f"(More cards exist on Theta but were too long to include: from {k['ref']} on.)"]
            break
        used += len(body)
        parts += ["", f"### {k['title']} (card {k['ref']})", "", body]
    rules = bot.get("rules") or {}
    if rules:
        keep = {k: rules[k] for k in ("mode", "cascade", "awayMessage") if k in rules}
        parts += ["", "## Your rules (wave.rules/1, card " + str(bot.get("rules_ref")) + ")", "", "```json",
                  json.dumps(keep, indent=1, ensure_ascii=False), "```"]
    return "\n".join(parts).rstrip() + "\n"


def blocked_soul(bot_name: str, reason: str) -> str:
    """What an added bot becomes when it can no longer be verified: it refuses to answer."""
    return (f"# {bot_name}\n\nThis Wave bot couldn't be verified on the Theta blockchain, so it's paused.\n\n"
            f"Reason: {reason}\n\nFor every message, reply only: \"I'm paused because I couldn't be verified on Theta. "
            "Open the Wave | Bots tab and click Check again, or remove me.\" Don't answer anything else.\n")
