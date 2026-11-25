# anypad-ios

Use a cheap USB or 2.4 GHz gamepad with iPhone/iPad games. A computer reads the gamepad and poses as a Bluetooth LE Xbox controller, which iOS already supports.

```
gamepad --(2.4 GHz dongle / USB)--> computer --(Bluetooth LE)--> iPhone / iPad
```

No app, jailbreak or extra hardware is needed.

| Version | How it runs |
|---|---|
| **[Linux](linux/README.md)** | On an installed Linux or an Ubuntu "Try Ubuntu" USB stick |
| **[Windows](windows/README.md)** | Windows plus WSL, using this PC's Bluetooth; no reboot |

## Status

Early. Tried on one laptop, one gamepad (Redgear Pro Series) and an iPad or iPhone.

| Feature | Linux | Windows |
|---|---|---|
| Pairing, recognised by iOS as a game controller | Works | Works |
| Buttons and sticks in a game | Works | Works |
| Rumble from games | Reaches the relay; motors unconfirmed | Reaches the relay; motors unconfirmed |
| Pairing limit (one phone, 3 minutes) | Tested with a stand-in | Works with a real iPad |
| Clearing an outdated pairing | Tested with a stand-in | Tested with a stand-in |
| Occasional disconnects | Seen, cause unknown | None in one 24-minute session |
| Xbox trigger rumble, Share button, real battery level | Not supported | Not supported |

Despite the name, only **Xbox 360-type (XInput) pads** are supported for now.

## Disclaimer

This is an independent hobby project, not affiliated with or endorsed by Microsoft, Apple, Redgear or Intel. Xbox is a trademark of Microsoft. The controller's name and ID are used only so that iOS recognises the input.

## License

[MIT](LICENSE)
