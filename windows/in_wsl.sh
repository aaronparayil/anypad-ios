#!/bin/bash
# Runs inside WSL as root. Usage: in_wsl.sh prepare | run KIT_DIR [SECONDS] | forget | relay KIT_DIR [relay options] | restore
CONF=/etc/bluetooth/main.conf
BACKUP=$CONF.anypad.bak
VHCI=/sys/devices/platform/vhci_hcd.0

# Give the adapter back from the Linux side. Safe to run more than once.
release() {
  systemctl stop bluetooth < /dev/null 2>/dev/null
  [ -f $BACKUP ] && cp $BACKUP $CONF && rm $BACKUP && echo "WSL's Bluetooth settings restored"
  modprobe -r btusb 2>/dev/null
  [ -r $VHCI/status ] || return 0
  # status lines: hub port state speed dev sockfd local_busid; only detach Intel's adapter
  while read -r hub port sta rest; do
    busid=${rest##* }
    [ "$(cat "/sys/bus/usb/devices/$busid/idVendor" 2>/dev/null)" = 8087 ] || continue
    echo $((10#$port)) > $VHCI/detach 2>/dev/null
  done < <(tail -n +2 $VHCI/status)
}
SELF=$(readlink -f "$0")
case "$1" in
  prepare)
    # cmac and ecdh must be loaded by hand: the kernel cannot load them itself in WSL.
    for m in vhci-hcd bluetooth cmac ecdh_generic btintel; do modprobe $m || exit 1; done
    [ -f $BACKUP ] || cp $CONF $BACKUP
    sed -i '/^[#[:space:]]*DeviceID[[:space:]]*=/d' $CONF
    sed -i '/^\[General\]/a DeviceID = usb:045e:0b13:0509' $CONF
    grep -q '^DeviceID = usb:045e:0b13:0509' $CONF && echo "Xbox ID set in WSL's Bluetooth settings"
    ;;
  run|relay)
    modprobe btusb < /dev/null || exit 1
    for i in $(seq 1 30); do [ -e /sys/class/bluetooth/hci0 ] && break; sleep 0.5; done
    [ -e /sys/class/bluetooth/hci0 ] || { echo "FAIL: Linux did not see the adapter"; dmesg | grep -iE "bluetooth|firmware" | tail -8; exit 1; }
    sleep 2
    systemctl restart bluetooth < /dev/null; sleep 3
    cd "$2" || exit 1
    if [ "$1" = relay ]; then
      shift 2
      # If Windows kills us without warning (closed window, crash), this still releases the adapter.
      setsid bash "$SELF" guard $$ < /dev/null > /dev/null 2>&1 &
      PYTHONDONTWRITEBYTECODE=1 python3 -u -W ignore relay.py --stdin "$@"
      exit $?
    fi
    if [ -n "$3" ]; then
      PYTHONDONTWRITEBYTECODE=1 timeout -s INT "$3" python3 -u pairing_test.py
    else
      PYTHONDONTWRITEBYTECODE=1 python3 -u pairing_test.py
    fi
    ;;
  guard)
    trap '' HUP INT TERM
    while kill -0 "$2" 2>/dev/null; do sleep 0.5; done
    sleep 1
    pkill -INT -f 'relay.py --stdin' && sleep 3
    release
    ;;
  forget)
    # Moved aside, not deleted: they stay in /var/lib/anypad-forgotten.
    [ -e /sys/class/bluetooth/hci0 ] && { echo "Stop the controller first."; exit 1; }
    systemctl stop bluetooth < /dev/null 2>/dev/null
    shopt -s nullglob
    n=0
    for d in /var/lib/bluetooth/*/??:??:??:??:??:??; do
      keep="/var/lib/anypad-forgotten/$(date +%Y%m%d-%H%M%S)"
      mkdir -p "$keep" && mv "$d" "$keep/" && n=$((n+1))
    done
    echo "saved pairings moved aside: $n"
    ;;
  restore)
    release
    true
    ;;
esac
