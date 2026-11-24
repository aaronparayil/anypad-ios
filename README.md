# anypad-ios

Use a cheap USB or 2.4 GHz gamepad with iPhone/iPad games. A Linux laptop reads the gamepad and poses as a Bluetooth LE Xbox controller, which iOS already supports.

```
gamepad --(2.4 GHz dongle / USB)--> Linux laptop --(Bluetooth LE)--> iPhone / iPad
```

No app, jailbreak or extra hardware is needed. It also works from an Ubuntu "Try Ubuntu" USB stick, without installing anything.

## Status

Early, and tried on one setup so far: a Redgear Pro Series controller (2.4 GHz dongle), an Intel AX211 adapter and Ubuntu 24.04 (BlueZ 5.72).

| Feature | State |
|---|---|
| Pairing, recognised by iOS as a game controller | Works on real hardware |
| Buttons and sticks in a game | Works on real hardware |
| Retry when Bluetooth won't turn on | Tested with a virtual gamepad only |
| Rumble | Tested with a virtual gamepad only |
| `--le-only` mode | Untested with iOS |
| Occasional disconnects | Seen, cause unknown |
| Xbox trigger rumble, Share button, real battery level | Not supported (battery always shows 100%) |

Despite the name, only **Xbox 360-type (XInput) pads** are supported for now. They use Linux's `xpad` driver, and `lsusb` usually shows `045e:028e`.

## What you need

- A Linux laptop with a Bluetooth adapter that supports LE peripheral mode. Only Ubuntu 24.04 has been tried.
- An iPhone or iPad that supports Xbox Wireless Controllers.
- WSL won't work, because it can't reach the Bluetooth adapter.

## Play

1. On the phone, open **Settings > Bluetooth** and forget any old *Xbox Wireless Controller*. "Try Ubuntu" loses its pairings at every shutdown.
2. Plug in the gamepad or dongle, turn it on, and run this in this folder:
   ```bash
   bash run.sh
   ```
   If the folder is on the Ubuntu boot stick, copy it off first, for example: `cp -r /cdrom/anypad-ios ~/ && cd ~/anypad-ios`.
3. On the phone, tap **Xbox Wireless Controller** in **Settings > Bluetooth** and pair.
4. When the terminal says `phone is listening: play!`, open a game that supports controllers.
5. Stop with `Ctrl+C`. On an installed Ubuntu, undo the Bluetooth change with `bash restore.sh`.

### Options

| Command | What it does |
|---|---|
| `bash run.sh --check` | Shows what the gamepad sends; no Bluetooth |
| `bash run.sh --test-rumble` | Runs the gamepad's motors; no Bluetooth |
| `bash run.sh --rumble 0` | Turns rumble off (`200` doubles it) |
| `bash run.sh --usb-id 1234:abcd` | Uses a gamepad with a different USB ID |
| `bash run.sh --le-only` | Turns off classic Bluetooth, if the phone treats the laptop as a speaker |
| `bash run.sh --dual` | Goes back from `--le-only` |

## Before you run it

- `setup.sh` (called by `run.sh`) edits `/etc/bluetooth/main.conf` and restarts Bluetooth. It keeps a backup, which `restore.sh` puts back.
- It needs `sudo`, for the Bluetooth settings and to read the gamepad.
- **While it runs, it accepts every pairing request without asking**, and trusts the device that paired. Stop it when you're not playing, and remove devices you don't recognise with `bluetoothctl remove <address>`.

## Troubleshooting

- **Keeps saying `waiting for the controller`:** check `lsusb`. Many pads have a mode switch; pick the Xbox/XInput mode.
- **Connected, but buttons do nothing:** run `bash run.sh --check` to see whether the gamepad itself is working.
- **Not in the phone's list:** `sudo btmgmt info` must list `le` and `advertising` under supported settings, and `rfkill list` must show Bluetooth unblocked.
- **Worked before, now won't connect:** forget the device on the phone, then run `bluetoothctl remove <phone address>` on the laptop.
- **iOS pairs but shows no Settings > General > Game Controller:** try the other identity with `bash setup.sh 0b20`, then run again. This one is untested.
- **Is it iOS or the gamepad?** `sudo python3 pairing_test.py` needs no gamepad; it just taps **A** every 2 seconds. Run `setup.sh` first.

## How it works

- `relay.py` reads Linux input events and turns them into Xbox input reports.
- `pairing_test.py` holds the Bluetooth side: a HID-over-GATT service registered with BlueZ over D-Bus, plus advertising and pairing.
- `setup.sh` sets BlueZ's `DeviceID` to `045e:0b13`, the ID of the Xbox Series X|S controller. The report layout follows that controller's, but isn't a byte-for-byte copy.

## Disclaimer

This is an independent hobby project, not affiliated with or endorsed by Microsoft, Apple or Redgear. Xbox is a trademark of Microsoft. The controller's name and ID are used only so that iOS recognises the input.

## License

[MIT](LICENSE)
