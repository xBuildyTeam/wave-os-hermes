# Wave | Bots for Hermes

Verified AI bots from the bots.theta store, checked on the Theta blockchain **on your computer**, and added to Hermes as real Hermes bots.

- **Store tab** (Hermes Desktop, Webapp and `hermes dashboard`): the 10 official Wave bots with their mascots, each one marked "Verified on Theta" only after this plugin re-checks it: name → listing → rules → mascot → every knowledge card fingerprint.
- **Add to Hermes**: the bot becomes its own bot in your sidebar's Bots list (a Hermes profile `wave-<name>`), with its mascot as the avatar. It runs on **your own AI model and login**, answers from its verified cards and cites them. Its terminal, files, browser, code, web, memory, delegation and scheduled-job tools are off, and MCP servers are off.
- **Stays honest**: re-checked on Theta once a day. A newer listing shows "Update available"; a failed check pauses the bot until it passes again; local edits to its SOUL.md are flagged.
- **No account, key or token** needed for any of this. Nothing is signed, paid or sent to Wave.
- **Optional: Connect to Wave OS** (Connection tab, `/bots connect` or `hermes wavebots connect`). One click on app.oswave.io gives Hermes a limited key: you pick the spending limit (default 0 = free and public bots only) and how long it lasts (30/90/365 days). The key is sealed to a one-time key on your computer and read once, so it never shows on screen, in a link or in a log. It's kept in your system keychain (or a 0600 file). It can only ask Wave bots, nothing else. Revoke it in Wave OS Settings › MCP Setup.
- **Ask the real bot on Wave**: on a bot's page, `/bots ask checker <question>`, or the `ask_wave` tool action (Hermes asks you to approve each one, and shows the TFUEL if a price is allowed). The answer comes back with the listing, cited cards, price and a receipt, and is treated as data, never instructions.

## Use it

| Where | How |
|---|---|
| Tab | Wave \| Bots in the sidebar (Store / Added / Connection) |
| Chat | `/bots`, `/bots find check my numbers`, `/bots info tally`, `/bots add tally`, `/bots check`, `/bots update tally`, `/bots remove tally yes` |
| CLI | `hermes wavebots list`, `hermes wavebots add tally`, `hermes wavebots check`, `hermes wavebots remove tally --yes` |
| Agent | the `wave_bots` tool (find, info, list_added, add, check, update, remove, connection, ask_wave). Add, update, remove and ask_wave go through Hermes's approval prompt and never run from scheduled jobs. |
| CLI (Wave OS) | `hermes wavebots connect`, `hermes wavebots status`, `hermes wavebots ask checker "…"`, `hermes wavebots disconnect` |
| Links | `hermes://open/wavebots?bot=checker` opens a bot's page; `hermes://open/wavebots?connected=1` opens Connection |

## How a bot is checked

1. `name.bots.theta` → the TNS registry (`0xffc4…e787`) → its resolver → the `wave.bot` text record = the listing ref.
2. The listing card (`wave.bot-listing/1`) is read from BrainVault v3 (`0xdb82…dc90`): `keccak256(content)` must equal both the logged and the stored content hash, and the listing must name itself.
3. The rules card's sha256 must equal the listing's `rulesHash`, signed by the same creator. The mascot and every knowledge card are hash-checked the same way.
4. "Official" = signed by Wave's official signer `0x4e96…86db`; anything else shows "Community".

A network failure shows "Couldn't reach Theta" and never counts as a failed check.

## Tests

`python -m pytest wavebots/tests -q`: 28 offline tests on recorded mainnet responses (tampered listing, tampered knowledge card, an older listing, offline, add / re-add / foreign profile / failed add rollback, check / edited / update / pause and recover, remove, approvals, cron refusal, the dashboard API, Connect: link, one-time take, wrong key, full-scope refused, polling, ask, revoke, disconnect).

Edit the UI in `ui/app.js` + `ui/style.css`, then `python3 ui/build.py`.
