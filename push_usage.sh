#!/bin/bash
# Karlz AI usage push: refresh usage.json from the plugin functions and ship it to
# gort's usage-api. Also ships the decrypted ollama.com session cookies so gort's
# collectOllama() can hit ollama.com/settings itself when the Mac is offline.
# Runs every ~60s via LaunchAgent com.karl.karlz-usage-push.
OUT=/tmp/karlz-usage.json
CKOUT=/tmp/ollama-cookies.json

/usr/bin/python3 /Users/karl/Claude/ai-usage-bar/usage_json.py > "$OUT" 2>/dev/null
if /usr/bin/python3 -c "import json,sys; d=json.load(open('$OUT')); sys.exit(0 if d.get('providers') else 1)" 2>/dev/null; then
  /usr/bin/scp -q -o ConnectTimeout=10 -o BatchMode=yes "$OUT" gort:.openclaw/workspace/apps/usage-api/usage.json
fi

# Extract + ship Ollama cookies for gort's collectOllama()
if /usr/bin/python3 /Users/karl/Claude/ai-usage-bar/push_ollama_cookies.py >/dev/null 2>&1; then
  /usr/bin/scp -q -o ConnectTimeout=10 -o BatchMode=yes "$CKOUT" gort:.config/ai-usage-bar/ollama-cookies.json
fi
