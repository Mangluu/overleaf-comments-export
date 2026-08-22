#!/bin/bash
# Build "Overleaf Comments Export.app" from launcher.sh.
#
#   bash packaging/make_app.sh [destination-folder] [app-home]
#
# destination-folder defaults to ~/Applications. app-home is the checkout the
# app should run from, and defaults to the directory holding this script, so
# building from a clone points the app at that clone. Not ~/Documents: that folder was inside iCloud
# Drive until the incident of 2026-08-22, and an app bundle in a live-sync
# folder is both slow to launch and easy to lose.
set -eu

DEST="${1:-$HOME/Applications}"
HERE="$(cd "$(dirname "$0")" && pwd)"
APP_HOME="${2:-$(cd "$HERE/.." && pwd)}"
APP="$DEST/Overleaf Comments Export.app"

if [ ! -x "$APP_HOME/.venv/bin/python" ]; then
    echo "warning: no virtualenv at $APP_HOME/.venv" >&2
    echo "         create one with: python3 -m venv .venv && .venv/bin/python -m pip install -e '.[gui,pdf]'" >&2
fi

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
sed "s|@APP_HOME@|$APP_HOME|" "$HERE/launcher.sh" \
    > "$APP/Contents/MacOS/Overleaf Comments Export"
chmod +x "$APP/Contents/MacOS/Overleaf Comments Export"

# The icon. Rebuild it if it is missing, so a fresh clone produces a complete
# app rather than a blank one, which is what it looked like before.
if [ ! -f "$HERE/AppIcon.icns" ] && [ -x "$APP_HOME/.venv/bin/python" ]; then
    "$APP_HOME/.venv/bin/python" "$HERE/make_icns.py" >/dev/null 2>&1 || true
fi
if [ -f "$HERE/AppIcon.icns" ]; then
    cp "$HERE/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
else
    echo "warning: no AppIcon.icns, the app will show a blank icon" >&2
fi

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Overleaf Comments Export</string>
    <key>CFBundleDisplayName</key><string>Overleaf Comments Export</string>
    <key>CFBundleExecutable</key><string>Overleaf Comments Export</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundleIdentifier</key><string>com.mangluu.overleaf-comments-export</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$(sed -n 's/^version = "\(.*\)"/\1/p' "$HERE/../pyproject.toml")</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <!-- A real app bundle rather than a bare script, so macOS gives the
         process a proper GUI identity and its windows and dialogs behave. -->
    <key>NSHighResolutionCapable</key><true/>
    <!-- Prefer native. Without this the bundle was launched translated on an
         Apple silicon Mac and could not load the virtualenv's arm64 modules. -->
    <key>LSArchitecturePriority</key>
    <array><string>arm64</string><string>x86_64</string></array>
</dict>
</plist>
PLIST

echo "Built: $APP"
echo "  running from: $APP_HOME"
