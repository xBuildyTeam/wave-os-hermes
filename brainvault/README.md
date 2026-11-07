# Wave OS BrainVault for Hermes

*Part of [Wave OS for Hermes](../README.md). Wave OS: [oswave.io](https://oswave.io) · Wave Web: [web.oswave.io](https://web.oswave.io)*

Portable, owner-held memory for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Hermes remembers on this install right away. When you want to keep those memories, you mint them to **your own** Wave vault on Theta. Private memories are encrypted to you, and nobody else can read them, not even Wave. Any new Hermes install pairs once with your wallet and gets its memories back from the chain.

- **The plugin never signs, never mints and never sees your wallet key.** Minting happens in Wave Web, and you approve each card in Wave Wallet Mint.
- **Pairing gives this install a decrypt-only agent key.** It can open only the cards you made readable by it, and you can revoke it in the wallet at any time.
- **Every card read from chain is fingerprint-checked** (keccak256 of the stored content).
- **Recalled memories are labelled as data, never instructions.** Text that looks like instructions is flagged as untrusted.
- **Keys, tokens, recovery phrases and keystores are refused at capture.** They are never stored, exported or minted.

## Install

```bash
git clone https://github.com/xBuildyTeam/wave-os-hermes
cp -r wave-os-hermes/brainvault ~/.hermes/plugins/brainvault   # or $HERMES_HOME/plugins/
hermes config set memory.provider brainvault
hermes memory status                              # brainvault ← active
```

**Windows (PowerShell):** Hermes keeps its files in `%LOCALAPPDATA%\hermes`, not `~/.hermes`, so copy the plugin there:

```powershell
git clone https://github.com/xBuildyTeam/wave-os-hermes
New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\hermes\plugins" | Out-Null
Copy-Item -Recurse -Force wave-os-hermes\brainvault "$env:LOCALAPPDATA\hermes\plugins\brainvault"
hermes config set memory.provider brainvault
hermes memory status
```

Not sure where your Hermes lives? `hermes config set` prints the path of its config.yaml, and the plugins folder sits next to it.

There are no extra Python packages to install: it uses `cryptography` (already a Hermes dependency) and the standard library. If `keyring` is installed, the agent key goes in your OS keychain. Otherwise it goes in a `0600` file.

## Use

| | |
|---|---|
| `hermes brainvault wallet 0x…` | Your Wave Wallet Mint address (to find your vault cards) |
| `hermes brainvault pair` | Opens Wave Web › Pair Hermes. Approve in Wave Wallet Mint and the agent key arrives end-to-end encrypted. |
| `hermes brainvault sync` | Read new cards from your vault (also runs in the background every 10 min) |
| `hermes brainvault export` | Write new memories to a Wave migration file and open Wave Web to review and mint them |
| `hermes brainvault search …`, `list`, `forget <id>`, `status`, `unpair` | |

Tools the agent gets: `brainvault_recall`, `brainvault_remember`, `brainvault_forget`, `brainvault_status`, `brainvault_send_to_wave`. Hermes's built-in memory writes (MEMORY.md / USER.md) are mirrored automatically, with provenance (operator, agent or external trust, session, date). Only the primary agent writes; subagents and cron runs can recall but never save.

## How the memory loop works

1. **Capture.** Facts and preferences go into a local store (`$HERMES_HOME/brainvault/brainvault.db`). Recall is instant, and nothing leaves your machine.
2. **Mint.** `export` builds a pack (`{"cards":[{title, tags, body, source}]}`, private by default). In Wave Web, choose New migration › Paste, then review and Publish. Wave Wallet Mint encrypts private cards (PV1) and signs. Choose "Readable by: Me + Hermes" so your agent can open them.
3. **Recall anywhere.** On a new install, run `pair` and then `sync`. The plugin finds your cards through Wave Web's public index, reads each one from Theta, checks its fingerprint, and opens the private ones with its agent key.

## Tests

```bash
python3 -m pytest brainvault/tests -q            # offline
BV_LIVE=1 python3 -m pytest brainvault/tests -q  # + Theta mainnet and Wave Web
```

The PV1 test vectors are made by Wave Wallet Mint's own code, so Python and the wallet stay byte-for-byte compatible.
