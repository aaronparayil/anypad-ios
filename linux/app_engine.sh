#!/usr/bin/env bash
# Runs the relay as root.
#   app_engine.sh run [ios|android]           from anypad.py (through pkexec); stops when stdin closes
#   app_engine.sh play [ios|android] [args]   from run.sh; Ctrl+C stops it
#   app_engine.sh restore
# For Android, Bluetooth is switched to LE only while the relay runs, then back: Android may
# otherwise pair over classic Bluetooth, where there is no controller.
set -uo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE" || exit 1
CONF="${XBOX_BRIDGE_CONF:-/etc/bluetooth/main.conf}"
PY="${ANYPAD_PYTHON:-/usr/bin/python3}"

set_mode() {    # "ControllerMode = le", or the line that was there before (maybe none)
  sed -i '/^[#[:space:]]*ControllerMode[[:space:]]*=/d' "$CONF"
  [ -n "$1" ] && sed -i "/^\[General\]/a $1" "$CONF"
  rfkill unblock bluetooth 2> /dev/null
  systemctl restart bluetooth < /dev/null
  sleep 3
}

case "${1:-run}" in
  run|play)
    how=$1
    phone=${2:-ios}
    shift $(( $# < 2 ? $# : 2 ))
    case "$phone" in ios|android) ;; *) echo "FAIL: unknown phone '$phone'"; exit 2 ;; esac
    if ! grep -qiE '^DeviceID[[:space:]]*=[[:space:]]*usb:045e:' "$CONF" || ! grep -q '^JustWorksRepairing' "$CONF"; then
      echo "Setting up Bluetooth (first time)..."
      bash setup.sh < /dev/null || { echo "FAIL: setting up Bluetooth"; exit 1; }
    fi
    modprobe xpad 2> /dev/null
    switched=""
    if [ "$phone" = android ] && ! grep -qE '^ControllerMode[[:space:]]*=[[:space:]]*le[[:space:]]*$' "$CONF"; then
      before=$(grep -m1 -E '^ControllerMode[[:space:]]*=' "$CONF")
      echo "Bluetooth on this laptop is LE only while AnyPad runs (for Android)"
      set_mode "ControllerMode = le"
      switched=1
    fi
    extra=()
    [ "$how" = run ] && extra=(--quit-on-eof)
    keep=()
    command -v systemd-inhibit > /dev/null &&
      keep=(systemd-inhibit --what=idle:sleep:handle-lid-switch --why="AnyPad is running")
    # Ctrl+C reaches the relay, which stops cleanly; this script then puts Bluetooth back.
    trap 'true' INT TERM HUP
    "${keep[@]}" "$PY" -u -W ignore relay.py --phone "$phone" "${extra[@]}" "$@"
    code=$?
    if [ -n "$switched" ]; then
      echo "Bluetooth on this laptop is back to how it was"
      set_mode "$before"
    fi
    exit $code
    ;;
  restore)
    exec bash restore.sh < /dev/null
    ;;
  *) echo "usage: app_engine.sh run|play [ios|android] | restore"; exit 2 ;;
esac
