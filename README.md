<img src="assets/logo.png" width="96" alt="AnyPad logo: half a gamepad, half wireless waves">

# AnyPad for iPhone and iPad

Use the gamepad you already have, wired or with a 2.4 GHz dongle, to play games on your **iPhone or iPad**. A computer reads the gamepad and poses as a Bluetooth LE Xbox controller, which iOS and iPadOS already support.

```
gamepad --(USB / 2.4 GHz dongle)--> computer --(Bluetooth LE)--> iPhone / iPad
```

No app on the iPhone or iPad, no jailbreak, no extra hardware. Games must support controllers.

| App | How it runs |
|---|---|
| **[Windows](windows/README.md)** | `AnyPad.exe`, one file, plus WSL and usbipd-win; uses this PC's Intel Bluetooth |
| **[Linux](linux/README.md)** | `anypad.py`, or a terminal script; also from an Ubuntu "Try Ubuntu" USB stick |

## Gamepads

| Gamepad | Windows | Linux |
|---|---|---|
| XInput (Xbox-type) | Read exactly; rumble sent | Read exactly; rumble sent |
| DirectInput and other HID pads | Usual button order, or learn the buttons with **Gamepad buttons** | Usual button order; PlayStation and Nintendo drivers understood |

## Status

Early. Tried on one laptop with one gamepad (Redgear Pro Series, XInput), mostly with an iPad Air. An iPhone should work the same way, but hasn't been confirmed in a game.

| Feature | Linux | Windows |
|---|---|---|
| Pairing, recognised as a game controller | Works | Works |
| Buttons and sticks in a game | Works | Works |
| Reconnecting without pairing again | Not tried | Works |
| Starting and stopping with the app | Window not tried yet | Works |
| Other gamepads (DirectInput and so on) | Tested with virtual pads | Mapping tested without a pad |
| Rumble from games | Reaches the relay; motors unconfirmed | Reaches the relay; motors unconfirmed |
| Occasional disconnects | Seen; try `--le-only` | Likely fixed in 0.1.1 by using Bluetooth LE only: none in one 13-minute session |
| Xbox trigger rumble, Share button, real battery level | Not supported | Not supported |

## Resource use (Windows, measured on that laptop)

While playing with the gamepad still, the engine uses about 0.5 % of one CPU core and 20 MB of memory. The window adds about 28 MB and almost no CPU. WSL itself is separate and uses much more memory.

## Disclaimer

This is an independent hobby project, not affiliated with or endorsed by Microsoft, Apple, Intel, Redgear or the Bluetooth SIG. Xbox is a trademark of Microsoft; iPhone and iPad are trademarks of Apple. The controller's name and ID are used only so that iOS recognises the input.

## License

[MIT](LICENSE)
