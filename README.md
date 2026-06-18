# AI Usage Bar

A macOS menu-bar tracker (SwiftBar plugin) showing live usage-vs-limit for **Claude**, **Codex**, **Featherless**, and **Ollama Cloud** — so you can see how much quota is left before each resets.

Menu bar shows a compact summary:

```
C 6%   X 100%   O 18%
```

`C` = Claude (5-hour window) · `X` = Codex (5-hour window) · `O` = Ollama (session window). Click for a dropdown with each service's short + weekly windows, reset countdowns, and dashboard links.

If an auth-based service (Claude or Ollama) loses its connection, the bar collapses to **⚠️ Sign in** and the dropdown shows a one-tap reconnect link.

## How each tile gets its data

| Tile | Source | Notes |
|---|---|---|
| **Claude** | `anthropic-ratelimit-unified-*` **response headers** on a tiny `/v1/messages` call (cached ~4 min) | Needs an OAuth token from `claude setup-token` (only `user:inference` scope required). The dedicated `/api/oauth/usage` endpoint needs `user:profile`, which this client can't grant — the header route avoids that. |
| **Codex** | Latest populated `rate_limits` block in `~/.codex/sessions/**/*.jsonl` | No auth. Goes blank when Codex is routed to a local provider (Featherless/Ollama) — this is normal and does **not** trigger the sign-in state. |
| **Ollama Cloud** | Scrapes the logged-in `ollama.com/settings` HTML using your Chrome session cookie | No public usage API exists. Decrypts the `ollama.com` cookie from Chrome's cookie store (v10 / AES-128-CBC) via the "Chrome Safe Storage" keychain key. Stay logged into ollama.com in Chrome. |
| **Featherless** | Local proxy reachability + key presence | Flat subscription — no token quota to meter. Status + dashboard link only. |

## Requirements

- macOS, Python 3 (system `python3` is fine), `openssl` (system LibreSSL is fine)
- [SwiftBar](https://github.com/swiftbar/SwiftBar)
- Google Chrome logged into ollama.com (for the Ollama tile)
- A Claude subscription (for the Claude token)

## Install

1. Install SwiftBar and point its **Plugin Folder** at a directory, e.g. `~/Library/Application Support/ai-usage-bar/plugins`.
2. Copy `aiusage.60s.py` into that folder and `chmod +x` it.
3. `mkdir -p ~/.config/ai-usage-bar && cp config.example.json ~/.config/ai-usage-bar/config.json`
4. **Claude token:** run `claude setup-token`, then save the `sk-ant-oat01-…` value to `~/.config/ai-usage-bar/claude-oauth.token` (`chmod 600`).
5. **Ollama:** just make sure Chrome is logged into ollama.com. First run will prompt once to allow the "Chrome Safe Storage" keychain item — click Always Allow.
6. Refresh: `open "swiftbar://refreshallplugins"`.

### Launch at login

SwiftBar can launch at login from its own menu, or use a LaunchAgent that runs `open -a SwiftBar` at load.

## Security notes

- **No secrets are stored in this repo.** Tokens/keys live in local files (`*.token`, `*.key`) that are git-ignored.
- The Ollama tile reads and decrypts a Chrome cookie locally on your machine; nothing leaves your machine except the authenticated request to ollama.com itself.
- The Claude tile makes a 1-token API call every few minutes to read the rate-limit headers — negligible, but it does add a sliver to the usage it measures.

## Caveats

- **Ollama** depends on staying logged into ollama.com in Chrome; the cookie can expire (~weeks) — open ollama.com once to refresh.
- **Ollama** is HTML scraping; if Ollama redesigns the settings page the parser may need a tweak.
- Built against SwiftBar 2.0.1; menu-bar ANSI color rendering is inconsistent across versions, so the title uses plain text.
