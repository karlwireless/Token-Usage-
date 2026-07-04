#!/usr/bin/env python3
"""Ships the two ollama.com session cookies (aid, __Secure-session) from Mac to
gort so that gort's usage-api can hit ollama.com/settings itself for the live
Session/Weekly percentages. Cookies are decrypted from Chrome's cookie store
using the plugin's existing helper. Writes /tmp/ollama-cookies.json (chmod 600)."""
import runpy, os, json, sys, time

PLUGIN = os.path.expanduser("~/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py")
OUT = "/tmp/ollama-cookies.json"

try:
    M = runpy.run_path(PLUGIN)
    ck = M["_chrome_ollama_cookies"]()
except Exception as e:
    print(f"cookie decrypt failed: {e}", file=sys.stderr)
    sys.exit(1)

if not ck.get("aid") or not ck.get("__Secure-session"):
    print("missing required cookies (aid, __Secure-session)", file=sys.stderr)
    sys.exit(1)

blob = {
    "aid": ck["aid"],
    "session": ck["__Secure-session"],
    "capturedAt": int(time.time()),
    "source": "mac-chrome-decrypt",
}
tmp = OUT + ".tmp"
with open(tmp, "w") as f:
    json.dump(blob, f)
os.chmod(tmp, 0o600)
os.replace(tmp, OUT)
print(f"ok: wrote {OUT} ({os.path.getsize(OUT)} bytes)")
