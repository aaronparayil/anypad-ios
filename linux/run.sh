#!/usr/bin/env bash
# One command to play: prepares Bluetooth if needed, keeps the laptop awake, runs the relay.
#   bash run.sh              normal
#   bash run.sh --check      show controller input only, no Bluetooth
#   bash run.sh --test-rumble   run the controller's motors only, no Bluetooth
#   bash run.sh --rumble 0      play with rumble off (200 = double strength)
#   bash run.sh --pair-seconds 0   no new pairing; only a phone paired earlier
#   bash run.sh --le-only    switch to Bluetooth LE only, then run (stays until --dual or reboot)
#   bash run.sh --dual       switch back to the default, then run
set -euo pipefail
cd "$(dirname "$0")"
CONF="${XBOX_BRIDGE_CONF:-/etc/bluetooth/main.conf}"

mode=""
args=()
for a in "$@"; do
  case "$a" in
    --le-only) mode=le ;;
    --dual) mode=dual ;;
    *) args+=("$a") ;;
  esac
done

if ! grep -qiE '^DeviceID[[:space:]]*=[[:space:]]*usb:045e:' "$CONF" ||
   ! grep -q '^JustWorksRepairing' "$CONF"; then
  bash setup.sh
fi
if [ -n "$mode" ]; then
  echo "== Setting Bluetooth mode: $mode"
  sudo sed -i -e '/^[#[:space:]]*ControllerMode[[:space:]]*=/d'     -e "/^\[General\]/a ControllerMode = $mode" "$CONF"
  sudo rfkill unblock bluetooth || true
  sudo systemctl restart bluetooth
  sleep 3
fi
sudo modprobe xpad || true

exec sudo systemd-inhibit --what=idle:sleep:handle-lid-switch --why="Xbox bridge is running"   /usr/bin/python3 relay.py "${args[@]}"
