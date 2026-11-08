# Wave OS for Hermes

> Hermes puts your agent in any browser. Wave puts your agent's memory on any machine.

Bring **Wave OS** to [Hermes Agent](https://github.com/NousResearch/hermes-agent): memory you own on the Theta blockchain, which works on any install and with any AI.

Wave OS: [oswave.io](https://oswave.io) · Wave Web: [web.oswave.io](https://web.oswave.io) · Wave Wallet Mint: [oswave.io/wallet](https://oswave.io/wallet)

| Part | What it does | Status |
|---|---|---|
| [`brainvault/`](brainvault/) | **Wave | BrainVault Mint**, a Hermes memory provider. Hermes remembers locally right away. You mint memories to your own Wave vault on Theta (private ones encrypted to you), and any new install pairs once and reads them back. | v0.1.0 |
| Wave bots + Wave AI over MCP | Find, check and call Wave bots (Checker, Tally, CHIEF…) with the price in every answer, plus Wave AI on Theta EdgeCloud. See [below](#wave-os-tools-in-hermes-mcp). | Live, needs a Wave OS MCP token |
| `wave-ai/` | Wave AI as a Hermes model provider (run Hermes itself on Wave credits) | Planned |

## Quick start: Wave | BrainVault Mint

```bash
git clone https://github.com/xBuildyTeam/wave-os-hermes
cp -r wave-os-hermes/brainvault ~/.hermes/plugins/brainvault
hermes config set memory.provider brainvault
hermes brainvault wallet 0xYourWaveWallet
hermes brainvault pair        # approve in Wave Wallet Mint
hermes brainvault sync
```

Full guide and security model: [brainvault/README.md](brainvault/README.md).

**The ground rules:** the plugin never signs, never mints and never sees your wallet key. You mint in Wave Web and approve each card in Wave Wallet Mint. This Hermes install holds only a decrypt-only agent key that you can revoke in the wallet.

## Wave OS tools in Hermes (MCP)

Hermes speaks MCP natively, so it can use Wave OS, including **Wave bots**, without a plugin. Create a token at **app.oswave.io › Settings › MCP Setup** (keep the default safe scope), then add this to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  wave_os:
    url: https://wave-mcp-proxy-production.up.railway.app/mcp
    headers:
      Authorization: "Bearer ${env:WAVE_MCP_TOKEN}"
    tools:
      include: [bots_discover, bots_inspect, bots_call, theta_ai_chat, theta_generate_image, theta_get_credits]
```

Check it with `hermes mcp test wave_os`. If it says HTTP transport isn't available, install Hermes's `mcp` extra (for a source install, run `uv sync --extra mcp`).

### Wave bots: the Bot Store tools

| Tool | What it does |
|---|---|
| `bots_discover` | Find listed Wave bots by what you need ("check my math"). Every result shows its price for you, right now. |
| `bots_inspect` | Check a bot before using it: what it does, what it accepts, its on-chain verification and price. Private card text is never shown. |
| `bots_call` | Ask a bot a question, or hand it a `wave.task/1` step and get a `wave.task/1` result back, ready for the next bot. |

**Every answer, and every error, includes the price.** Public bots run on your own Wave credits (about 1 per answer) with no TFUEL charge. Each token has its own TFUEL spending limit, and it starts at **0**, so paid bots stay off until you raise it in MCP Setup. Bot answers come back flagged `untrusted: true`: they're data for Hermes to weigh, not instructions.

Example: Hermes asks `bots_call` with `{"bot": "checker.bots.theta", "question": "Rent 1800, Food 600, Car 450, Phone 120, Savings 750. Total 3920. Does it add up?"}`. Checker answers **FAIL: the items sum to 3,720**, charging 1 Wave credit and returning a receipt.

Official bots today include Checker, Tally, Planner, Scribe, Clerk, Critic, Risk, Reader, Maker, CHIEF and Wavey (`wave.theta`).

### Wave AI tools
`theta_ai_chat`, `theta_generate_image` and `theta_get_credits`, paid with your Wave credits on Theta EdgeCloud. Remove `tools.include` to see every safe-scope tool. The safe scope never includes tools that delete or deploy.

## License

MIT. Wave OS, Wave Web, Wave Wallet Mint and BrainVault are Wave OS products.
