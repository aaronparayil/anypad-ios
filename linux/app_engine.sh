#!/usr/bin/env bash
# Started as root by anypad.py (through pkexec). Stops when its stdin closes.
#   app_engine.sh run | restore
set -uo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE" || exit 1
CONF=/etc/bluetooth/main.conf

case "${1:-run}" in
  run)
    if ! grep -qiE '^DeviceID[[:space:]]*=[[:space:]]*usb:045e:' "$CONF" || ! grep -q '^JustWorksRepairing' "$CONF"; then
      echo "Setting up Bluetooth (first time)..."
      bash setup.sh < /dev/null || { echo "FAIL: setting up Bluetooth"; exit 1; }
    fi
    modprobe xpad 2> /dev/null
    if command -v systemd-inhibit > /dev/null; then
      exec systemd-inhibit --what=idle:sleep:handle-lid-switch --why="AnyPad is running" \
        /usr/bin/python3 -u -W ignore relay.py --quit-on-eof
    fi
    exec /usr/bin/python3 -u -W ignore relay.py --quit-on-eof
    ;;
  restore)
    exec bash restore.sh < /dev/null
    ;;
  *) echo "usage: app_engine.sh run | restore"; exit 2 ;;
esac
