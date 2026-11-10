# Wave | Bots for Hermes

Verified AI bots from the bots.theta store, checked on the Theta blockchain **on your computer**, and added to Hermes as real Hermes bots.

- **Store tab** (Hermes Desktop, Webapp and `hermes dashboard`): the 10 official Wave bots with their mascots, each one marked "Verified on Theta" only after this plugin re-checks it: name → listing → rules → mascot → every knowledge card fingerprint.
- **Add to Hermes**: the bot becomes its own bot in your sidebar's Bots list (a Hermes profile `wave-<name>`), with its mascot as the avatar. It runs on **your own AI model and login**, answers from its verified cards and cites them. Its terminal, files, browser, code, web, memory, delegation and scheduled-job tools are off, and MCP servers are off.
- **Stays honest**: re-checked on Theta once a day. A newer listing shows "Update available"; a failed check pauses the bot until it passes again; local edits to its SOUL.md are flagged.
- **No account, key or token** needed for any of this. Nothing is signed, paid or sent to Wave. Paid and private bots, and "Ask the real bot on Wave", come with one-click Connect to Wave OS in the next version.

## Use it

| Where | How |
|---|---|
| Tab | Wave \| Bots in the sidebar (Store / Added / Connection) |
| Chat | `/bots`, `/bots find check my numbers`, `/bots info tally`, `/bots add tally`, `/bots check`, `/bots update tally`, `/bots remove tally yes` |
| CLI | `hermes wavebots list`, `hermes wavebots add tally`, `hermes wavebots check`, `hermes wavebots remove tally --yes` |
| Agent | the `wave_bots` tool (find, info, list_added, add, check, update, remove). Add, update and remove go through Hermes's approval prompt and never run from scheduled jobs. |
| Links | `hermes://open/wavebots?bot=checker` opens a bot's page |

## How a bot is checked

1. `name.bots.theta` → the TNS registry (`0xffc4…e787`) → its resolver → the `wave.bot` text record = the listing ref.
2. The listing card (`wave.bot-listing/1`) is read from BrainVault v3 (`0xdb82…dc90`): `keccak256(content)` must equal both the logged and the stored content hash, and the listing must name itself.
3. The rules card's sha256 must equal the listing's `rulesHash`, signed by the same creator. The mascot and every knowledge card are hash-checked the same way.
4. "Official" = signed by Wave's official signer `0x4e96…86db`; anything else shows "Community".

A network failure shows "Couldn't reach Theta" and never counts as a failed check.

## Tests

`python -m pytest wavebots/tests -q`: 23 offline tests on recorded mainnet responses (tampered listing, tampered knowledge card, an older listing, offline, add / re-add / foreign profile / failed add rollback, check / edited / update / pause and recover, remove, approvals, cron refusal, the dashboard API).

Edit the UI in `ui/app.js` + `ui/style.css`, then `python3 ui/build.py`.
