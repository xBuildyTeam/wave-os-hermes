# Wave | BrainVault Mint: security review (0.6.1, November 8, 2026)

**Scans:** Bandit (Python), Semgrep (256 rules: Python, JavaScript, secrets), pip-audit (cryptography), a git-history secret search, and live probes of the plugin API in a real Hermes dashboard. All 32 plugin tests pass.

**Result:** no high or critical findings. Semgrep found nothing, pip-audit found no known vulnerabilities, and the only keys in git history are randomly generated test vectors (`tests/pv1_vectors.json`, made by `tests/make_vectors.mjs`).

## What holds up
- **Plugin API:** Hermes requires its session token on every `/api/plugins/brainvault/*` route and rejects foreign Host headers, so other websites can't read memories or change settings (probed: 401 without the token, 401 for a rebinding Host, no CORS for other origins).
- **Wallet key:** the plugin never holds it, signs or mints. The agent key is decrypt-only and revocable.
- **Send to Wave:** memories are AES-256-GCM encrypted with a fresh key. The key travels only in the link's `#fragment`, which browsers never send to the server. The drop is one-time and expires in 10 minutes.
- **Pairing:** the agent key arrives PV1-encrypted to a one-time key, is format-checked and must match the public key the wallet described.
- **Sync and Ask Wavey:** every card is read from Theta and checked (keccak fingerprint and creator; Wavey cards must be signed by Wave's official signer and match the text exactly). Recalled text is framed as notes, never as instructions.
- **Secrets:** seed phrases, private keys and API tokens are blocked before they're saved.
- **Page:** no raw HTML rendering; every link is built on the Wave Web address.

## Fixed in 0.6.1
1. **Send link no longer shown to the AI model** when the browser already opened it. The link holds the one-time decryption key, and tool results go to the model's provider.
2. **Wave Web address pinned** to `https://*.oswave.io`, whatever the config file says, so a tampered config can't send drops or pairing elsewhere.
3. **Input size limits** on every page API field (titles, tags, ids, wallet).
4. **Self-check uses an explicit error,** not `assert`, which Python can strip.

## Known limits (accepted)
- **Key file on Windows:** without `keyring` the agent key is a file in `%LOCALAPPDATA%\hermes\brainvault`, protected by your Windows account's folder permissions (Unix-style 0600 doesn't apply on Windows). Malware running as you could read it. It can only decrypt cards shared with this Hermes, and you can revoke it in Wave Wallet Mint. Installing `keyring` moves it to Windows Credential Manager.
- **Recall goes to your AI model:** recalled memories are sent to whichever model Hermes uses, so use a provider you trust with private memories.
- **Pairing link:** whoever has the link within 10 minutes could put a fake key, which only makes pairing fail. They can't get your key or cards.
