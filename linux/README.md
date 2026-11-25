# AnyPad on Linux, for iPhone and iPad

The gamepad plugs into the Linux laptop, and the laptop poses as a Bluetooth LE Xbox controller. It also runs from an Ubuntu "Try Ubuntu" USB stick, without installing anything.

## What you need

- A Bluetooth adapter that supports LE peripheral mode. Tried on one laptop: Intel AX211, Ubuntu 24.04 (BlueZ 5.72).
- A gamepad. Xbox-type pads are read exactly; other pads use the usual button order, and PlayStation and Nintendo drivers are understood.

## Play with the app

```bash
python3 anypad.py
```

It needs GTK 3 (`sudo apt install python3-gi gir1.2-gtk-3.0`; Ubuntu Desktop usually has it). Press **Start**, enter your password, and pair from the iPhone or iPad; press **Stop** when you're done. `bash install-app.sh` adds it to your applications menu. Only the relay runs as root. **The window hasn't been tried on a real desktop yet.**

## Play in a terminal

1. On the phone, open **Settings > Bluetooth** and forget any old *Xbox Wireless Controller*. "Try Ubuntu" loses its pairings at every shutdown.
2. Plug in the gamepad or dongle, turn it on, and run this in this folder:
   ```bash
   bash run.sh
   ```
   From the Ubuntu boot stick, copy the folder off first, for example: `cp -r /cdrom/anypad-ios ~/ && cd ~/anypad-ios/linux`.
3. On the phone, tap **Xbox Wireless Controller** in **Settings > Bluetooth** and pair.
4. When the terminal says `phone is listening: play!`, open a game that supports controllers.
5. Stop with `Ctrl+C`. On an installed Ubuntu, undo the Bluetooth change with `bash restore.sh`.

| Command | What it does |
|---|---|
| `bash run.sh --check` | Shows what the gamepad sends; no Bluetooth |
| `bash run.sh --test-rumble` | Runs the gamepad's motors; no Bluetooth |
| `bash run.sh --rumble 0` | Turns rumble off (`200` doubles it) |
| `bash run.sh --usb-id 1234:abcd` | Uses a gamepad with a different USB ID |
| `bash run.sh --pair-seconds 0` | Allows no new pairing, only a phone that paired earlier |
| `bash run.sh --le-only` | Turns off classic Bluetooth, if the phone treats the laptop as a speaker. Untested with iOS |
| `bash run.sh --dual` | Goes back from `--le-only` |

## Before you run it

- `setup.sh` (called by `run.sh`) edits `/etc/bluetooth/main.conf` and restarts Bluetooth. It keeps a backup, which `restore.sh` puts back.
- It needs `sudo`, for the Bluetooth settings and to read the gamepad.
- **Pairing has no PIN, like a real controller, so it is limited instead:** after each start, one phone may pair, for up to 3 minutes. Then new pairings are refused; a phone that already paired can still reconnect. Start it only when your own phone is ready, and check that the phone that paired is yours.
- It refuses the laptop's other Bluetooth services (audio, files, network) to devices the laptop doesn't already trust. If you used an early version on an installed Ubuntu, remove old phones with `bluetoothctl remove <address>`.
- A stranger nearby can still try to connect without pairing. Whether button presses could be overheard that way hasn't been tested.

## Troubleshooting

- **Keeps saying `waiting for the controller`:** check `lsusb`. Many pads have a mode switch; pick the Xbox/XInput mode.
- **Connected, but buttons do nothing:** run `bash run.sh --check`.
- **Not in the phone's list:** `sudo btmgmt info` must list `le` and `advertising` under supported settings, and `rfkill list` must show Bluetooth unblocked.
- **Pairing fails:** pairing may have closed; stop and run again.
- **The phone connects and drops every second:** the phone forgot this controller but the laptop didn't. While pairing is open the relay clears the old entry; otherwise forget it on the phone and run again, or use `bluetoothctl remove <phone address>`.
- **iOS pairs but shows no Settings > General > Game Controller:** try `bash setup.sh 0b20`, then run again. Untested.
- **Is it iOS or the gamepad?** `sudo python3 pairing_test.py` needs no gamepad; it taps **A** every 2 seconds. Run `setup.sh` first.

## Files

- `relay.py` reads Linux input events (or the Windows program's input with `--stdin`) and turns them into Xbox input reports.
- `pairing_test.py` holds the Bluetooth side: a HID-over-GATT service registered with BlueZ over D-Bus, advertising and the pairing limit.
- `setup.sh` sets BlueZ's `DeviceID` to `045e:0b13`, the ID of the Xbox Series X|S controller. The report layout follows that controller's, but isn't a byte-for-byte copy.
- `anypad.py` is the window, `app_engine.sh` what it runs as root, `install-app.sh` the menu entry.
- `tests/` runs the relay against a stand-in for BlueZ and a virtual gamepad. As root on Linux, for example: `python3 tests/test_pairing.py "$PWD" "$PWD/tests"`.
