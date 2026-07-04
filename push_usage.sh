#!/bin/bash
# Karlz AI cookie push: ship the decrypted ollama.com session cookies to gort so
# gort's collectOllama() can hit ollama.com/settings itself. Runs every ~60s via
# LaunchAgent com.karl.karlz-usage-push.
#
# Note (2026-07-03): the old usage.json push was REMOVED. All four tiles are
# now collected server-side on gort (collectClaude/collectCodex/collectZai/
# collectOllama). The Mac no longer needs to push usage data — pushing it
# was overwriting gort's merged results and making /api/usage serve
# laptop-cache to the iOS app. Cookies are still pushed here so that
# collectOllama can hit ollama.com with a valid session.
CKOUT=/tmp/ollama-cookies.json
if /usr/bin/python3 /Users/karl/Claude/ai-usage-bar/push_ollama_cookies.py >/dev/null 2>&1; then
  /usr/bin/scp -q -o ConnectTimeout=10 -o BatchMode=yes "$CKOUT" gort:.config/ai-usage-bar/ollama-cookies.json
fi
