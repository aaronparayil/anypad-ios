#!/usr/bin/env bash
# One command to play: prepares Bluetooth if needed, keeps the laptop awake, runs the relay.
#   bash run.sh              normal
#   bash run.sh --check      show controller input only, no Bluetooth
#   bash run.sh --test-rumble   run the controller's motors only, no Bluetooth
#   bash run.sh --rumble 0      play with rumble off (200 = double strength)
#   bash run.sh --pair-seconds 0   no new pairing; only a phone paired earlier
#   bash run.sh --le-only    switch to Bluetooth LE only, then run (stays until --dual or reboot)
#   bash run.sh --dual       switch back to the default, then run
#   bash run.sh --android    for an Android phone or tablet: LE only while it runs, then back
#   bash run.sh --ios        for an iPhone or iPad (the default, except in the Android download)
set -euo pipefail
cd "$(dirname "$0")"
CONF="${XBOX_BRIDGE_CONF:-/etc/bluetooth/main.conf}"

mode=""
phone=ios
# The Android download has a file named "phone" that says android.
[ "$(cat phone 2> /dev/null)" = android ] && phone=android
bluetooth=yes
args=()
for a in "$@"; do
  case "$a" in
    --le-only) mode=le ;;
    --dual) mode=dual ;;
    --android) phone=android ;;
    --ios) phone=ios ;;
    --check|--test-rumble) bluetooth=no; args+=("$a") ;;
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

if [ "$bluetooth" = yes ]; then
  exec sudo ${XBOX_BRIDGE_CONF:+XBOX_BRIDGE_CONF="$CONF"} bash app_engine.sh play "$phone" "${args[@]}"
fi

exec sudo systemd-inhibit --what=idle:sleep:handle-lid-switch --why="Xbox bridge is running"   /usr/bin/python3 relay.py "${args[@]}"
