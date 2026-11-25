#!/usr/bin/env bash
# Adds AnyPad to your applications menu (for you only). Undo: bash install-app.sh --remove
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
FILE="$APPS/io.github.aaronparayil.anypad.desktop"
if [ "${1:-}" = "--remove" ]; then
  rm -f "$FILE"
  echo "Removed AnyPad from the menu."
  exit 0
fi
mkdir -p "$APPS"
cat > "$FILE" <<EOF
[Desktop Entry]
Type=Application
Name=AnyPad
Comment=Use any gamepad with your iPhone or iPad
Exec=/usr/bin/python3 "$HERE/anypad.py"
Icon=$HERE/anypad.png
Categories=Game;Utility;
Keywords=gamepad;controller;bluetooth;iphone;ipad;
EOF
echo "AnyPad is in your applications menu. Keep this folder where it is: $HERE"
