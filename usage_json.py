#!/usr/bin/env python3
"""Karlz AI usage feed: reuse the AI Usage Bar plugin's provider functions and
emit a compact JSON blob for the iOS/watch app (served via gort). No secrets in
the output — just usage percentages, resets, and labels."""
import runpy, json, os, time
from datetime import datetime

PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aiusage.60s.py")
M = runpy.run_path(PLUGIN)

def clock(epoch):
    """Epoch seconds -> local 'h:mm AM' string, or '' if unusable."""
    try:
        return datetime.fromtimestamp(float(epoch)).strftime("%-I:%M %p")
    except Exception:
        return ""

def num(v):
    try:
        f = float(v)
        return round(f, 1)
    except Exception:
        return None

def provider(pid, name, label, pct, reset, wpct, wreset, ok, extra=None):
    d = {"id": pid, "name": name, "label": label or "",
         "pct": num(pct), "reset": reset or "",
         "weeklyPct": num(wpct), "weeklyReset": wreset or "",
         "ok": bool(ok)}
    if extra:
        d["extra"] = extra
    return d

out = []

# Claude
try:
    c = M["get_claude"]()
    ok = c.get("mode") == "api" and c.get("p5h") is not None
    out.append(provider("claude", "Claude", c.get("label"),
                        c.get("p5h"), clock(c.get("p5h_reset")),
                        c.get("pwk"), clock(c.get("pwk_reset")), ok))
except Exception as e:
    out.append(provider("claude", "Claude", "", None, "", None, "", False, str(e)[:60]))

# Codex
try:
    x = M["get_codex"]()
    lbl = (x.get("plan") or "").title()
    out.append(provider("codex", "Codex", lbl,
                        x.get("p5h"), clock(x.get("p5h_reset")),
                        x.get("pwk"), clock(x.get("pwk_reset")), x.get("ok", False)))
except Exception as e:
    out.append(provider("codex", "Codex", "", None, "", None, "", False, str(e)[:60]))

# Ollama Cloud
try:
    o = M["get_ollama"]()
    u = o.get("usage") or {}
    ok = u.get("s_pct") is not None or u.get("w_pct") is not None
    out.append(provider("ollama", "Ollama Cloud", "",
                        u.get("s_pct"), u.get("s_reset"),
                        u.get("w_pct"), u.get("w_reset"), ok,
                        extra=(f"bal {u.get('balance')}" if u.get("balance") else None)))
except Exception as e:
    out.append(provider("ollama", "Ollama Cloud", "", None, "", None, "", False, str(e)[:60]))

# z.ai
try:
    z = M["get_zai"]()
    mon = z.get("monitor") or {}
    t5 = (mon.get("token_5h") or {})
    tw = (mon.get("token_weekly") or {})
    lbl = (z.get("plan") or "").upper()
    out.append(provider("zai", "z.ai", lbl,
                        t5.get("pct"), clock(t5.get("reset")) or (t5.get("reset") if isinstance(t5.get("reset"), str) else ""),
                        tw.get("pct"), clock(tw.get("reset")) or (tw.get("reset") if isinstance(tw.get("reset"), str) else ""),
                        z.get("ok", False)))
except Exception as e:
    out.append(provider("zai", "z.ai", "", None, "", None, "", False, str(e)[:60]))

blob = {"ts": int(time.time()), "updated": datetime.now().strftime("%-I:%M %p"), "providers": out}
print(json.dumps(blob, indent=2))
