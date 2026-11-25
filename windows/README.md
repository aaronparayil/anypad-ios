# anypad-ios on Windows

Windows reads the gamepad and sends it to the Linux relay in WSL, which poses as the Bluetooth controller using this PC's adapter. No reboot or Ubuntu stick.

**Works end to end on one PC and one iPad** (25 Nov 2026): an Intel AX211 adapter, WSL 3.0.3, Ubuntu 26.04 (BlueZ 5.85) and a Redgear Pro Series controller. Not tried anywhere else.

## What you need

- Windows 11 with WSL 2, and an Ubuntu distro as the **default** WSL distro. In it: `bluez`, `python3-dbus` and `python3-gi` (`sudo apt install bluez python3-dbus python3-gi`).
- [usbipd-win](https://github.com/dorssel/usbipd-win). Its installer opens TCP port 3240 to your local network.
- An **Intel** USB Bluetooth adapter (`usbipd list` shows `8087:...`). It's found automatically. Others are refused.
- An Xbox 360-type (XInput) gamepad.

## Play

1. Open **AnyPad.exe**. It's one file, with nothing else to copy. It lists what's ready and what isn't, with a link to fix most of it.
2. Turn Bluetooth **off** in Windows, and remove any phone from Windows' **Settings > Bluetooth & devices**. Windows won't release the adapter while one of its own Bluetooth devices is in use; headphones can block it too.
3. Press **Start** and approve the admin prompt.
4. On the iPhone or iPad, tap **Xbox Wireless Controller** in **Settings > Bluetooth** and pair within 3 minutes. When the window says **Connected: play!**, open a game.
5. Press **Stop** (or close the window) and approve the prompt, so the adapter is unshared. Then turn Windows Bluetooth back on.

To build it, run `build.cmd`. It uses the C# compiler that ships with Windows.

### In a terminal

`controller.exe`, from a clone of this repo, is the same engine without the window. Press **Q** to stop it.

| Command | What it does |
|---|---|
| `controller.exe` | Plays; explains itself and asks first |
| `controller.exe --stop` | Stops a running one from another window |
| `controller.exe --check` | Shows what the gamepad sends; no Bluetooth |
| `controller.exe --test-rumble` | Runs the gamepad's motors; no Bluetooth |
| `controller.exe --preflight` | Checks whether it's safe to start; changes nothing |
| `controller.exe --why` | Shows why Windows last refused to release the adapter |
| `controller.exe --forget` | Moves saved phone pairings aside so a phone can pair afresh |
| `--busid`, `--rumble`, `--pair-seconds` | Adapter bus ID (normally found automatically), rumble strength, pairing time |

## Before you run it

- **Windows has no Bluetooth while it runs.** Earbuds, and Bluetooth mice and keyboards, disconnect.
- **Network:** usbipd offers a shared adapter to your local network. While it runs, the program adds a firewall rule so only WSL can reach it, and removes the rule and the share when you stop. If the program is killed, the share and the rule both stay until you run and stop it again, or run `usbipd unbind` and delete the rule. If you share the adapter yourself, that rule isn't there. Mirrored WSL networking isn't supported. Adding and removing the rule, and unsharing on stop, worked on the PC above.
- The admin prompt shows an unknown publisher, because the program isn't signed. Build it yourself if you'd rather not trust a download.
- Inside WSL it edits `/etc/bluetooth/main.conf` and restores it afterwards.
- Pairing has no PIN but is limited to one phone for 3 minutes; see [../linux/README.md](../linux/README.md).
- It writes the last run's messages to `%LOCALAPPDATA%nypad-ios\last-run.log`, without Bluetooth addresses. Device names can appear, so check before sharing it.
- If the program is killed, a guard in WSL releases the adapter. Tested on the PC above: back in 2 seconds.
- **Don't use usbipd's `--force`.** Repeated forced shares left that PC without a Bluetooth radio until a restart.

## Known limits

- AnyPad's window is new: its checks work on that PC, but Start and Stop haven't been used for a game yet. The engine under it has.
- Only one adapter, gamepad, PC and iPad tried. Not tested: reconnecting without pairing again, and long sessions.
- Clearing an outdated pairing automatically is only tested with a stand-in.
- The Xbox button uses an undocumented Windows call. Rumble is sent to the gamepad; whether the motors respond depends on it.
- Releasing an adapter left attached by an earlier run hasn't been tried on hardware.

## Files

- `AnyPad.cs`: the window. `controller.cs`: the engine, used by both programs. `in_wsl.sh`: the WSL side. `make_icon.py` draws `AnyPad.ico`.
- AnyPad writes the WSL files it carries to `%LOCALAPPDATA%\anypad-ios\app` each time it opens.
- `keyboard-test/`: a separate experiment, where Windows itself poses as a Bluetooth keyboard. It worked on one phone. Its gamepad mode didn't work as a controller on iOS.
- `echo_frames.py`: checks the Windows-to-WSL link, with `controller.exe --child "wsl.exe -u root -- python3 <path>"`.
