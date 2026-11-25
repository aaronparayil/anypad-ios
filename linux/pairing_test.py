#!/usr/bin/env python3
"""
Pairing test: make this Ubuntu laptop look like an Xbox Wireless Controller
over Bluetooth LE (HID over GATT), so you can check whether iOS/iPadOS accepts it.

No real controller is involved yet. Once a phone subscribes to input, the script
taps the "A" button every 2 seconds so you can watch the input arrive on the phone.

Run setup.sh first (it sets the USB vendor/product ID that BlueZ reports), then:
    sudo python3 pairing_test.py
Stop with Ctrl+C.
"""
import os
import signal
import struct
import sys
import time

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

DEVICE_NAME = "Xbox Wireless Controller"
APPEARANCE_GAMEPAD = 0x03C4

BLUEZ = "org.bluez"
DBUS_OM = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP = "org.freedesktop.DBus.Properties"
ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
GATT_MANAGER = "org.bluez.GattManager1"
ADV_MANAGER = "org.bluez.LEAdvertisingManager1"
AGENT_MANAGER = "org.bluez.AgentManager1"
GATT_SERVICE = "org.bluez.GattService1"
GATT_CHRC = "org.bluez.GattCharacteristic1"
GATT_DESC = "org.bluez.GattDescriptor1"
LE_ADV = "org.bluez.LEAdvertisement1"
AGENT = "org.bluez.Agent1"

ROOT = "/xboxtest"


def uuid16(x):
    return "0000%04x-0000-1000-8000-00805f9b34fb" % x


def dbus_bytes(data):
    return dbus.Array([dbus.Byte(b) for b in data], signature="y")


# HID report descriptor modelled on the Xbox Series X|S controller's Bluetooth LE layout.
# Input report 1 (16 bytes): LX LY RX RY (16-bit each), LT RT (10-bit + 6 pad each),
# hat (4 bits + 4 pad), 15 buttons + 1 pad, Share/Record (1 bit + 7 pad).
# Output report 3 (8 bytes): rumble.
REPORT_MAP = bytes([
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x05,        # Usage (Game Pad)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        #   Report ID (1)
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x15, 0x00,        #     Logical Min (0)
    0x27, 0xFF, 0xFF, 0x00, 0x00,  # Logical Max (65535)
    0x95, 0x02,        #     Report Count (2)
    0x75, 0x10,        #     Report Size (16)
    0x81, 0x02,        #     Input (Data,Var,Abs)
    0xC0,              #   End Collection
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    0x09, 0x32,        #     Usage (Z)
    0x09, 0x35,        #     Usage (Rz)
    0x15, 0x00,        #     Logical Min (0)
    0x27, 0xFF, 0xFF, 0x00, 0x00,  # Logical Max (65535)
    0x95, 0x02,        #     Report Count (2)
    0x75, 0x10,        #     Report Size (16)
    0x81, 0x02,        #     Input (Data,Var,Abs)
    0xC0,              #   End Collection
    0x05, 0x02,        #   Usage Page (Simulation Controls)
    0x09, 0xC5,        #   Usage (Brake)
    0x15, 0x00,        #   Logical Min (0)
    0x26, 0xFF, 0x03,  #   Logical Max (1023)
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x0A,        #   Report Size (10)
    0x81, 0x02,        #   Input (Data,Var,Abs)
    0x15, 0x00,        #   Logical Min (0)
    0x25, 0x00,        #   Logical Max (0)
    0x75, 0x06,        #   Report Size (6)
    0x95, 0x01,        #   Report Count (1)
    0x81, 0x03,        #   Input (Const)  padding
    0x05, 0x02,        #   Usage Page (Simulation Controls)
    0x09, 0xC4,        #   Usage (Accelerator)
    0x15, 0x00,        #   Logical Min (0)
    0x26, 0xFF, 0x03,  #   Logical Max (1023)
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x0A,        #   Report Size (10)
    0x81, 0x02,        #   Input (Data,Var,Abs)
    0x15, 0x00,        #   Logical Min (0)
    0x25, 0x00,        #   Logical Max (0)
    0x75, 0x06,        #   Report Size (6)
    0x95, 0x01,        #   Report Count (1)
    0x81, 0x03,        #   Input (Const)  padding
    0x05, 0x01,        #   Usage Page (Generic Desktop)
    0x09, 0x39,        #   Usage (Hat switch)
    0x15, 0x01,        #   Logical Min (1)
    0x25, 0x08,        #   Logical Max (8)
    0x35, 0x00,        #   Physical Min (0)
    0x46, 0x3B, 0x01,  #   Physical Max (315)
    0x66, 0x14, 0x00,  #   Unit (Degrees)
    0x75, 0x04,        #   Report Size (4)
    0x95, 0x01,        #   Report Count (1)
    0x81, 0x42,        #   Input (Data,Var,Abs,Null State)
    0x75, 0x04,        #   Report Size (4)
    0x95, 0x01,        #   Report Count (1)
    0x15, 0x00,        #   Logical Min (0)
    0x25, 0x00,        #   Logical Max (0)
    0x35, 0x00,        #   Physical Min (0)
    0x45, 0x00,        #   Physical Max (0)
    0x65, 0x00,        #   Unit (None)
    0x81, 0x03,        #   Input (Const)  padding
    0x05, 0x09,        #   Usage Page (Button)
    0x19, 0x01,        #   Usage Min (1)
    0x29, 0x0F,        #   Usage Max (15)
    0x15, 0x00,        #   Logical Min (0)
    0x25, 0x01,        #   Logical Max (1)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x0F,        #   Report Count (15)
    0x81, 0x02,        #   Input (Data,Var,Abs)
    0x15, 0x00,        #   Logical Min (0)
    0x25, 0x00,        #   Logical Max (0)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x01,        #   Report Count (1)
    0x81, 0x03,        #   Input (Const)  padding
    0x05, 0x0C,        #   Usage Page (Consumer)
    0x0A, 0xB2, 0x00,  #   Usage (Record)  = Share button
    0x15, 0x00,        #   Logical Min (0)
    0x25, 0x01,        #   Logical Max (1)
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x01,        #   Report Size (1)
    0x81, 0x02,        #   Input (Data,Var,Abs)
    0x15, 0x00,        #   Logical Min (0)
    0x25, 0x00,        #   Logical Max (0)
    0x75, 0x07,        #   Report Size (7)
    0x95, 0x01,        #   Report Count (1)
    0x81, 0x03,        #   Input (Const)  padding
    0x05, 0x0F,        #   Usage Page (Physical Interface / haptics)
    0x09, 0x21,        #   Usage (Set Effect Report)
    0x85, 0x03,        #   Report ID (3)
    0xA1, 0x02,        #   Collection (Logical)
    0x09, 0x97,        #     Usage (DC Enable Actuators)
    0x15, 0x00,        #     Logical Min (0)
    0x25, 0x01,        #     Logical Max (1)
    0x75, 0x04,        #     Report Size (4)
    0x95, 0x01,        #     Report Count (1)
    0x91, 0x02,        #     Output (Data,Var,Abs)
    0x15, 0x00,        #     Logical Min (0)
    0x25, 0x00,        #     Logical Max (0)
    0x75, 0x04,        #     Report Size (4)
    0x95, 0x01,        #     Report Count (1)
    0x91, 0x03,        #     Output (Const)  padding
    0x09, 0x70,        #     Usage (Magnitude)
    0x15, 0x00,        #     Logical Min (0)
    0x25, 0x64,        #     Logical Max (100)
    0x75, 0x08,        #     Report Size (8)
    0x95, 0x04,        #     Report Count (4)
    0x91, 0x02,        #     Output (Data,Var,Abs)
    0x09, 0x50,        #     Usage (Duration)
    0x66, 0x01, 0x10,  #     Unit (Seconds)
    0x55, 0x0E,        #     Unit Exponent (-2)
    0x15, 0x00,        #     Logical Min (0)
    0x26, 0xFF, 0x00,  #     Logical Max (255)
    0x75, 0x08,        #     Report Size (8)
    0x95, 0x01,        #     Report Count (1)
    0x91, 0x02,        #     Output (Data,Var,Abs)
    0x09, 0xA7,        #     Usage (Start Delay)
    0x15, 0x00,        #     Logical Min (0)
    0x26, 0xFF, 0x00,  #     Logical Max (255)
    0x75, 0x08,        #     Report Size (8)
    0x95, 0x01,        #     Report Count (1)
    0x91, 0x02,        #     Output (Data,Var,Abs)
    0x65, 0x00,        #     Unit (None)
    0x55, 0x00,        #     Unit Exponent (0)
    0x09, 0x7C,        #     Usage (Loop Count)
    0x15, 0x00,        #     Logical Min (0)
    0x26, 0xFF, 0x00,  #     Logical Max (255)
    0x75, 0x08,        #     Report Size (8)
    0x95, 0x01,        #     Report Count (1)
    0x91, 0x02,        #     Output (Data,Var,Abs)
    0xC0,              #   End Collection
    0xC0,              # End Collection
])

INPUT_REPORT_ID = 0x01
OUTPUT_REPORT_ID = 0x03
STICK_CENTER = 32768

# Button bits in the 15-button field (byte 0 / byte 1 of the 2-byte field).
BTN_A, BTN_B, BTN_X, BTN_Y = 0, 1, 3, 4
BTN_LB, BTN_RB = 6, 7
BTN_VIEW, BTN_MENU, BTN_XBOX, BTN_LS, BTN_RS = 10, 11, 12, 13, 14


def make_input_report(lx=STICK_CENTER, ly=STICK_CENTER, rx=STICK_CENTER, ry=STICK_CENTER,
                      lt=0, rt=0, hat=0, buttons=(), share=False):
    """Build the 16-byte input report (no report ID byte; HOGP carries the ID separately)."""
    mask = 0
    for b in buttons:
        mask |= 1 << b
    return struct.pack("<HHHHHHBHB", lx, ly, rx, ry, lt & 0x3FF, rt & 0x3FF,
                       hat & 0x0F, mask & 0x7FFF, 1 if share else 0)


class InvalidArgs(dbus.exceptions.DBusException):
    _dbus_error_name = "org.freedesktop.DBus.Error.InvalidArgs"


class Application(dbus.service.Object):
    def __init__(self, bus):
        self.services = []
        super().__init__(bus, ROOT)

    @dbus.service.method(DBUS_OM, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        out = {}
        for s in self.services:
            out[s.get_path()] = s.get_properties()
            for c in s.chrcs:
                out[c.get_path()] = c.get_properties()
                for d in c.descs:
                    out[d.get_path()] = d.get_properties()
        return out


class Service(dbus.service.Object):
    def __init__(self, app, uuid):
        self.path = "%s/service%d" % (ROOT, len(app.services))
        self.uuid = uuid
        self.chrcs = []
        super().__init__(app.connection, self.path)
        app.services.append(self)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {GATT_SERVICE: {
            "UUID": self.uuid,
            "Primary": dbus.Boolean(True),
            "Characteristics": dbus.Array([c.get_path() for c in self.chrcs], signature="o"),
        }}

    @dbus.service.method(DBUS_PROP, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE:
            raise InvalidArgs()
        return self.get_properties()[GATT_SERVICE]


class Characteristic(dbus.service.Object):
    def __init__(self, service, uuid, flags, value=b"", name="", on_write=None, on_subscribe=None):
        self.path = "%s/char%d" % (service.path, len(service.chrcs))
        self.service = service
        self.uuid = uuid
        self.flags = flags
        self.value = bytes(value)
        self.name = name or uuid
        self.on_write = on_write
        self.on_subscribe = on_subscribe
        self.descs = []
        self.notifying = False
        super().__init__(service.connection, self.path)
        service.chrcs.append(self)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {GATT_CHRC: {
            "Service": self.service.get_path(),
            "UUID": self.uuid,
            "Flags": dbus.Array(self.flags, signature="s"),
            "Descriptors": dbus.Array([d.get_path() for d in self.descs], signature="o"),
        }}

    @dbus.service.method(DBUS_PROP, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_CHRC:
            raise InvalidArgs()
        return self.get_properties()[GATT_CHRC]

    @dbus.service.method(GATT_CHRC, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        offset = int(options.get("offset", 0))
        if offset == 0:
            log("phone read %s" % self.name)
        return dbus_bytes(self.value[offset:])

    @dbus.service.method(GATT_CHRC, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        data = bytes(value)
        self.value = data
        log("phone wrote %s: %s" % (self.name, data.hex()))
        if self.on_write:
            self.on_write(data)

    @dbus.service.method(GATT_CHRC)
    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        log("phone subscribed to %s" % self.name)
        if self.on_subscribe:
            self.on_subscribe(True)

    @dbus.service.method(GATT_CHRC)
    def StopNotify(self):
        self.notifying = False
        log("phone unsubscribed from %s" % self.name)
        if self.on_subscribe:
            self.on_subscribe(False)

    @dbus.service.signal(DBUS_PROP, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    def notify(self, data):
        self.value = bytes(data)
        if self.notifying:
            self.PropertiesChanged(GATT_CHRC, {"Value": dbus_bytes(self.value)}, [])


class Descriptor(dbus.service.Object):
    def __init__(self, chrc, uuid, flags, value):
        self.path = "%s/desc%d" % (chrc.path, len(chrc.descs))
        self.chrc = chrc
        self.uuid = uuid
        self.flags = flags
        self.value = bytes(value)
        super().__init__(chrc.connection, self.path)
        chrc.descs.append(self)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def get_properties(self):
        return {GATT_DESC: {
            "Characteristic": self.chrc.get_path(),
            "UUID": self.uuid,
            "Flags": dbus.Array(self.flags, signature="s"),
        }}

    @dbus.service.method(DBUS_PROP, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_DESC:
            raise InvalidArgs()
        return self.get_properties()[GATT_DESC]

    @dbus.service.method(GATT_DESC, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        offset = int(options.get("offset", 0))
        return dbus_bytes(self.value[offset:])


class Advertisement(dbus.service.Object):
    PATH = ROOT + "/adv0"

    def __init__(self, bus):
        super().__init__(bus, self.PATH)

    def get_properties(self):
        return {LE_ADV: {
            "Type": "peripheral",
            "ServiceUUIDs": dbus.Array([uuid16(0x1812)], signature="s"),
            "LocalName": dbus.String(DEVICE_NAME),
            "Appearance": dbus.UInt16(APPEARANCE_GAMEPAD),
            "Discoverable": dbus.Boolean(True),
        }}

    @dbus.service.method(DBUS_PROP, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADV:
            raise InvalidArgs()
        return self.get_properties()[LE_ADV]

    @dbus.service.method(LE_ADV)
    def Release(self):
        log("advertisement released by BlueZ")


class Rejected(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class PairingGate:
    """Lets one phone pair, for a limited time after start, and nothing else.

    Two layers, because either alone has a gap: the agent refuses requests, and the
    adapter's Pairable switch is turned off. The kernel can accept classic Bluetooth
    "Just Works" pairings without asking the agent, so the switch has to go off too.
    A phone that is already paired can reconnect at any time.
    """
    SETTLE_SECONDS = 5      # let the phone finish exchanging keys before locking
    CLAIM_SECONDS = 40      # a pairing attempt that stalls frees the slot again

    def __init__(self, adapter_props, seconds):
        self.props = adapter_props
        self.seconds = seconds
        self.is_open = False
        self.claimed = None
        self.claim_timer = None
        self.old_pairable = bool(adapter_props.Get(ADAPTER, "Pairable"))
        # Closed until start(), so nothing can pair before the agent is in place.
        self.set_pairable(False)

    def set_pairable(self, on):
        # BlueZ answers Busy while a previous change is still being applied.
        for attempt in range(20):
            try:
                self.props.Set(ADAPTER, "Pairable", dbus.Boolean(on))
                return
            except dbus.exceptions.DBusException as e:
                busy = e.get_dbus_name() in ("org.bluez.Error.Busy", "org.bluez.Error.InProgress",
                                             "org.bluez.Error.NotReady")
                if not busy or attempt == 19:
                    raise
                time.sleep(0.15)

    def start(self):
        if self.seconds <= 0:
            log("pairing is off: only a phone that is already paired can connect")
            return
        try:
            self.set_pairable(True)
        except dbus.exceptions.DBusException as e:
            log("FAIL: could not open pairing (%s); run again" % e)
            return
        self.is_open = True
        log("pairing is open for %d seconds, for one phone" % self.seconds)
        GLib.timeout_add_seconds(self.seconds, self.on_timeout)

    def on_timeout(self, final=False):
        if self.claimed and self.is_open and not final:
            # A phone is mid-pairing: let that one finish, once, before closing.
            GLib.timeout_add_seconds(self.CLAIM_SECONDS, self.on_timeout, True)
        else:
            self.close("time is up")
        return False

    def allow(self, device):
        device = str(device)
        if self.is_open and self.claimed in (None, device):
            self.claimed = device
            self.stop_claim_timer()
            self.claim_timer = GLib.timeout_add_seconds(self.CLAIM_SECONDS, self.release)
            log("accepting pairing")
            return
        log("REFUSED pairing from %s" % device.split("/")[-1])
        raise Rejected("pairing is closed")

    def stop_claim_timer(self):
        if self.claim_timer is not None:
            GLib.source_remove(self.claim_timer)
            self.claim_timer = None

    def release(self):
        self.claim_timer = None
        self.claimed = None
        return False

    def cancelled(self):
        self.stop_claim_timer()
        self.claimed = None

    def paired(self, device):
        """Some device finished pairing: take no new ones, then lock the adapter."""
        device = str(device)
        self.stop_claim_timer()
        if not self.is_open:
            log("WARNING: %s paired while pairing was closed. If it isn't yours: "
                "bluetoothctl remove %s" % (device.split("/")[-1], address_of(device)))
            return
        if self.claimed not in (None, device):
            log("WARNING: %s paired as well. If it isn't yours: bluetoothctl remove %s"
                % (device.split("/")[-1], address_of(device)))
        self.is_open = False
        self.claimed = device
        GLib.timeout_add_seconds(self.SETTLE_SECONDS, self.on_settled)

    def on_settled(self):
        self.close("a phone has paired", force=True)
        return False

    def close(self, why, force=False):
        if not self.is_open and not force:
            return
        self.is_open = False
        try:
            self.set_pairable(False)
            log("pairing is closed (%s); to pair another phone, stop and run again" % why)
        except dbus.exceptions.DBusException as e:
            log("WARNING: could not turn pairing off (%s). Stop with Ctrl+C when not in use" % e)

    def restore(self):
        self.is_open = False
        self.set_pairable(self.old_pairable)


def address_of(device_path):
    return device_path.split("/")[-1].replace("dev_", "").replace("_", ":")


class Agent(dbus.service.Object):
    """Answers pairing requests ("Just Works", like a real controller) as the gate decides.

    Devices are not marked trusted, and every other Bluetooth service on the laptop
    (audio, files, network) is refused: the controller needs none of them.
    """
    PATH = ROOT + "/agent"

    def __init__(self, bus, path, gate):
        super().__init__(bus, path)
        self.gate = gate
        self.refused = set()

    @dbus.service.method(AGENT)
    def Release(self):
        pass

    @dbus.service.method(AGENT, in_signature="os")
    def AuthorizeService(self, device, uuid):
        if uuid not in self.refused:
            self.refused.add(uuid)
            log("refused other Bluetooth service %s (not needed for the controller)" % uuid)
        raise Rejected("only the controller is offered")

    @dbus.service.method(AGENT, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        raise Rejected("not supported")

    @dbus.service.method(AGENT, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        raise Rejected("not supported")

    @dbus.service.method(AGENT, in_signature="ouq")
    def DisplayPasskey(self, device, passkey, entered):
        log("passkey %06d" % passkey)

    @dbus.service.method(AGENT, in_signature="os")
    def DisplayPinCode(self, device, pincode):
        raise Rejected("not supported")

    @dbus.service.method(AGENT, in_signature="ou")
    def RequestConfirmation(self, device, passkey):
        self.gate.allow(device)

    @dbus.service.method(AGENT, in_signature="o")
    def RequestAuthorization(self, device):
        self.gate.allow(device)

    @dbus.service.method(AGENT)
    def Cancel(self):
        log("pairing cancelled")
        self.gate.cancelled()


def log(msg):
    print("[xbox-test] " + msg, flush=True)


def find_adapter(bus):
    om = dbus.Interface(bus.get_object(BLUEZ, "/"), DBUS_OM)
    for path, ifaces in om.GetManagedObjects().items():
        if GATT_MANAGER in ifaces and ADV_MANAGER in ifaces:
            return path
    return None


def check_device_id():
    try:
        with open("/etc/bluetooth/main.conf") as f:
            for line in f:
                s = line.strip()
                if s.lower().startswith("deviceid") and "=" in s:
                    log("BlueZ DeviceID: " + s.split("=", 1)[1].strip())
                    return
    except OSError:
        pass
    log("WARNING: no DeviceID in /etc/bluetooth/main.conf - run setup.sh first, "
        "or iOS will not see an Xbox vendor/product ID")


def main():
    if os.geteuid() != 0:
        log("run with sudo: sudo python3 pairing_test.py")
        sys.exit(1)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    check_device_id()

    adapter_path = find_adapter(bus)
    if not adapter_path:
        log("FAIL: no Bluetooth adapter with LE advertising + GATT server support found")
        sys.exit(1)
    log("using adapter " + adapter_path)

    adapter_props = dbus.Interface(bus.get_object(BLUEZ, adapter_path), DBUS_PROP)
    old_alias = adapter_props.Get(ADAPTER, "Alias")
    adapter_props.Set(ADAPTER, "Powered", dbus.Boolean(True))
    adapter_props.Set(ADAPTER, "Alias", dbus.String(DEVICE_NAME))
    gate = PairingGate(adapter_props, 180)

    # ---- GATT database ----
    app = Application(bus)

    battery = Service(app, uuid16(0x180F))
    Characteristic(battery, uuid16(0x2A19), ["read", "notify"], bytes([100]), name="Battery Level")

    hid = Service(app, uuid16(0x1812))
    # HID Information: bcdHID 1.11, country 0, flags = normally connectable
    Characteristic(hid, uuid16(0x2A4A), ["read"], bytes([0x11, 0x01, 0x00, 0x02]),
                   name="HID Information")
    Characteristic(hid, uuid16(0x2A4B), ["read", "encrypt-read"], REPORT_MAP, name="Report Map")
    Characteristic(hid, uuid16(0x2A4C), ["write-without-response"], bytes([0x00]),
                   name="HID Control Point")

    state = {"subscribed": False, "tick": 0, "first_tap_logged": False}

    def on_subscribe(on):
        state["subscribed"] = on
        if on:
            log("CONNECTED: phone subscribed to input; tapping A every 2 s. Not a pass yet - "
                "check Settings > General > Game Controller on the phone.")

    input_report = Characteristic(
        hid, uuid16(0x2A4D), ["read", "notify", "encrypt-read"], make_input_report(),
        name="Input Report", on_subscribe=on_subscribe)
    Descriptor(input_report, uuid16(0x2908), ["read"], bytes([INPUT_REPORT_ID, 0x01]))

    def on_rumble(data):
        log("phone sent rumble/output report: %s" % data.hex())

    output_report = Characteristic(
        hid, uuid16(0x2A4D),
        ["read", "write", "write-without-response", "encrypt-read", "encrypt-write"],
        bytes(8), name="Output Report (rumble)", on_write=on_rumble)
    Descriptor(output_report, uuid16(0x2908), ["read"], bytes([OUTPUT_REPORT_ID, 0x02]))

    adv = Advertisement(bus)
    agent = Agent(bus, Agent.PATH, gate)

    loop = GLib.MainLoop()

    def fail(what):
        def handler(err):
            log("FAIL: %s: %s" % (what, err))
            loop.quit()
        return handler

    agent_mgr = dbus.Interface(bus.get_object(BLUEZ, "/org/bluez"), AGENT_MANAGER)
    agent_mgr.RegisterAgent(Agent.PATH, "NoInputNoOutput")
    agent_mgr.RequestDefaultAgent(Agent.PATH)
    gate.start()

    gatt_mgr = dbus.Interface(bus.get_object(BLUEZ, adapter_path), GATT_MANAGER)
    adv_mgr = dbus.Interface(bus.get_object(BLUEZ, adapter_path), ADV_MANAGER)
    gatt_mgr.RegisterApplication(ROOT, {},
                                 reply_handler=lambda: log("GATT HID service registered"),
                                 error_handler=fail("registering GATT service"))
    adv_mgr.RegisterAdvertisement(Advertisement.PATH, {},
                                  reply_handler=lambda: log(
                                      "advertising as '%s' - open Settings > Bluetooth on the "
                                      "iPhone/iPad now" % DEVICE_NAME),
                                  error_handler=fail("starting LE advertising"))

    # Report connection / pairing changes of any remote device.
    def on_device_change(interface, changed, invalidated, path=None):
        if interface != DEVICE:
            return
        for key in ("Connected", "Paired", "ServicesResolved"):
            if key in changed:
                log("%s %s = %s" % (path.split("/")[-1], key, bool(changed[key])))
        if changed.get("Paired"):
            gate.paired(path)

    bus.add_signal_receiver(on_device_change, dbus_interface=DBUS_PROP,
                            signal_name="PropertiesChanged", arg0=DEVICE,
                            path_keyword="path")

    # 10 Hz report loop: neutral, plus a 200 ms tap of A every 2 s.
    def tick():
        if state["subscribed"]:
            state["tick"] = (state["tick"] + 1) % 20
            pressed = state["tick"] < 2
            input_report.notify(make_input_report(buttons=(BTN_A,) if pressed else ()))
            if pressed and not state["first_tap_logged"]:
                log("sent first A tap")
                state["first_tap_logged"] = True
        return True

    GLib.timeout_add(100, tick)

    def shutdown(*_):
        loop.quit()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run()
    finally:
        log("cleaning up")
        for call in (lambda: adv_mgr.UnregisterAdvertisement(Advertisement.PATH),
                     lambda: gatt_mgr.UnregisterApplication(ROOT),
                     gate.restore,
                     lambda: agent_mgr.UnregisterAgent(Agent.PATH),
                     lambda: adapter_props.Set(ADAPTER, "Alias", old_alias)):
            try:
                call()
            except dbus.exceptions.DBusException:
                pass


if __name__ == "__main__":
    main()
