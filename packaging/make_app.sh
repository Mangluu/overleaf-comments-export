#!/bin/bash
# Build "Overleaf Comments Export.app" from launcher.sh.
#
#   bash packaging/make_app.sh [destination-folder]
#
# Defaults to ~/Applications. Not ~/Documents: that folder was inside iCloud
# Drive until the incident of 2026-08-22, and an app bundle in a live-sync
# folder is both slow to launch and easy to lose.
set -eu

DEST="${1:-$HOME/Applications}"
APP="$DEST/Overleaf Comments Export.app"
HERE="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$HERE/launcher.sh" "$APP/Contents/MacOS/Overleaf Comments Export"
chmod +x "$APP/Contents/MacOS/Overleaf Comments Export"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Overleaf Comments Export</string>
    <key>CFBundleDisplayName</key><string>Overleaf Comments Export</string>
    <key>CFBundleExecutable</key><string>Overleaf Comments Export</string>
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
