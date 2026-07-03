# AI Usage Bar

A macOS menu-bar tracker (SwiftBar plugin) showing live usage-vs-limit for **Claude**, **Codex**, **Featherless**, **Ollama Cloud**, and **z.ai** — so you can see how much quota is left before each resets.

Menu bar shows a compact summary:

```
C 6%   X 100%   O 18%   Z ok
```

`C` = Claude (5-hour window) · `X` = Codex (5-hour window) · `O` = Ollama (session window) · `Z` = z.ai API health. Click for a dropdown with each service's short + weekly windows, reset countdowns, and dashboard links.

If an auth-based service (Claude or Ollama) loses its connection, the bar collapses to **⚠️ Sign in** and the dropdown shows a one-tap reconnect link.

## How each tile gets its data

| Tile | Source | Notes |
|---|---|---|
| **Claude** | `anthropic-ratelimit-unified-*` **response headers** on a tiny `/v1/messages` call (cached ~4 min) | Needs an OAuth token from `claude setup-token` (only `user:inference` scope required). The dedicated `/api/oauth/usage` endpoint needs `user:profile`, which this client can't grant — the header route avoids that. |
| **Codex** | Latest populated `rate_limits` block in `~/.codex/sessions/**/*.jsonl` | No auth. Goes blank when Codex is routed to a local provider (Featherless/Ollama) — this is normal and does **not** trigger the sign-in state. |
| **Ollama Cloud** | Scrapes the logged-in `ollama.com/settings` HTML using your Chrome session cookie | No public usage API exists. Decrypts the `ollama.com` cookie from Chrome's cookie store (v10 / AES-128-CBC) via the "Chrome Safe Storage" keychain key. Stay logged into ollama.com in Chrome. |
| **Featherless** | Local proxy reachability + key presence | Flat subscription — no token quota to meter. Status + dashboard link only. |
| **z.ai** | Tiny Anthropic-compatible `GLM-5.2` probe against `https://api.z.ai/api/anthropic` | z.ai exposes documented Coding Plan limits, but no live used-percent API. The tile shows API/key health, probe token usage, and configured Lite/Pro/Max reference limits. |

## Requirements

- macOS, Python 3 (system `python3` is fine), `openssl` (system LibreSSL is fine)
- [SwiftBar](https://github.com/swiftbar/SwiftBar)
- Google Chrome logged into ollama.com (for the Ollama tile)
- A Claude subscription (for the Claude token)

## Install

One-shot installer (private repo, so clone with SSH or download a zip):

```sh
git clone git@github.com:karlwireless/Token-Usage-.git
cd Token-Usage-
./install.sh
```

The installer is idempotent (safe to re-run) and:

- installs SwiftBar to `/Applications` if not already present
- drops the plugin into `~/Library/Application Support/ai-usage-bar/plugins/`
- seeds `~/.config/ai-usage-bar/config.json` from the example (existing config preserved)
- installs a LaunchAgent so SwiftBar starts at login
- symlinks the Claude desktop app's bundled `claude` CLI to `~/.local/bin/claude` (if Claude Desktop is installed)
- launches SwiftBar

After it finishes, it prints two one-time auth steps:

1. **Claude token** — `~/.local/bin/claude setup-token`, then save the printed `sk-ant-oat01-…` to `~/.config/ai-usage-bar/claude-oauth.token` (`chmod 600`).
2. **Ollama** — stay logged into `ollama.com` in Google Chrome; first refresh will pop a one-time "Chrome Safe Storage" keychain prompt — click **Always Allow**.

Codex (X) and Featherless work automatically if those tools are installed.

### Uninstall

```sh
./uninstall.sh          # removes plugin, LaunchAgent, claude symlink (keeps config/tokens)
./uninstall.sh --purge  # also removes ~/.config/ai-usage-bar
```
SwiftBar itself is not removed; delete `/Applications/SwiftBar.app` manually if you want it gone.

## Security notes

- **No secrets are stored in this repo.** Tokens/keys live in local files (`*.token`, `*.key`) that are git-ignored.
- The Ollama tile reads and decrypts a Chrome cookie locally on your machine; nothing leaves your machine except the authenticated request to ollama.com itself.
- The Claude tile makes a 1-token API call every few minutes to read the rate-limit headers — negligible, but it does add a sliver to the usage it measures.
- The z.ai tile makes a cached 1-token `GLM-5.2` API probe at most every 30 minutes and reads the key from `~/.config/ai-usage-bar/zai.key` or `ZAI_API_KEY`.

## Caveats

- **Ollama** depends on staying logged into ollama.com in Chrome; the cookie can expire (~weeks) — open ollama.com once to refresh.
- **Ollama** is HTML scraping; if Ollama redesigns the settings page the parser may need a tweak.
- **z.ai** does not publish live remaining-quota percentages; the plugin shows health plus documented plan limits from `z_ai.plan` (`lite`, `pro`, or `max`).
- Built against SwiftBar 2.0.1; menu-bar ANSI color rendering is inconsistent across versions, so the title uses plain text.
