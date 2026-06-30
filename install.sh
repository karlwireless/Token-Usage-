#!/bin/bash
# AI Usage Bar — installer for macOS
# Idempotent: re-running is safe; won't clobber an existing config.
set -euo pipefail

# ----- where things go -----------------------------------------------------
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$HOME/Library/Application Support/ai-usage-bar/plugins"
CFG_DIR="$HOME/.config/ai-usage-bar"
CFG_FILE="$CFG_DIR/config.json"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/com.ameba.SwiftBar.launch.plist"
APP="/Applications/SwiftBar.app"
SWIFTBAR_URL_FALLBACK="https://github.com/swiftbar/SwiftBar/releases/download/v2.0.1/SwiftBar.v2.0.1.b536.zip"

say()  { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m ✓\033[0m %s\n"  "$*"; }
warn() { printf "\033[1;33m ⚠\033[0m %s\n"  "$*"; }
die()  { printf "\033[1;31m ✗ %s\033[0m\n"  "$*" >&2; exit 1; }

# ----- 0. prereqs ----------------------------------------------------------
say "Checking prerequisites…"
command -v python3 >/dev/null || die "python3 not found (install Xcode CLT or Python 3)"
command -v openssl >/dev/null || die "openssl not found"
[ -f "$REPO_DIR/aiusage.60s.py" ] || die "aiusage.60s.py not found next to installer"
ok "python3, openssl, plugin source"

# ----- 1. SwiftBar ---------------------------------------------------------
if [ ! -d "$APP" ]; then
    say "Installing SwiftBar…"
    URL="$SWIFTBAR_URL_FALLBACK"
    # try to find the latest release; fall back to pinned URL on any failure
    LATEST=$(curl -fsSL --max-time 8 https://api.github.com/repos/swiftbar/SwiftBar/releases/latest 2>/dev/null \
             | python3 -c "import json,sys
try:
    d=json.load(sys.stdin)
    for a in d.get('assets',[]):
        if a['name'].endswith('.zip'):
            print(a['browser_download_url']); break
except: pass" 2>/dev/null || true)
    [ -n "$LATEST" ] && URL="$LATEST"
    TMP=$(mktemp -d)
    curl -fsSL --max-time 120 -o "$TMP/sb.zip" "$URL" || die "SwiftBar download failed ($URL)"
    ditto -x -k "$TMP/sb.zip" "$TMP/out"
    [ -d "$TMP/out/SwiftBar.app" ] || die "SwiftBar.app not in downloaded zip"
    mv "$TMP/out/SwiftBar.app" /Applications/
    xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
    rm -rf "$TMP"
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true
    ok "SwiftBar installed at $APP"
else
    ok "SwiftBar already installed"
fi

# ----- 2. plugin -----------------------------------------------------------
say "Installing plugin…"
mkdir -p "$PLUGIN_DIR"
cp "$REPO_DIR/aiusage.60s.py" "$PLUGIN_DIR/aiusage.60s.py"
chmod +x "$PLUGIN_DIR/aiusage.60s.py"
ok "Plugin → $PLUGIN_DIR/aiusage.60s.py"

# ----- 3. config -----------------------------------------------------------
say "Setting up config…"
mkdir -p "$CFG_DIR"
if [ -e "$CFG_FILE" ]; then
    warn "Existing config preserved: $CFG_FILE"
else
    cp "$REPO_DIR/config.example.json" "$CFG_FILE"
    ok "Config seeded → $CFG_FILE"
fi

# ----- 4. SwiftBar prefs ---------------------------------------------------
say "Configuring SwiftBar…"
# stop SwiftBar so prefs writes stick
osascript -e 'quit app "SwiftBar"' 2>/dev/null || true
pkill -x SwiftBar 2>/dev/null || true
sleep 1
defaults write com.ameba.SwiftBar PluginDirectory "$PLUGIN_DIR"
defaults write com.ameba.SwiftBar MakePluginExecutable -bool true
defaults write com.ameba.SwiftBar DisableBmpEnvVars -bool false
# make the menu-bar item visible (SwiftBar 2.x key)
defaults write com.ameba.SwiftBar "NSStatusItem VisibleCC Item-1" -bool true
ok "SwiftBar prefs set"

# ----- 5. LaunchAgent (launch at login) -----------------------------------
say "Installing LaunchAgent (launch-at-login)…"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$LAUNCH_AGENT" <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ameba.SwiftBar.launch</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-a</string>
    <string>$APP</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>/tmp/swiftbar-launch.err</string>
</dict>
</plist>
XML
plutil -lint "$LAUNCH_AGENT" >/dev/null || die "LaunchAgent plist invalid"
launchctl unload "$LAUNCH_AGENT" 2>/dev/null || true
launchctl load "$LAUNCH_AGENT"
ok "LaunchAgent loaded"

# ----- 6. symlink bundled Claude CLI if present ---------------------------
CLAUDE_BUNDLED=$(ls -t "$HOME/Library/Application Support/Claude/claude-code/"*/claude.app/Contents/MacOS/claude 2>/dev/null | head -1 || true)
if [ -n "$CLAUDE_BUNDLED" ] && [ -x "$CLAUDE_BUNDLED" ]; then
    mkdir -p "$HOME/.local/bin"
    ln -sf "$CLAUDE_BUNDLED" "$HOME/.local/bin/claude"
    ok "Claude CLI symlinked → ~/.local/bin/claude"
else
    warn "Claude desktop not detected — install it for the easiest 'claude setup-token' path"
fi

# ----- 7. launch SwiftBar -------------------------------------------------
say "Launching SwiftBar…"
open -a "$APP"
sleep 3
open "swiftbar://refreshallplugins" 2>/dev/null || true
ok "SwiftBar running"

# ----- 8. next steps ------------------------------------------------------
G=$'\033[1;32m'; B=$'\033[1m'; C=$'\033[36m'; R=$'\033[0m'
printf "\n%s──────── Install complete ────────%s\n\n" "$G" "$R"
printf "The menu-bar item should appear shortly (top-right). Two services need a one-time auth step:\n\n"
printf "%sClaude%s (for the C tile)\n" "$B" "$R"
printf "  1. In Terminal, run:    %s~/.local/bin/claude setup-token%s\n" "$C" "$R"
printf "     (or use whichever 'claude' CLI you have on PATH)\n"
printf "  2. Approve in your browser; copy the printed %ssk-ant-oat01-…%s token.\n" "$C" "$R"
printf "  3. Save it:\n"
printf "       %secho 'PASTE_TOKEN_HERE' > %s/claude-oauth.token && chmod 600 %s/claude-oauth.token%s\n\n" "$C" "$CFG_DIR" "$CFG_DIR" "$R"
printf "%sOllama Cloud%s (for the O tile)\n" "$B" "$R"
printf "  1. Open %shttps://ollama.com/settings%s in Google Chrome and stay logged in.\n" "$C" "$R"
printf "  2. On the first plugin refresh you'll get ONE macOS keychain prompt for\n"
printf "     \"Chrome Safe Storage\" — click %sAlways Allow%s.\n\n" "$B" "$R"
printf "%sCodex%s (X tile) and %sFeatherless%s work automatically if those tools are installed.\n\n" "$B" "$R" "$B" "$R"
printf "Force a refresh any time:    %sopen \"swiftbar://refreshallplugins\"%s\n" "$C" "$R"
printf "Edit config:                 %s%s%s\n\n" "$C" "$CFG_FILE" "$R"
