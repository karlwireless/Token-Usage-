# Gort side of AI Usage Bar

`usage-api-server.js` is the mirror of `gort:~/.openclaw/workspace/apps/usage-api/server.js`.

This is the always-on API that the Karlz AI iOS + watch app hits at
`https://gort.pitta-crested.ts.net:7811/api/usage`.

## What it does
- Serves the last-known merged usage snapshot to the iOS/watch app
- Refreshes every 60s from server-side collectors:
  - `collectClaude()` — hits Anthropic's `/v1/messages` with the OAuth token, reads
    `anthropic-ratelimit-unified-*` headers (always live, gort-independent-of-Mac)
  - `collectZai()` — z.ai's monitor endpoints with the API key (always live)
  - `collectCodex()` — SSHes to `coder` and reads Codex session `rate_limits`
    (always live if Codex Desktop runs on coder)
- Ollama tile currently comes from the Mac's `push_usage.sh` (laptop-cache).
  Phase 3 goal: `collectOllama()` on gort using a cookie set up by a one-time login.

## Deploy
- Edit `usage-api-server.js` here → `scp` to gort → restart the launchd job
  `com.openclaw.usage-api`.
- The gort file paths and TLS cert paths are hardcoded (see top of file).

## Secrets on gort (not in this repo)
- `~/.config/ai-usage-bar/claude-oauth.token` (chmod 600)
- `~/.config/ai-usage-bar/zai.key` (chmod 600)
- `~/.openclaw/workspace/gort.pitta-crested.ts.net.{key,crt}` (TLS)
