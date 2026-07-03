# AI Usage Bar Handoff

This file is for another AI or engineer setting up Karl's AI Usage Bar on another device.

The project is a macOS SwiftBar menu-bar plugin that shows live usage for Claude, Codex, Ollama Cloud, z.ai, and Featherless. It is designed for Karl's Tailscale fleet, but the menu-bar UI itself requires macOS because it runs under SwiftBar.

Current source of truth:

- GitHub: `karlwireless/Token-Usage-`
- Working source on Karl's active Mac: `/Users/karl/Claude/ai-usage-bar`
- Live SwiftBar plugin path: `/Users/karl/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py`
- Runtime config path: `/Users/karl/.config/ai-usage-bar/config.json`
- OpenClaw skill on Gort: `/Users/gort/.openclaw/workspace/skills/ai-usage-bar/SKILL.md`

Do not commit secrets. Tokens and API keys live only in local config/key files.

## What The Bar Shows

Menu-bar title example:

```text
C 28%  X 8%  O 0.5%  Z 1%
```

Meaning:

- `C`: Claude 5-hour unified usage percentage.
- `X`: Codex 5-hour usage percentage.
- `O`: Ollama Cloud session usage percentage.
- `Z`: z.ai Coding Plan 5-hour token usage percentage.

Clicking the SwiftBar item opens a dropdown with reset times, weekly windows, and provider-specific details.

## Device Requirements

For the full menu-bar experience:

- macOS.
- Tailscale connected to Karl's fleet.
- Python 3.
- `openssl`.
- SwiftBar.
- Google Chrome, logged into `ollama.com`, for the Ollama Cloud tile.
- Claude Desktop or another `claude` CLI capable of `claude setup-token`, for the Claude tile.
- Local API/key files for Claude and z.ai.

For a non-macOS device:

- The Python plugin can be run manually as a CLI status printer, but SwiftBar is macOS-only. Do not present it as a finished Linux/Raspberry Pi menu-bar install without replacing the UI layer.

## Tailscale / Fleet Notes

The target device being on Tailscale helps with moving files and asking Gort for context.

At the start of any fleet session, read Karl's rules and fleet map:

```sh
ssh gort "cat ~/.openclaw/CODING.md ~/.openclaw/bootstrap.md"
```

If direct `ssh gort` fails, follow Karl's normal onboarding/bootstrap instructions. Gort is the hub and already has access to the rest of the fleet.

Do not copy secrets by printing them into chat. If a secret must move from one trusted Tailscale Mac to another, use `scp` or paste it locally into the target file with correct permissions.

## Installation Path

Preferred path if GitHub access/deploy key is already available on the target Mac:

```sh
git clone git@github.com:karlwireless/Token-Usage-.git
cd Token-Usage-
./install.sh
```

Alternate path if the target Mac does not have GitHub access but can SSH to a Tailscale node that already has the repo:

```sh
mkdir -p ~/Claude
scp -r <source-node>:/Users/karl/Claude/ai-usage-bar ~/Claude/
cd ~/Claude/ai-usage-bar
./install.sh
```

Adjust `<source-node>` and usernames to the actual Tailscale host. If using Gort as a hop, use the fleet map in `bootstrap.md`.

The installer:

- Installs SwiftBar if missing.
- Copies `aiusage.60s.py` into `~/Library/Application Support/ai-usage-bar/plugins/`.
- Creates `~/.config/ai-usage-bar/config.json` from `config.example.json` if no config exists.
- Sets SwiftBar's plugin directory.
- Installs a LaunchAgent for login startup.
- Starts SwiftBar and refreshes plugins.

## Required Secret Files

Create the config directory:

```sh
mkdir -p ~/.config/ai-usage-bar
chmod 700 ~/.config/ai-usage-bar
```

### Claude

File:

```text
~/.config/ai-usage-bar/claude-oauth.token
```

How to create:

```sh
~/.local/bin/claude setup-token
```

Follow the browser login flow, copy the printed `sk-ant-oat01-...` token, then save it:

```sh
printf '%s\n' 'PASTE_TOKEN_HERE' > ~/.config/ai-usage-bar/claude-oauth.token
chmod 600 ~/.config/ai-usage-bar/claude-oauth.token
```

Do not commit or print this token.

### z.ai

File:

```text
~/.config/ai-usage-bar/zai.key
```

The key is a z.ai API key. It can also be supplied by environment variable `ZAI_API_KEY`, but the file is preferred for SwiftBar because SwiftBar launch environments are sparse.

Save it:

```sh
printf '%s\n' 'PASTE_ZAI_KEY_HERE' > ~/.config/ai-usage-bar/zai.key
chmod 600 ~/.config/ai-usage-bar/zai.key
```

Do not commit or print this key.

### Ollama Cloud

No local API key is used for live usage. The plugin decrypts Chrome's logged-in `ollama.com` cookies locally.

On the target Mac:

1. Open Google Chrome.
2. Log into `https://ollama.com/settings`.
3. Keep Chrome logged in.
4. On the first SwiftBar refresh, macOS may ask for access to `Chrome Safe Storage`; choose `Always Allow`.

### Codex

No token is needed by this plugin. It reads local Codex session JSONL files:

```text
~/.codex/sessions/**/*.jsonl
~/.codex/archived_sessions/*.jsonl
```

It chooses the newest populated `rate_limits` event by event timestamp, not merely the newest file. This matters because active session files can contain stale startup `0%` blocks before later nonzero usage.

### Featherless

No usage quota API is available. The plugin shows local proxy status, key presence, and current Codex model when possible.

Expected key path:

```text
~/.codex/featherless.key
```

Expected local proxy:

```text
127.0.0.1:18086
```

## Provider Data Sources

### Claude

The plugin makes a tiny cached `/v1/messages` call and reads Anthropic unified rate-limit headers:

- `anthropic-ratelimit-unified-5h-utilization`
- `anthropic-ratelimit-unified-5h-reset`
- `anthropic-ratelimit-unified-7d-utilization`
- `anthropic-ratelimit-unified-7d-reset`

The token needs `user:inference`. Do not use the deprecated/sensitive profile endpoint path here.

### Codex

Reads local Codex session files and finds the newest populated `rate_limits` object:

- `primary.used_percent`: 5-hour usage.
- `primary.resets_at`: 5-hour reset.
- `secondary.used_percent`: weekly usage.
- `secondary.resets_at`: weekly reset.
- `plan_type`: plan label.

If Codex is routed to a local provider and no OpenAI rate-limit data exists, the Codex tile may be blank or stale. That is not an auth failure.

### Ollama Cloud

Scrapes the logged-in HTML from:

```text
https://ollama.com/settings
```

It parses:

- `Session usage ... % used`
- `Weekly usage ... % used`
- reset strings in the order `[session, weekly]`
- optional balance remaining

The plugin decrypts Chrome cookies from:

```text
~/Library/Application Support/Google/Chrome/Default/Cookies
```

Cookie decryption uses the macOS Keychain item `Chrome Safe Storage` and the system `openssl` command.

### z.ai

The z.ai tile uses official GLM Coding Plan monitor endpoints discovered from the official `zai-org/zai-coding-plugins` `glm-plan-usage` plugin.

Base domain:

```text
https://api.z.ai
```

Endpoints:

```text
/api/monitor/usage/model-usage
/api/monitor/usage/tool-usage
/api/monitor/usage/quota/limit
```

Auth header:

```text
Authorization: <z.ai API key>
```

The plugin shows:

- live plan level, for example `PRO`;
- 5-hour token percentage and reset;
- weekly token percentage and reset;
- monthly MCP percentage, used, remaining, and reset;
- last 24-hour model calls and token usage;
- last 24-hour tool usage for search/web-read/zread.

It also performs a tiny Anthropic-compatible health probe against:

```text
https://api.z.ai/api/anthropic/v1/messages
```

That probe confirms API/key health and returns per-request usage. It is not the primary quota source.

## Config

Main config:

```text
~/.config/ai-usage-bar/config.json
```

Example:

```json
{
  "claude": {
    "oauth_token": "",
    "label": "Max 20x"
  },
  "featherless": {
    "dashboard_url": "https://featherless.ai/account",
    "proxy_url": "http://127.0.0.1:18086/v1/models"
  },
  "ollama_cloud": {
    "dashboard_url": "https://ollama.com/settings",
    "local_url": "http://127.0.0.1:11434/api/tags"
  },
  "z_ai": {
    "dashboard_url": "https://z.ai/manage-apikey/rate-limits",
    "base_url": "https://api.z.ai/api/anthropic",
    "model": "GLM-5.2",
    "plan": "pro",
    "key_path": "~/.config/ai-usage-bar/zai.key"
  },
  "display": {
    "warn_percent": 50,
    "crit_percent": 80,
    "ok_color": "#00E000",
    "warn_color": "#FF8C00",
    "crit_color": "#FF2A2A",
    "none_color": "#AAAAAA"
  }
}
```

The z.ai `plan` value is only a fallback. If the monitor endpoint works, live z.ai account level overrides it.

## Verify The Install

Run the live plugin directly:

```sh
python3 "$HOME/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py"
```

Expected first line resembles:

```text
C 28%  X 8%  O 0.5%  Z 1%
```

Force SwiftBar to refresh:

```sh
open "swiftbar://refreshallplugins"
```

Confirm SwiftBar is configured to the right plugin folder:

```sh
defaults read com.ameba.SwiftBar PluginDirectory
```

Expected:

```text
/Users/<user>/Library/Application Support/ai-usage-bar/plugins
```

Confirm SwiftBar is running:

```sh
pgrep -af SwiftBar
```

## Common Failures

### Menu bar says `Sign in`

Only Claude and Ollama can trigger the global sign-in warning.

For Claude:

- token missing or expired;
- regenerate with `~/.local/bin/claude setup-token`;
- save to `~/.config/ai-usage-bar/claude-oauth.token`;
- `chmod 600` the file.

For Ollama:

- Chrome is not logged into `ollama.com`;
- cookie expired;
- macOS Keychain denied `Chrome Safe Storage`;
- log into `https://ollama.com/settings` in Chrome and refresh SwiftBar.

### `X 0%` when Codex is clearly not zero

Check that the deployed plugin is current. Old code selected the first rate-limit block from the newest modified file and could land on stale startup `0%`.

Current code scans recent session files and chooses the newest populated rate-limit event by event timestamp.

Run:

```sh
python3 "$HOME/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py" | sed -n '1,25p'
```

If source is updated but live plugin is not, redeploy:

```sh
install -m 755 ./aiusage.60s.py "$HOME/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py"
open "swiftbar://refreshallplugins"
```

### Ollama shows `0%`

Current code preserves small nonzero values, for example `0.2%`. If it shows exactly `0%`, the Ollama dashboard is probably returning exactly `0`, not a rounding bug.

Debug:

```sh
python3 - <<'PY'
import runpy
m = runpy.run_path('/Users/karl/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py')
print(m['_ollama_cloud_usage']())
PY
```

Adjust the path for the target user if needed.

### z.ai shows plan name instead of percent

That means the monitor endpoint failed but the API health probe worked. Check:

- `~/.config/ai-usage-bar/zai.key` exists and is correct;
- `chmod 600 ~/.config/ai-usage-bar/zai.key`;
- target can reach `https://api.z.ai`;
- `z_ai.base_url` is `https://api.z.ai/api/anthropic`.

Debug without printing the key:

```sh
python3 - <<'PY'
import runpy
m = runpy.run_path('/Users/karl/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py')
z = m['get_zai']()
print({k: z.get(k) for k in ('ok', 'key', 'plan', 'err', 'monitor_err')})
print((z.get('monitor') or {}).get('level'))
print((z.get('monitor') or {}).get('token_5h'))
PY
```

### SwiftBar installed but no icon appears

Run:

```sh
defaults write com.ameba.SwiftBar "NSStatusItem VisibleCC Item-1" -bool true
open -a /Applications/SwiftBar.app
open "swiftbar://refreshallplugins"
```

Also check macOS menu-bar overflow/notch behavior.

## Updating Existing Installs

On a target Mac with an existing install:

```sh
cd ~/Claude/ai-usage-bar
git pull
install -m 755 ./aiusage.60s.py "$HOME/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py"
open "swiftbar://refreshallplugins"
```

Do not overwrite `~/.config/ai-usage-bar/config.json` unless intentionally changing local settings.

## What To Update In OpenClaw

If this is installed on a new recurring-use Mac, update OpenClaw on Gort:

- `~/.openclaw/MEMORY.md` active project line if runtime locations change.
- `~/.openclaw/workspace/skills/ai-usage-bar/SKILL.md` with the new runtime host/path.
- today's journal: `~/.openclaw/memory/YYYY-MM-DD.md`.

Suggested journal line:

```text
HH:MM — Installed AI Usage Bar on <host>: SwiftBar plugin at ~/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py, config at ~/.config/ai-usage-bar/config.json, source from karlwireless/Token-Usage-.
```

## Security Rules

- Never commit `*.token`, `*.key`, real `config.json`, Chrome cookies, or copied Keychain material.
- Do not paste API keys or OAuth tokens into chat logs.
- Use Tailscale SSH/SCP for file movement when possible.
- Keep secret files mode `600`; config directory mode `700` is preferred.
- If a command prints a secret by mistake, stop and tell Karl.

## Current Known-Good Behavior

As of the last verified install on Karl's active Mac:

```text
C 28%  X 8%  O 0.5%  Z 1%
```

z.ai monitor data showed:

- plan level `PRO`;
- 5-hour token usage `1%`;
- weekly token usage `1%`;
- monthly MCP usage `0%`;
- MCP remaining `1,000`;
- last 24h model calls/tokens `0 / 0`.

These numbers are expected to change over time; use them only as a shape check.
