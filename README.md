# Wave OS for Hermes

Bring **Wave OS** to [Hermes Agent](https://github.com/NousResearch/hermes-agent): memory you own on the Theta blockchain, which works on any install and with any AI.

Wave OS: [oswave.io](https://oswave.io) · Wave Web: [web.oswave.io](https://web.oswave.io) · Wave Wallet Mint: [oswave.io/wallet](https://oswave.io/wallet)

| Part | What it does | Status |
|---|---|---|
| [`brainvault/`](brainvault/) | **Wave OS BrainVault**, a Hermes memory provider. Hermes remembers locally right away. You mint memories to your own Wave vault on Theta (private ones encrypted to you), and any new install pairs once and reads them back. | v0.1.0 |
| Wave OS tools over MCP | Wave AI on Theta EdgeCloud (chat, images, credits) and Wave OS memory, as Hermes tools. See [below](#wave-os-tools-in-hermes-mcp). | Works with a Wave OS MCP token |
| `wave-ai/` | Wave AI as a Hermes model provider (run Hermes itself on Wave credits) | Planned |

## Quick start: Wave OS BrainVault

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

Hermes speaks MCP natively, so it can connect to Wave OS without a plugin. Create a token at **app.oswave.io › Settings › MCP Setup** (keep the default safe scope), then add this to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  wave-os:
    url: https://wave-mcp.up.railway.app/mcp
    headers:
      Authorization: "Bearer ${env:WAVE_MCP_TOKEN}"
```

You get tools such as `theta_ai_chat`, `theta_generate_image` and `theta_get_credits` (paid with your Wave credits on Theta EdgeCloud), plus `wave_recall_memory` and `wave_save_memory`. The safe scope hides tools that delete or deploy.

## License

MIT. Wave OS, Wave Web, Wave Wallet Mint and BrainVault are Wave OS products.
