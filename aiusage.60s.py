#!/usr/bin/env python3
# <xbar.title>AI Usage</xbar.title>
# <xbar.version>1.0</xbar.version>
# <xbar.author>Claude Code</xbar.author>
# <xbar.desc>Live usage-vs-limit for Claude, Codex, Featherless and Ollama Cloud.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
"""
AI Usage menu-bar plugin (SwiftBar).

Data sources (see the per-tile functions for the gory details):
  Claude        -> GET api.anthropic.com/api/oauth/usage  (needs OAuth token in config)
                   fallback: token throughput summed from ~/.claude transcripts
  Codex         -> latest populated rate_limits block in ~/.codex/sessions/**.jsonl
  Featherless   -> local proxy reachability + key (no usage API exists; flat plan)
  Ollama Cloud  -> local server reachability + cloud models (real limits at dashboard)
"""
import json, os, glob, time, re, urllib.request, urllib.error, socket
from datetime import datetime

HOME = os.path.expanduser("~")
CFG_PATH = os.path.join(HOME, ".config", "ai-usage-bar", "config.json")

# ----------------------------------------------------------------------------- config
def load_cfg():
    try:
        with open(CFG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

CFG = load_cfg()
DISP = CFG.get("display", {})
WARN = DISP.get("warn_percent", 50)
CRIT = DISP.get("crit_percent", 80)
# Bright, colorblind-friendly palette (editable in config.json -> display)
OK_COLOR   = DISP.get("ok_color",   "#00E000")  # bright green
WARN_COLOR = DISP.get("warn_color", "#FF8C00")  # bright amber/brown
CRIT_COLOR = DISP.get("crit_color", "#FF2A2A")  # bright red
NONE_COLOR = DISP.get("none_color", "#AAAAAA")

# ----------------------------------------------------------------------------- helpers
def color_for(pct):
    if pct is None:
        return NONE_COLOR
    if pct >= CRIT:
        return CRIT_COLOR
    if pct >= WARN:
        return WARN_COLOR
    return OK_COLOR

def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def ansi_color(text, hexc):
    """Wrap text in a 24-bit ANSI truecolor code (SwiftBar renders this with ansi=true)."""
    r, g, b = _hex_rgb(hexc)
    return f"\033[1m\033[38;2;{r};{g};{b}m{text}\033[0m"

def bar(pct, width=10):
    if pct is None:
        return "—"
    filled = int(round(min(max(pct, 0), 100) / 100 * width))
    return "█" * filled + "░" * (width - filled)

def to_epoch(v):
    """Accept unix seconds (int/float/str) or ISO-8601 string -> epoch seconds."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    try:
        return float(s)
    except ValueError:
        pass
    try:
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2).timestamp()
    except Exception:
        return None

def fmt_reset(epoch):
    if epoch is None:
        return "reset time unknown"
    delta = epoch - time.time()
    if delta <= 0:
        return "resets momentarily"
    mins = int(delta // 60)
    if mins < 60:
        return f"resets in {mins}m"
    hours = mins // 60
    rem = mins % 60
    if hours < 24:
        return f"resets in {hours}h{rem:02d}m"
    days = hours // 24
    hrem = hours % 24
    return f"resets in {days}d{hrem}h"

def as_percent(v):
    """Normalize a usage value to 0-100. Fractions (<=1) become percents."""
    if v is None:
        return None
    try:
        v = float(v)
    except Exception:
        return None
    if 0 <= v <= 1:
        return v * 100.0
    return v

def port_open(host, port, timeout=0.6):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

# ----------------------------------------------------------------------------- Codex
def get_codex():
    """Most recent populated rate_limits block across all Codex sessions."""
    out = {"ok": False, "plan": None, "p5h": None, "p5h_reset": None,
           "pwk": None, "pwk_reset": None, "note": None}

    def find_rl(o):
        if isinstance(o, dict):
            rl = o.get("rate_limits")
            if isinstance(rl, dict):
                return rl
            for v in o.values():
                r = find_rl(v)
                if r is not None:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = find_rl(v)
                if r is not None:
                    return r
        return None

    files = glob.glob(os.path.join(HOME, ".codex", "sessions", "**", "*.jsonl"), recursive=True)
    files += glob.glob(os.path.join(HOME, ".codex", "archived_sessions", "*.jsonl"))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    best = None
    best_mtime = -1
    # newest file first; stop once we find a populated block in a recent file
    for fp in files[:40]:
        try:
            mt = os.path.getmtime(fp)
            with open(fp, errors="ignore") as f:
                for line in f:
                    if "rate_limits" not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    rl = find_rl(o)
                    if rl and (rl.get("primary") or rl.get("secondary")):
                        if mt > best_mtime:
                            best = rl
                            best_mtime = mt
        except Exception:
            continue
        if best is not None:
            break

    if best is None:
        out["note"] = "No live limit data yet (Codex currently routed to a local provider)."
        return out

    out["ok"] = True
    out["plan"] = best.get("plan_type")
    pr = best.get("primary") or {}
    sc = best.get("secondary") or {}
    # Codex's used_percent is already a 0-100 percentage — do NOT pass through
    # as_percent() (which would treat values <=1 as a 0..1 fraction and 100x them).
    def _num(v):
        try: return float(v)
        except (TypeError, ValueError): return None
    out["p5h"] = _num(pr.get("used_percent"))
    out["p5h_reset"] = to_epoch(pr.get("resets_at"))
    out["pwk"] = _num(sc.get("used_percent"))
    out["pwk_reset"] = to_epoch(sc.get("resets_at"))
    out["age_min"] = int((time.time() - best_mtime) / 60)
    return out

# ----------------------------------------------------------------------------- Claude
CLAUDE_CACHE = "/tmp/ai_usage_claude.json"

def _read_claude_token():
    p = os.path.join(HOME, ".config", "ai-usage-bar", "claude-oauth.token")
    if os.path.exists(p):
        t = open(p).read().strip()
        if t:
            return t
    return (CFG.get("claude", {}) or {}).get("oauth_token", "").strip()

def _claude_from_headers(token):
    """5h + weekly utilization come back as response headers on any messages call."""
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=b'{"model":"claude-haiku-4-5-20251001","max_tokens":1,"messages":[{"role":"user","content":"."}]}',
        headers={"Authorization": "Bearer " + token, "anthropic-beta": "oauth-2025-04-20",
                 "anthropic-version": "2023-06-01", "content-type": "application/json",
                 "User-Agent": "ai-usage-bar/1.0"})
    try:
        h = urllib.request.urlopen(req, timeout=15).headers
    except urllib.error.HTTPError as e:
        if e.code == 429:      # over the limit, but the headers are still there
            h = e.headers
        else:
            raise
    def num(name):
        v = h.get(name)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    def pct(name):
        v = num(name)
        return v * 100 if v is not None else None
    return {
        "p5h": pct("anthropic-ratelimit-unified-5h-utilization"),
        "p5h_reset": num("anthropic-ratelimit-unified-5h-reset"),
        "pwk": pct("anthropic-ratelimit-unified-7d-utilization"),
        "pwk_reset": num("anthropic-ratelimit-unified-7d-reset"),
        "overage": pct("anthropic-ratelimit-unified-overage-utilization"),
        "status": h.get("anthropic-ratelimit-unified-status"),
    }

def _extract_windows(obj):
    """Find {percent, reset} windows anywhere in the response, tagged by key hint."""
    found = []
    def rec(o, hint=""):
        if isinstance(o, dict):
            pct = None
            for pk in ("utilization", "used_percent", "percent_used", "percent", "usage", "used"):
                if pk in o and isinstance(o[pk], (int, float)):
                    pct = o[pk]
                    break
            reset = None
            for rk in ("resets_at", "reset_at", "reset", "resets", "next_reset", "reset_time"):
                if rk in o:
                    reset = o[rk]
                    break
            if pct is not None:
                found.append((hint.lower(), as_percent(pct), to_epoch(reset)))
            for k, v in o.items():
                rec(v, k)
        elif isinstance(o, list):
            for v in o:
                rec(v, hint)
    rec(obj)
    return found

def _classify(found):
    five = week = None
    for hint, pct, reset in found:
        h = hint
        if any(t in h for t in ("five", "5h", "5_hour", "hour", "short")) and five is None:
            five = (pct, reset)
        elif any(t in h for t in ("seven", "week", "7d", "7_day", "day", "long")) and week is None:
            week = (pct, reset)
    # fallback: if exactly two windows and we couldn't tag them, assume order [5h, weekly]
    if (five is None or week is None) and len(found) >= 2:
        srt = sorted(found, key=lambda x: (x[2] or 0))
        if five is None:
            five = (srt[0][1], srt[0][2])
        if week is None:
            week = (srt[-1][1], srt[-1][2])
    return five, week

def _claude_from_transcripts():
    """No-token fallback: tokens consumed in the rolling 5h window, from local transcripts."""
    cutoff = time.time() - 5 * 3600
    total = 0
    files = glob.glob(os.path.join(HOME, ".claude", "projects", "**", "*.jsonl"), recursive=True)
    for fp in files:
        try:
            if os.path.getmtime(fp) < cutoff:
                continue
            with open(fp, errors="ignore") as f:
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    ts = o.get("timestamp")
                    ep = to_epoch(ts) if ts else None
                    if ep is not None and ep < cutoff:
                        continue
                    msg = o.get("message") or {}
                    u = msg.get("usage") if isinstance(msg, dict) else None
                    if not isinstance(u, dict):
                        continue
                    total += (u.get("input_tokens", 0) or 0)
                    total += (u.get("output_tokens", 0) or 0)
                    total += (u.get("cache_creation_input_tokens", 0) or 0)
        except Exception:
            continue
    return total

def get_claude():
    out = {"mode": None, "label": CFG.get("claude", {}).get("label", ""),
           "p5h": None, "p5h_reset": None, "pwk": None, "pwk_reset": None,
           "overage": None, "throughput": None, "error": None}
    token = _read_claude_token()
    if not token:
        out["mode"] = "transcripts"
        out["throughput"] = _claude_from_transcripts()
        return out
    # cache the API result for a few minutes so we don't make a call every 60s
    try:
        c = json.load(open(CLAUDE_CACHE))
        if time.time() - c.get("_ts", 0) < 240:
            out.update(c["data"]); out["mode"] = "api"
            return out
    except Exception:
        pass
    try:
        data = _claude_from_headers(token)
        out.update(data); out["mode"] = "api"
        json.dump({"_ts": time.time(), "data": data}, open(CLAUDE_CACHE, "w"))
        return out
    except urllib.error.HTTPError as e:
        out["error"] = f"HTTP {e.code} (token may be expired — re-run claude setup-token)"
    except Exception as e:
        out["error"] = str(e)[:120]
    out["mode"] = "transcripts"
    out["throughput"] = _claude_from_transcripts()
    return out

# ----------------------------------------------------------------------------- Featherless
def get_featherless():
    fc = CFG.get("featherless", {})
    proxy_up = port_open("127.0.0.1", 18086)
    model = None
    try:
        with open(os.path.join(HOME, ".codex", "config.toml")) as f:
            for line in f:
                if line.strip().startswith("model ="):
                    model = line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass
    key_present = os.path.exists(os.path.join(HOME, ".codex", "featherless.key"))
    return {"proxy_up": proxy_up, "model": model, "key": key_present,
            "dash": fc.get("dashboard_url", "https://featherless.ai")}

# ----------------------------------------------------------------------------- Ollama Cloud
def _chrome_ollama_cookies():
    """Decrypt the ollama.com session cookies from Chrome's cookie store (v10 / AES-128-CBC)."""
    import sqlite3, hashlib, subprocess, shutil
    pw = subprocess.run(["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
                        capture_output=True, timeout=5).stdout.strip()
    if not pw:
        return {}
    key = hashlib.pbkdf2_hmac("sha1", pw, b"saltysalt", 1003, 16)
    src = os.path.join(HOME, "Library/Application Support/Google/Chrome/Default/Cookies")
    tmp = "/tmp/ai_usage_ck.db"
    shutil.copy(src, tmp)
    rows = sqlite3.connect(tmp).execute(
        "select name, encrypted_value from cookies where host_key like '%ollama.com%'").fetchall()
    out = {}
    for name, enc in rows:
        if name not in ("aid", "__Secure-session") or enc[:3] != b"v10":
            continue
        p = subprocess.run(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-K", key.hex(), "-iv", "20" * 16, "-nopad"],
            input=enc[3:], capture_output=True, timeout=5)
        val = p.stdout
        if val:
            val = val[:-val[-1]]                       # strip PKCS7 padding
        if len(val) > 32 and any(b < 9 for b in val[:32]):
            val = val[32:]                             # strip sha256(host) prefix if present
        try:
            out[name] = val.decode("utf-8", "replace")
        except Exception:
            pass
    return out

def _ollama_cloud_usage():
    """Live Session + Weekly usage, scraped from the logged-in ollama.com settings page."""
    cookies = _chrome_ollama_cookies()
    jar = "; ".join(f"{k}={v}" for k, v in cookies.items())
    if not jar:
        return None
    req = urllib.request.Request(
        "https://ollama.com/settings",
        headers={"Cookie": jar, "User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "replace")
    if "Session usage" not in html:
        return None  # cookie expired / not logged in

    def pct(label):
        m = re.search(label + r".*?([\d.]+)%\s*used", html, re.S | re.I)
        return float(m.group(1)) if m else None

    # "Resets in ..." strings appear in order: [session, weekly]
    resets = re.findall(r"Resets in ([^<.]+)", html)
    s_pct, w_pct = pct("Session usage"), pct("Weekly usage")
    s_reset = resets[0].strip() if len(resets) > 0 else None
    w_reset = resets[1].strip() if len(resets) > 1 else None
    bal = None
    mb = re.search(r"Balance remaining.{0,120}?(\$[\d.,]+)", html, re.S | re.I)
    if mb:
        bal = mb.group(1)
    return {"s_pct": s_pct, "s_reset": s_reset, "w_pct": w_pct, "w_reset": w_reset, "balance": bal}

def get_ollama():
    oc = CFG.get("ollama_cloud", {})
    up = port_open("127.0.0.1", 11434)
    cloud_models = []
    if up:
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as r:
                tags = json.loads(r.read().decode())
            for m in tags.get("models", []):
                name = m.get("name", "")
                if name.endswith(":cloud") or "cloud" in name:
                    cloud_models.append(name)
        except Exception:
            pass
    try:
        with open(os.path.join(HOME, ".ollama", "config.json")) as f:
            ints = json.load(f).get("integrations", {})
        for v in ints.values():
            for m in v.get("models", []):
                if m not in cloud_models:
                    cloud_models.append(m)
    except Exception:
        pass
    usage, err = None, None
    try:
        usage = _ollama_cloud_usage()
    except Exception as e:
        err = str(e)[:120]
    return {"up": up, "cloud_models": cloud_models, "usage": usage, "err": err,
            "dash": oc.get("dashboard_url", "https://ollama.com/settings")}

# ----------------------------------------------------------------------------- render
def line(text, **params):
    parts = [text]
    extra = " ".join(f"{k}={v}" for k, v in params.items())
    if extra:
        parts.append(extra)
    print(" | ".join(parts))

def pct_str(p):
    return f"{p:.0f}%" if p is not None else "—"

def main():
    codex = get_codex()
    claude = get_claude()
    feath = get_featherless()
    ollama = get_ollama()

    # ---- connection health: Claude (token) + Ollama (cookie) are the auth-based services.
    #      Codex is local-only (no login) and is NOT allowed to trigger the sign-in state.
    claude_ok = claude.get("mode") == "api" and claude.get("p5h") is not None
    ou = ollama.get("usage") or {}
    ollama_ok = ou.get("s_pct") is not None or ou.get("w_pct") is not None
    signin = not (claude_ok and ollama_ok)

    # ---- menu bar title
    if signin:
        print("⚠️ Sign in")
    else:
        seg = []
        if claude.get("p5h") is not None:
            seg.append(f"C {claude['p5h']:.0f}%")
        if codex.get("p5h") is not None:
            seg.append(f"X {codex['p5h']:.0f}%")
        if ou.get("s_pct") is not None:
            seg.append(f"O {ou['s_pct']:.0f}%")
        print("  ".join(seg) if seg else "AI Usage")
    print("---")
    print(f"AI Usage — updated {datetime.now().strftime('%-I:%M %p')} | size=11 color=#888888")
    print("---")

    # ---- reconnect banner: shown at top of dropdown whenever an auth service dropped
    if signin:
        down = []
        if not ollama_ok:
            down.append("Ollama")
        if not claude_ok:
            down.append("Claude")
        print(f"⚠️  Sign-in needed: {', '.join(down)} | size=14 color={WARN_COLOR}")
        if not ollama_ok:
            line("→  Sign in to Ollama (opens ollama.com)", color=WARN_COLOR, size=13,
                 href=ollama.get("dash", "https://ollama.com/settings"))
        if not claude_ok:
            line("→  Open Claude account (opens claude.ai)", color=WARN_COLOR, size=13,
                 href="https://claude.ai/settings/usage")
            line("    then in Terminal run:  ~/.local/bin/claude setup-token",
                 font=MONO, size=11, color="#888888")
        print("---")

    # ---- Claude
    label = f"  ({claude['label']})" if claude.get("label") else ""
    print(f"Claude{label} | size=13")
    if claude["mode"] in ("api",) and (claude["p5h"] is not None or claude["pwk"] is not None):
        p = claude["p5h"]
        line(f"5-hour   {bar(p)}  {pct_str(p)}", color=color_for(p), font=MONO)
        line(f"  {fmt_reset(claude['p5h_reset'])}", color="#888888", size=11)
        p = claude["pwk"]
        line(f"Weekly   {bar(p)}  {pct_str(p)}", color=color_for(p), font=MONO)
        line(f"  {fmt_reset(claude['pwk_reset'])}", color="#888888", size=11)
    elif claude["mode"] == "transcripts":
        k = (claude.get("throughput") or 0) / 1000.0
        line(f"~{k:.0f}k tokens used in last 5h (local estimate)", color="#d29922")
        line("Add an OAuth token for exact % — see config", color="#888888", size=11)
        line("How: run  claude setup-token", color="#888888", size=11, font=MONO)
    else:
        line(f"Couldn't read usage: {claude.get('error','unknown')}", color="#e5534b", size=11)
    line("Open Claude usage page", href="https://claude.ai/settings/usage")
    print("---")

    # ---- Codex
    plan = f"  ({codex['plan']})" if codex.get("plan") else ""
    print(f"Codex{plan} | size=13")
    if codex["ok"]:
        p = codex["p5h"]
        line(f"5-hour   {bar(p)}  {pct_str(p)}", color=color_for(p), font=MONO)
        line(f"  {fmt_reset(codex['p5h_reset'])}", color="#888888", size=11)
        p = codex["pwk"]
        line(f"Weekly   {bar(p)}  {pct_str(p)}", color=color_for(p), font=MONO)
        line(f"  {fmt_reset(codex['pwk_reset'])}", color="#888888", size=11)
        if codex.get("age_min", 0) > 30:
            line(f"  (last seen {codex['age_min']}m ago)", color="#888888", size=10)
    else:
        line(codex.get("note", "No data"), color="#888888", size=11)
    print("---")

    # ---- Featherless
    dot = "🟢" if feath["proxy_up"] else "⚪️"
    print(f"Featherless  {dot} | size=13")
    line(f"Model: {feath.get('model') or 'n/a'}", size=11, color="#888888")
    line(f"Proxy {'up' if feath['proxy_up'] else 'down'} · key {'present' if feath['key'] else 'missing'}",
         size=11, color="#888888")
    line("Flat subscription — no token quota to meter", size=11, color="#888888")
    line("Open Featherless dashboard", href=feath["dash"])
    print("---")

    # ---- Ollama Cloud
    dot = "🟢" if ollama["up"] else "⚪️"
    print(f"Ollama Cloud  {dot} | size=13")
    u = ollama.get("usage")
    if u and (u.get("s_pct") is not None or u.get("w_pct") is not None):
        p = u["s_pct"]
        line(f"Session  {bar(p)}  {pct_str(p)}", color=color_for(p), font=MONO)
        if u.get("s_reset"):
            line(f"  resets in {u['s_reset']}", color="#888888", size=11)
        p = u["w_pct"]
        line(f"Weekly   {bar(p)}  {pct_str(p)}", color=color_for(p), font=MONO)
        if u.get("w_reset"):
            line(f"  resets in {u['w_reset']}", color="#888888", size=11)
        if u.get("balance"):
            line(f"Extra-usage balance: {u['balance']}", color="#888888", size=11)
    elif ollama.get("err"):
        line("Live usage unavailable (log into ollama.com in Chrome)", color="#d29922", size=11)
    else:
        line("Live usage unavailable — open dashboard below", color="#d29922", size=11)
    if ollama["cloud_models"]:
        line(f"Active model: {ollama['cloud_models'][0]}", size=11, color="#888888")
    line("Usage & limits (web dashboard)", href=ollama["dash"])
    print("---")

    line("Refresh", refresh="true")
    line("Edit config…", href="file://" + CFG_PATH.replace(" ", "%20"))

MONO = "Menlo"

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("AI Usage ⚠️")
        print("---")
        print(f"Plugin error: {e}")
