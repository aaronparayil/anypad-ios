<img src="assets/logo.png" width="96" alt="AnyPad logo: half a gamepad, half wireless waves">

# AnyPad for iPhone, iPad and Android

Use the gamepad you already have, wired or with a 2.4 GHz dongle, to play games on your **iPhone, iPad or Android phone or tablet**. A computer reads the gamepad and poses as a Bluetooth LE Xbox controller, which iOS, iPadOS and Android already support.

```
gamepad --(USB / 2.4 GHz dongle)--> computer --(Bluetooth LE)--> iPhone / iPad / Android
```

No app on the phone, no jailbreak or root, no extra hardware. Games must support controllers.

## Four apps

Pick the one for your computer and your phone. Each pair is the same program with different instructions.

| | For iPhone and iPad | For Android |
|---|---|---|
| **[Windows](windows/README.md)**: one file, plus WSL and usbipd-win; uses this PC's Intel Bluetooth | `AnyPad-iOS.exe` | `AnyPad-Android.exe` |
| **[Linux](linux/README.md)**: a window or a terminal script; also from an Ubuntu "Try Ubuntu" USB stick | `AnyPad-Linux-iOS` | `AnyPad-Linux-Android` |

Download them from [Releases](https://github.com/aaronparayil/anypad-ios/releases). The Android apps use only Bluetooth LE while they run, because Android may otherwise pair over classic Bluetooth, where there's no controller.

**Android without a computer:** many Android phones and tablets accept a USB gamepad, or its 2.4 GHz dongle, directly through a USB-C (OTG) adapter. Try that first; AnyPad is for when it doesn't work.

## Gamepads

| Gamepad | Windows | Linux |
|---|---|---|
| XInput (Xbox-type) | Read exactly; rumble sent | Read exactly; rumble sent |
| DirectInput and other HID pads | Usual button order, or learn the buttons with **Gamepad buttons** | Usual button order; PlayStation and Nintendo drivers understood |

## Status

Early. Tried on one laptop with one gamepad (Redgear Pro Series, XInput), mostly with an iPad Air.

| Feature | iPhone and iPad | Android |
|---|---|---|
| Pairing, recognised as a game controller | Works (iPad) | Not tried on a device yet |
| Buttons and sticks in a game | Works (iPad) | Checked with the Linux kernel's own drivers and Android's button layout file: every button, stick and trigger lands in the right place |
| Rumble from games | Reaches the relay; motors unconfirmed | Checked with the kernel's Xbox driver: reaches the relay; motors unconfirmed |
| Reconnecting without pairing again | Works on Windows | Not tried |
| Occasional disconnects | None in one 13-minute session with Bluetooth LE only | Not tried |
| Xbox trigger rumble, Share button, real battery level | Not supported | Not supported |

| App part | Linux | Windows |
|---|---|---|
| Starting and stopping with the window | Tested on a virtual screen, not on a real desktop | Works |
| Other gamepads (DirectInput and so on) | Tested with virtual pads | Mapping tested without a pad |

## Resource use (Windows, measured on that laptop)

While playing with the gamepad still, the engine uses about 0.5 % of one CPU core and 20 MB of memory. The window adds about 28 MB and almost no CPU. WSL itself is separate and uses much more memory.

## Disclaimer

This is an independent hobby project, not affiliated with or endorsed by Microsoft, Apple, Google, Intel, Redgear or the Bluetooth SIG. Xbox is a trademark of Microsoft; iPhone and iPad are trademarks of Apple; Android is a trademark of Google. The controller's name and ID are used only so that phones recognise the input.

## License

[MIT](LICENSE)
