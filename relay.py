#!/usr/bin/env python3
"""
Relay: forwards a USB gamepad (the Redgear dongle, which Linux sees as an Xbox 360
pad, 045e:028e) to an iPhone/iPad, posing as a Bluetooth Xbox Wireless Controller.

Easiest way to start it:   bash run.sh
Controller check only, no Bluetooth or phone needed:   bash run.sh --check
Rumble motors only, no Bluetooth or phone needed:      bash run.sh --test-rumble

The Bluetooth side is exactly the one that passed pairing_test.py; its classes and
report layout are imported from there unchanged.
"""
import argparse
import fcntl
import os
import re
import signal
import struct
import subprocess
import sys
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

import pairing_test as pt

# ---- Linux input constants (input-event-codes.h) ----
EV_SYN, EV_KEY, EV_ABS, EV_FF = 0x00, 0x01, 0x03, 0x15
FF_RUMBLE = 0x50
SYN_REPORT, SYN_DROPPED = 0, 3
ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ = 0, 1, 2, 3, 4, 5
ABS_HAT0X, ABS_HAT0Y = 16, 17
AXES = (ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ, ABS_HAT0X, ABS_HAT0Y)

KEY_TO_BUTTON = {
    0x130: pt.BTN_A, 0x131: pt.BTN_B, 0x133: pt.BTN_X, 0x134: pt.BTN_Y,
    0x136: pt.BTN_LB, 0x137: pt.BTN_RB,
    0x13A: pt.BTN_VIEW, 0x13B: pt.BTN_MENU, 0x13C: pt.BTN_XBOX,
    0x13D: pt.BTN_LS, 0x13E: pt.BTN_RS,
}
BUTTON_NAMES = {
    pt.BTN_A: "A", pt.BTN_B: "B", pt.BTN_X: "X", pt.BTN_Y: "Y",
    pt.BTN_LB: "LB", pt.BTN_RB: "RB", pt.BTN_VIEW: "View", pt.BTN_MENU: "Menu",
    pt.BTN_XBOX: "Xbox", pt.BTN_LS: "LS", pt.BTN_RS: "RS",
}
# Some pads report the d-pad as four keys (left, right, up, down) instead of a hat.
DPAD_KEYS = {0x2C0: (-1, 0), 0x2C1: (1, 0), 0x2C2: (0, -1), 0x2C3: (0, 1)}

# HID hat value for each (x, y) d-pad position; 0 means released.
HAT = {(0, 0): 0, (0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4,
       (0, 1): 5, (-1, 1): 6, (-1, 0): 7, (-1, -1): 8}

EVENT = struct.Struct("llHHi")           # struct input_event on 64-bit Linux
DEFAULT_RANGE = {ABS_Z: (0, 255), ABS_RZ: (0, 255), ABS_HAT0X: (-1, 1), ABS_HAT0Y: (-1, 1)}
MIN_INTERVAL = 0.010                     # stick/trigger movement: at most 100 reports/s

START = time.monotonic()


def log(msg):
    print("[relay %7.1fs] %s" % (time.monotonic() - START, msg), flush=True)


rumble_seen = False


def bluetooth_log(msg):
    """Bluetooth messages with timestamps; rumble arrives many times a second, so log it once."""
    global rumble_seen
    if msg.startswith("phone wrote Output Report"):
        if rumble_seen:
            return
        rumble_seen = True
        msg = "game is sending rumble (not logged again)"
    log(msg)


pt.log = bluetooth_log


def _ior(nr, size):
    return (2 << 30) | (size << 16) | (ord("E") << 8) | nr


# struct ff_effect (48 bytes): type, id, direction, trigger x2, length, delay, then at
# offset 16 the rumble magnitudes (strong, weak).
FF_EFFECT = struct.Struct("HhHHHHH2xHH28x")
EVIOCSFF = (1 << 30) | (FF_EFFECT.size << 16) | (ord("E") << 8) | 0x80
MAX_RUMBLE_MS = 5000


def parse_rumble(data):
    """Xbox rumble report -> (strong %, weak %, length in ms, repeats), or None if malformed.

    Bytes: enable bits (1 weak, 2 strong, 4/8 triggers), left trigger, right trigger,
    strong, weak (0-100), on-time and off-time in 10 ms units, extra repeats.
    The trigger motors are skipped; this kind of pad has none.
    """
    if len(data) != 8:
        return None
    enable, _, _, strong, weak, on, _, loops = data
    strong = min(strong, 100) if enable & 2 else 0
    weak = min(weak, 100) if enable & 1 else 0
    length = on * 10
    repeats = min(loops + 1, max(1, MAX_RUMBLE_MS // length)) if length else 0
    return strong, weak, length, repeats


class Pad:
    """Holds the gamepad's current state and turns it into an Xbox input report."""

    def __init__(self):
        self.ranges = dict(DEFAULT_RANGE)
        self.reset()

    def reset(self):
        self.axes = {}
        self.keys = set()

    def handle(self, etype, code, value):
        """Apply one event. Returns True if it changed a button or the d-pad."""
        if etype == EV_KEY and (code in KEY_TO_BUTTON or code in DPAD_KEYS):
            if value:
                self.keys.add(code)
            else:
                self.keys.discard(code)
            return True
        if etype == EV_ABS and code in AXES:
            changed = self.axes.get(code) != value
            self.axes[code] = value
            return changed and code in (ABS_HAT0X, ABS_HAT0Y)
        return False

    def _scaled(self, code, top, rest):
        if code not in self.axes:
            return rest
        lo, hi = self.ranges.get(code, (-32768, 32767))
        if hi <= lo:
            return rest
        v = min(max(self.axes[code], lo), hi)
        return (v - lo) * top // (hi - lo)

    def buttons(self):
        return tuple(sorted(KEY_TO_BUTTON[k] for k in self.keys if k in KEY_TO_BUTTON))

    def hat(self):
        x, y = self.axes.get(ABS_HAT0X, 0), self.axes.get(ABS_HAT0Y, 0)
        for key, (dx, dy) in DPAD_KEYS.items():
            if key in self.keys:
                x, y = x + dx, y + dy
        return HAT[((x > 0) - (x < 0), (y > 0) - (y < 0))]

    def report(self):
        # xpad already reports stick Y as "down is positive", which is what HID uses.
        c = pt.STICK_CENTER
        return pt.make_input_report(
            lx=self._scaled(ABS_X, 65535, c), ly=self._scaled(ABS_Y, 65535, c),
            rx=self._scaled(ABS_RX, 65535, c), ry=self._scaled(ABS_RY, 65535, c),
            lt=self._scaled(ABS_Z, 1023, 0), rt=self._scaled(ABS_RZ, 1023, 0),
            hat=self.hat(), buttons=self.buttons())

    def describe(self):
        names = [BUTTON_NAMES[b] for b in self.buttons()]
        lx, ly, rx, ry, lt, rt = struct.unpack_from("<6H", self.report())
        return "L(%5d,%5d) R(%5d,%5d) LT %4d RT %4d dpad %d  %s" % (
            lx, ly, rx, ry, lt, rt, self.hat(), " ".join(names))


def find_pad(text, usb_id):
    """Pick the gamepad's /dev/input/eventN out of /proc/bus/input/devices."""
    by_name = None
    for block in text.split("\n\n"):
        ident = re.search(r"Vendor=(\w+) Product=(\w+)", block)
        name = re.search(r'N: Name="(.*)"', block)
        event = re.search(r"H: Handlers=.*\b(event\d+)", block)
        is_joystick = re.search(r"H: Handlers=.*\bjs\d+", block)
        if not (ident and name and event):
            continue
        found = ("/dev/input/" + event.group(1), name.group(1))
        if "%s:%s" % ident.groups() == usb_id:
            return found
        if by_name is None and is_joystick and re.search(r"x-?box|xinput|redgear", name.group(1), re.I):
            by_name = found
    return by_name


class PadReader:
    """Opens the gamepad, feeds events into a Pad, and reopens it after an unplug."""

    def __init__(self, pad, usb_id, on_change, device=None):
        self.pad, self.usb_id, self.on_change = pad, usb_id, on_change
        self.device = device
        self.fd = None
        self.writable = False
        self.effect_id = -1
        self.rumble_failed = False
        self.waiting_logged = False
        self.resync = False
        self.urgent = False
        self.buf = b""
        self.try_open()
        GLib.timeout_add_seconds(1, self.try_open)

    def try_open(self):
        if self.fd is not None:
            return True
        if self.device:
            found = (self.device, "given with --device")
        else:
            try:
                with open("/proc/bus/input/devices") as f:
                    found = find_pad(f.read(), self.usb_id)
            except OSError:
                found = None
        if found:
            for access in (os.O_RDWR, os.O_RDONLY):
                try:
                    self.fd = os.open(found[0], access | os.O_NONBLOCK)
                    self.writable = access == os.O_RDWR
                    break
                except OSError as e:
                    if access == os.O_RDONLY and not self.waiting_logged:
                        log("cannot open %s: %s" % (found[0], e))
        if self.fd is None:
            if not self.waiting_logged:
                log("waiting for the controller (%s): plug in the dongle, turn the pad on"
                    % self.usb_id)
                self.waiting_logged = True
            return True
        self.waiting_logged = False
        self.buf = b""
        self.resync = self.urgent = False
        self.effect_id = -1
        self.rumble_failed = False
        log("controller found: %s (%s), rumble %s" % (
            found[1], found[0], "offered by driver" if self.has_rumble() else "not available"))
        self.read_current_state()
        self.on_change(True)
        GLib.io_add_watch(self.fd, GLib.PRIORITY_HIGH,
                          GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.on_readable)
        return True

    def has_rumble(self):
        bits = bytearray(16)
        try:
            fcntl.ioctl(self.fd, _ior(0x20 + EV_FF, len(bits)), bits)
        except OSError:
            return False
        return self.writable and bool(bits[FF_RUMBLE // 8] >> (FF_RUMBLE % 8) & 1)

    def rumble(self, strong, weak, length, repeats=1):
        """Run the motors (0-100 %) for length ms; zero strength or length stops them."""
        if self.fd is None or self.rumble_failed:
            return
        try:
            if not (strong or weak) or not length:
                if self.effect_id >= 0:
                    os.write(self.fd, EVENT.pack(0, 0, EV_FF, self.effect_id, 0))
                return
            if self.effect_id < 0 and not self.has_rumble():
                raise OSError("the controller's driver offers no rumble")
            effect = bytearray(FF_EFFECT.pack(
                FF_RUMBLE, self.effect_id, 0, 0, 0, length, 0,
                strong * 0xFFFF // 100, weak * 0xFFFF // 100))
            fcntl.ioctl(self.fd, EVIOCSFF, effect)     # new effect, or update the current one
            self.effect_id = FF_EFFECT.unpack(effect)[1]
            os.write(self.fd, EVENT.pack(0, 0, EV_FF, self.effect_id, repeats))
        except OSError as e:
            # Never let rumble break the buttons and sticks.
            self.rumble_failed = True
            log("rumble switched off: %s" % e)

    def read_current_state(self):
        """Ask the kernel for axis ranges and what is held right now."""
        self.pad.reset()
        for code in AXES:
            buf = bytearray(24)
            try:
                fcntl.ioctl(self.fd, _ior(0x40 + code, 24), buf)
            except OSError:
                continue
            value, lo, hi = struct.unpack_from("3i", buf)
            if hi > lo:
                self.pad.ranges[code] = (lo, hi)
                self.pad.axes[code] = value
        keys = bytearray(96)
        try:
            fcntl.ioctl(self.fd, _ior(0x18, len(keys)), keys)
        except OSError:
            return
        for code in list(KEY_TO_BUTTON) + list(DPAD_KEYS):
            if keys[code // 8] >> (code % 8) & 1:
                self.pad.keys.add(code)

    def on_readable(self, fd, condition):
        data = b""
        if condition & GLib.IO_IN:
            try:
                data = os.read(fd, EVENT.size * 64)
            except BlockingIOError:
                return True
            except OSError:
                data = b""
        if not data:
            log("controller disconnected; released all buttons")
            os.close(fd)
            self.fd = None
            self.pad.reset()
            self.on_change(True)
            return False
        self.feed(data)
        return True

    def feed(self, data):
        self.buf += data
        while len(self.buf) >= EVENT.size:
            _, _, etype, code, value = EVENT.unpack_from(self.buf)
            self.buf = self.buf[EVENT.size:]
            if etype == EV_SYN and code == SYN_DROPPED:
                self.resync = True      # kernel dropped events: ignore up to SYN_REPORT
            elif etype == EV_SYN and code == SYN_REPORT:
                if self.resync:
                    self.resync = False
                    self.read_current_state()
                    self.urgent = True
                self.on_change(self.urgent)
                self.urgent = False
            elif not self.resync:
                self.urgent |= self.pad.handle(etype, code, value)


class Sender:
    """Sends button changes at once; limits the rate of pure stick/trigger movement."""

    def __init__(self, pad, emit):
        self.pad, self.emit = pad, emit
        self.last = None
        self.last_time = 0.0
        self.timer = None

    def update(self, urgent):
        report = self.pad.report()
        if report == self.last:
            return
        wait = MIN_INTERVAL - (time.monotonic() - self.last_time)
        if urgent or wait <= 0:
            self.send(report)
        elif self.timer is None:
            self.timer = GLib.timeout_add(max(1, int(wait * 1000)), self.flush)

    def flush(self):
        self.timer = None
        report = self.pad.report()
        if report != self.last:
            self.send(report)
        return False

    def send(self, report):
        self.last = report
        self.last_time = time.monotonic()
        self.emit(report)


def run_check(args):
    pad = Pad()
    last = [None]

    def show(urgent):
        line = pad.describe()
        if line != last[0]:
            last[0] = line
            print(line, flush=True)

    reader = PadReader(pad, args.usb_id, show, args.device)
    log("controller check: move and press everything, Ctrl+C to stop")
    run_loop(GLib.MainLoop())
    return reader is None


def run_test_rumble(args):
    reader = PadReader(Pad(), args.usb_id, lambda urgent: None, args.device)
    if reader.fd is None:
        return 1
    loop = GLib.MainLoop()
    steps = [("STRONG (left) motor", 100, 0), ("WEAK (right) motor", 0, 100), ("BOTH", 100, 100)]

    def step():
        if not steps or reader.fd is None or reader.rumble_failed:
            loop.quit()
            return False
        name, strong, weak = steps.pop(0)
        log("%s for 1.5 seconds" % name)
        reader.rumble(strong, weak, 1500)
        return True

    step()
    GLib.timeout_add(2500, step)
    run_loop(loop)
    log("done" if not reader.rumble_failed else "rumble is not available")
    return 1 if reader.rumble_failed else 0


def run_loop(loop):
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, loop.quit)
    loop.run()


def power_on(adapter_props):
    """Turn the adapter on if needed, retrying: BlueZ can refuse while it is still settling."""
    for attempt in range(6):
        try:
            if adapter_props.Get(pt.ADAPTER, "Powered"):
                return True
            try:
                subprocess.run(["rfkill", "unblock", "bluetooth"], check=False)
            except OSError:
                pass    # rfkill not installed; powering on may still work
            adapter_props.Set(pt.ADAPTER, "Powered", dbus.Boolean(True))
            return True
        except dbus.exceptions.DBusException as e:
            if attempt == 0:
                log("Bluetooth is off or not ready (%s); retrying" % e)
            time.sleep(1)
    log("FAIL: could not turn Bluetooth on. Turn it on in the top-right menu, or run: "
        "sudo systemctl restart bluetooth   then run this again")
    return False


def run_relay(args):
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    pt.BUS = bus
    pt.check_device_id()

    adapter_path = pt.find_adapter(bus)
    if not adapter_path:
        log("FAIL: no usable Bluetooth adapter found")
        return 1
    adapter_props = dbus.Interface(bus.get_object(pt.BLUEZ, adapter_path), pt.DBUS_PROP)
    old_alias = adapter_props.Get(pt.ADAPTER, "Alias")
    if not power_on(adapter_props):
        return 1
    adapter_props.Set(pt.ADAPTER, "Alias", dbus.String(pt.DEVICE_NAME))
    adapter_props.Set(pt.ADAPTER, "Pairable", dbus.Boolean(True))

    # Same services, order and flags as pairing_test.py, which iOS accepted.
    app = pt.Application(bus)
    battery = pt.Service(app, pt.uuid16(0x180F))
    pt.Characteristic(battery, pt.uuid16(0x2A19), ["read", "notify"], bytes([100]),
                      name="Battery Level")
    hid = pt.Service(app, pt.uuid16(0x1812))
    pt.Characteristic(hid, pt.uuid16(0x2A4A), ["read"], bytes([0x11, 0x01, 0x00, 0x02]),
                      name="HID Information")
    pt.Characteristic(hid, pt.uuid16(0x2A4B), ["read", "encrypt-read"], pt.REPORT_MAP,
                      name="Report Map")
    pt.Characteristic(hid, pt.uuid16(0x2A4C), ["write-without-response"], bytes([0x00]),
                      name="HID Control Point")

    pad = Pad()

    def on_subscribe(on):
        if on:
            log("phone is listening: play!")
            emit(pad.report())

    input_report = pt.Characteristic(
        hid, pt.uuid16(0x2A4D), ["read", "notify", "encrypt-read"], pt.make_input_report(),
        name="Input Report", on_subscribe=on_subscribe)
    pt.Descriptor(input_report, pt.uuid16(0x2908), ["read"], bytes([pt.INPUT_REPORT_ID, 0x01]))
    output_report = pt.Characteristic(
        hid, pt.uuid16(0x2A4D),
        ["read", "write", "write-without-response", "encrypt-read", "encrypt-write"],
        bytes(8), name="Output Report (rumble)", on_write=lambda data: on_rumble(data))
    pt.Descriptor(output_report, pt.uuid16(0x2908), ["read"],
                  bytes([pt.OUTPUT_REPORT_ID, 0x02]))

    def emit(report):
        # Always hand reports to BlueZ. It knows which phones are subscribed, and it keeps
        # a paired phone's subscription across reconnects without telling us again.
        input_report.value = report
        input_report.PropertiesChanged(pt.GATT_CHRC, {"Value": pt.dbus_bytes(report)}, [])

    def on_rumble(data):
        parsed = parse_rumble(data)
        if parsed and args.rumble > 0:
            strong, weak, length, repeats = parsed
            reader.rumble(min(100, strong * args.rumble // 100),
                          min(100, weak * args.rumble // 100), length, repeats)

    adv = pt.Advertisement(bus)
    agent = pt.Agent(bus, pt.Agent.PATH)
    keep = (adv, agent)     # held so they stay exported

    loop = GLib.MainLoop()
    failed = []

    def fail(what):
        def handler(err):
            log("FAIL: %s: %s" % (what, err))
            failed.append(what)
            loop.quit()
        return handler

    agent_mgr = dbus.Interface(bus.get_object(pt.BLUEZ, "/org/bluez"), pt.AGENT_MANAGER)
    agent_mgr.RegisterAgent(pt.Agent.PATH, "NoInputNoOutput")
    agent_mgr.RequestDefaultAgent(pt.Agent.PATH)
    gatt_mgr = dbus.Interface(bus.get_object(pt.BLUEZ, adapter_path), pt.GATT_MANAGER)
    adv_mgr = dbus.Interface(bus.get_object(pt.BLUEZ, adapter_path), pt.ADV_MANAGER)
    gatt_mgr.RegisterApplication(
        pt.ROOT, {}, reply_handler=lambda: log("controller service registered"),
        error_handler=fail("registering GATT service"))
    adv_mgr.RegisterAdvertisement(
        pt.Advertisement.PATH, {},
        reply_handler=lambda: log("ready: on the phone, open Settings > Bluetooth and tap '%s'"
                                  % pt.DEVICE_NAME),
        error_handler=fail("starting LE advertising"))

    def on_device_change(interface, changed, invalidated, path=None):
        if "Connected" in changed:
            if not changed["Connected"]:
                reader.rumble(0, 0, 0)
            log("phone %s" % ("connected" if changed["Connected"] else "DISCONNECTED"))
        if changed.get("Paired"):
            log("phone paired")
            pt.set_trusted(path)
        if changed.get("ServicesResolved"):
            emit(pad.report())

    bus.add_signal_receiver(on_device_change, dbus_interface=pt.DBUS_PROP,
                            signal_name="PropertiesChanged", arg0=pt.DEVICE,
                            path_keyword="path")

    def on_adapter_change(interface, changed, invalidated):
        if "Powered" in changed and not changed["Powered"]:
            log("the LAPTOP's Bluetooth was turned off; press Ctrl+C and run again")

    bus.add_signal_receiver(on_adapter_change, dbus_interface=pt.DBUS_PROP,
                            signal_name="PropertiesChanged", arg0=pt.ADAPTER)

    sender = Sender(pad, emit)
    reader = PadReader(pad, args.usb_id, sender.update, args.device)
    try:
        run_loop(loop)
    finally:
        log("stopping")
        reader.rumble(0, 0, 0)
        pad.reset()
        sender.update(True)
        for call in (lambda: adv_mgr.UnregisterAdvertisement(pt.Advertisement.PATH),
                     lambda: gatt_mgr.UnregisterApplication(pt.ROOT),
                     lambda: agent_mgr.UnregisterAgent(pt.Agent.PATH),
                     lambda: adapter_props.Set(pt.ADAPTER, "Alias", old_alias)):
            try:
                call()
            except dbus.exceptions.DBusException:
                pass
    del keep
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description="Forward a USB gamepad to iOS over Bluetooth")
    ap.add_argument("--check", action="store_true",
                    help="only show what the controller is doing; no Bluetooth")
    ap.add_argument("--test-rumble", action="store_true",
                    help="only run the controller's motors; no Bluetooth")
    ap.add_argument("--rumble", type=int, default=100, metavar="PERCENT",
                    help="rumble strength: 0 is off, 200 is double (default 100)")
    ap.add_argument("--usb-id", default="045e:028e", help="controller USB ID (from lsusb)")
    ap.add_argument("--device", help="use this /dev/input/eventN instead of searching")
    args = ap.parse_args()
    if os.geteuid() != 0:
        log("run with sudo")
        return 1
    if args.test_rumble:
        return run_test_rumble(args)
    return run_check(args) if args.check else run_relay(args)


if __name__ == "__main__":
    sys.exit(main())
