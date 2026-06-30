#!/bin/bash
# AI Usage Bar — uninstaller. Removes the plugin, LaunchAgent, and symlink.
# Leaves your config + tokens in ~/.config/ai-usage-bar (so you don't lose them).
# Use --purge to also delete config/tokens. Does NOT uninstall SwiftBar itself.
set -euo pipefail

PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

say()  { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m ✓\033[0m %s\n"  "$*"; }

say "Stopping SwiftBar…"
osascript -e 'quit app "SwiftBar"' 2>/dev/null || true
pkill -x SwiftBar 2>/dev/null || true

LA="$HOME/Library/LaunchAgents/com.ameba.SwiftBar.launch.plist"
if [ -f "$LA" ]; then
    launchctl unload "$LA" 2>/dev/null || true
    rm -f "$LA"
    ok "LaunchAgent removed"
fi

PLUG="$HOME/Library/Application Support/ai-usage-bar/plugins/aiusage.60s.py"
if [ -f "$PLUG" ]; then
    rm -f "$PLUG"
    rmdir "$(dirname "$PLUG")" 2>/dev/null || true
    rmdir "$(dirname "$(dirname "$PLUG")")" 2>/dev/null || true
    ok "Plugin removed"
fi

if [ -L "$HOME/.local/bin/claude" ]; then
    rm -f "$HOME/.local/bin/claude"
    ok "Removed ~/.local/bin/claude symlink"
fi

if [ "$PURGE" = "1" ]; then
    rm -rf "$HOME/.config/ai-usage-bar"
    ok "Purged $HOME/.config/ai-usage-bar (config + tokens)"
else
    printf "\033[1;33m ⚠\033[0m Config and tokens left in %s (use --purge to remove)\n" "$HOME/.config/ai-usage-bar"
fi

echo
echo "Done. SwiftBar itself (/Applications/SwiftBar.app) was not removed."
