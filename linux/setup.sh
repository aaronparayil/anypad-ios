#!/usr/bin/env bash
# Prepares Ubuntu's Bluetooth stack (BlueZ) for the pairing test.
#   bash setup.sh          -> identify as Xbox Series X|S controller (USB ID 045e:0b13)
#   bash setup.sh 0b20     -> identify as Xbox One S controller, BLE firmware (045e:0b20)
# Undo with: bash restore.sh
set -euo pipefail

PID="${1:-0b13}"
CONF=/etc/bluetooth/main.conf
BACKUP="$CONF.xboxtest.bak"

if /usr/bin/python3 -c 'import dbus, gi' 2>/dev/null && command -v bluetoothctl >/dev/null; then
  echo "== Needed packages are already installed"
else
  echo "== Installing Python bindings (free, from Ubuntu's own repos; needs internet)"
  sudo apt-get update
  sudo apt-get install -y bluez python3-dbus python3-gi
fi

echo "== BlueZ version (needs 5.50 or newer)"
bluetoothd --version || /usr/libexec/bluetooth/bluetoothd --version || true

if [ ! -f "$BACKUP" ]; then
  sudo cp "$CONF" "$BACKUP"
  echo "== Backed up $CONF to $BACKUP"
fi

echo "== Setting DeviceID = usb:045e:${PID}:0509 in $CONF"
sudo sed -i -e '/^[#[:space:]]*DeviceID[[:space:]]*=/d' -e '/^[#[:space:]]*JustWorksRepairing[[:space:]]*=/d' "$CONF"
if grep -q '^\[General\]' "$CONF"; then
  # "confirm" lets a phone that forgot us pair again; the relay's pairing limit decides.
  sudo sed -i -e "/^\[General\]/a DeviceID = usb:045e:${PID}:0509\nJustWorksRepairing = confirm" "$CONF"
else
  printf '[General]\nDeviceID = usb:045e:%s:0509\nJustWorksRepairing = confirm\n' "$PID" | sudo tee -a "$CONF" >/dev/null
fi

echo "== Restarting Bluetooth"
sudo rfkill unblock bluetooth || true
sudo systemctl restart bluetooth
sleep 2

echo "== Adapter check: 'le' and 'advertising' must appear under supported settings"
sudo timeout 10 btmgmt info | sed -n '1,12p' || true
bluetoothctl show | grep -E 'Name|Alias|Powered|Roles' || true

echo
echo "Bluetooth is ready. To play, run:  bash run.sh"
