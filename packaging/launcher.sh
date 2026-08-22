#!/bin/bash
# Launcher for Overleaf Comments Export.
#
# Source + venv live under ~/Library/Application Support rather than in
# ~/Documents, which keeps them clear of the macOS permission prompts on
# Documents and, as of the iCloud incident of 2026-08-22, clear of iCloud
# Drive as well. Active repositories do not belong in a live-sync folder.
#
# This file is in the repository on purpose. The .app it builds was lost when
# the old Documents tree went, and it was the one piece of the project that
# had never been committed.

set -u

APP_HOME="$HOME/Library/Application Support/OverleafCommentsExport/overleaf_comments_export"
VENV_DIR="$APP_HOME/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

LOG_DIR="$HOME/Library/Logs/OverleafCommentsExport"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/launcher.log"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Which architecture this Mac really is. `uname -m` reports the architecture
# of the *calling process*, so inside a translated one it says x86_64 on an
# Apple silicon Mac, and the app then tried to run an arm64 virtualenv under
# Rosetta and failed to load every compiled module. hw.optional.arm64 is a
# property of the hardware and does not change under translation.
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    NATIVE_ARCH="arm64"
else
    NATIVE_ARCH="x86_64"
fi

{
    echo "[$(ts)] launch starting"
    echo "[$(ts)] APP_HOME=$APP_HOME"
} >>"$LOG_FILE"

show_alert() {
    /usr/bin/osascript <<EOF >/dev/null 2>&1
display dialog "$1" buttons {"OK"} default button "OK" with icon stop with title "Overleaf Comments Export"
EOF
}

if [ ! -x "$VENV_PYTHON" ]; then
    msg="The Python environment is missing at:

$VENV_PYTHON

Please reinstall the tool. See ~/Library/Logs/OverleafCommentsExport/launcher.log for details."
    echo "[$(ts)] FATAL: venv python not found" >>"$LOG_FILE"
    show_alert "$msg"
    exit 1
fi

# Verify all required dependencies are importable. If anything is missing,
# self-heal by reinstalling editable from the package source.
NEEDED="import browser_cookie3, pyoverleaf, requests, tkinter, pymupdf, overleaf_comments_export"
if ! /usr/bin/arch -"$NATIVE_ARCH" "$VENV_PYTHON" -c "$NEEDED" >>"$LOG_FILE" 2>&1; then
    echo "[$(ts)] dependency check failed; attempting reinstall..." >>"$LOG_FILE"
    /usr/bin/arch -"$NATIVE_ARCH" "$VENV_PYTHON" -m pip install --quiet --upgrade pip >>"$LOG_FILE" 2>&1 || true
    /usr/bin/arch -"$NATIVE_ARCH" "$VENV_PYTHON" -m pip install --quiet -e "$APP_HOME[gui,pdf]" >>"$LOG_FILE" 2>&1
    if ! /usr/bin/arch -"$NATIVE_ARCH" "$VENV_PYTHON" -c "$NEEDED" >>"$LOG_FILE" 2>&1; then
        echo "[$(ts)] FATAL: reinstall failed" >>"$LOG_FILE"
        show_alert "Required Python packages could not be installed.

See log at:
~/Library/Logs/OverleafCommentsExport/launcher.log

You can install them manually:
\"$VENV_PYTHON\" -m pip install -e \"$APP_HOME\""
        exit 1
    fi
    echo "[$(ts)] reinstall succeeded" >>"$LOG_FILE"
fi

echo "[$(ts)] dependencies ok, launching GUI" >>"$LOG_FILE"

# Default to the window; anything passed through goes to the command line.
exec /usr/bin/arch -"$NATIVE_ARCH" "$VENV_PYTHON" -m overleaf_comments_export "${@:---gui}" \
    >>"$LOG_FILE" 2>&1
