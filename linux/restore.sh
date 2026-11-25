#!/usr/bin/env bash
# Puts Ubuntu's Bluetooth config back the way it was before setup.sh.
set -euo pipefail
CONF=/etc/bluetooth/main.conf
BACKUP="$CONF.xboxtest.bak"
if [ -f "$BACKUP" ]; then
  sudo cp "$BACKUP" "$CONF"
  sudo rm "$BACKUP"
  sudo systemctl restart bluetooth
  echo "Restored $CONF and restarted Bluetooth."
else
  echo "No backup found at $BACKUP - nothing to restore."
fi
