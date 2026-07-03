#!/bin/bash
# Karlz AI usage push: refresh usage.json from the plugin functions and ship it to
# gort's usage-api. Runs every ~60s via LaunchAgent com.karl.karlz-usage-push.
OUT=/tmp/karlz-usage.json
/usr/bin/python3 /Users/karl/Claude/ai-usage-bar/usage_json.py > "$OUT" 2>/dev/null
# only push if it parsed and has providers
if /usr/bin/python3 -c "import json,sys; d=json.load(open('$OUT')); sys.exit(0 if d.get('providers') else 1)" 2>/dev/null; then
  /usr/bin/scp -q -o ConnectTimeout=10 -o BatchMode=yes "$OUT" gort:.openclaw/workspace/apps/usage-api/usage.json
fi
