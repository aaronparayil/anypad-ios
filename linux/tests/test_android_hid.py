"""What Android makes of AnyPad's controller, checked with the Linux kernel Android runs on.

Android's Bluetooth stack hands a Bluetooth LE gamepad to the kernel through /dev/uhid, and
the kernel's HID drivers turn it into an input device. This test does the same with the
exact report layout, name and ID the relay uses, presses every button, moves every stick,
then maps the kernel's codes with Android's key layout. AOSP has no layout file for
045e:0b13, so Android uses Generic.kl; the lines below are copied from it.
It also asks the kernel for rumble, which the hid-microsoft driver turns into the Xbox
rumble report, and checks that the relay reads it back.

Needs root and /dev/uhid (modprobe uhid hid-microsoft). WSL's kernel has no uhid: then it
says SKIPPED, unless REQUIRE_UHID=1 (as in CI).
"""
import fcntl, glob, os, re, struct, sys, threading, time
KIT, SP = sys.argv[1], sys.argv[2]
sys.path.insert(0, KIT)
sys.dont_write_bytecode = True
import pairing_test as pt
import relay

# From AOSP frameworks/base/data/keyboards/Generic.kl
GENERIC_KL_KEYS = {304: "BUTTON_A", 305: "BUTTON_B", 306: "BUTTON_C", 307: "BUTTON_X", 308: "BUTTON_Y",
                   309: "BUTTON_Z", 310: "BUTTON_L1", 311: "BUTTON_R1", 312: "BUTTON_L2", 313: "BUTTON_R2",
                   314: "BUTTON_SELECT", 315: "BUTTON_START", 316: "BUTTON_MODE", 317: "BUTTON_THUMBL",
                   318: "BUTTON_THUMBR", 167: "MEDIA_RECORD", 158: "BACK", 172: "HOME"}
GENERIC_KL_AXES = {0x00: "X", 0x01: "Y", 0x02: "Z", 0x03: "RX", 0x04: "RY", 0x05: "RZ",
                   0x09: "RTRIGGER", 0x0a: "LTRIGGER", 0x10: "HAT_X", 0x11: "HAT_Y"}

ok = True


def chk(n, c, extra=""):
    global ok
    ok &= bool(c)
    print("PASS" if c else "FAIL", n, extra if not c else "", flush=True)


if not os.path.exists("/dev/uhid"):
    os.system("modprobe uhid 2> /dev/null")
if not os.path.exists("/dev/uhid"):
    print("SKIPPED: this kernel has no /dev/uhid")
    sys.exit(1 if os.environ.get("REQUIRE_UHID") == "1" else 0)
os.system("modprobe hid-microsoft 2> /dev/null")

UHID_DESTROY, UHID_START, UHID_OPEN, UHID_OUTPUT = 1, 2, 4, 6
UHID_GET_REPORT, UHID_GET_REPORT_REPLY, UHID_CREATE2, UHID_INPUT2 = 9, 10, 11, 12
UHID_SET_REPORT, UHID_SET_REPORT_REPLY = 13, 14
EVENT_SIZE = 4376          # sizeof(struct uhid_event)
EV_SYN, EV_KEY, EV_ABS, EV_FF = 0, 1, 3, 0x15
FF_RUMBLE = 0x50
NAME = b"AnyPad Android test"

fd = os.open("/dev/uhid", os.O_RDWR)
os.write(fd, struct.pack("<I128s64s64sHHIIII4096s", UHID_CREATE2, NAME, b"", b"", len(pt.REPORT_MAP),
                         5, 0x045E, 0x0B13, 0x0509, 0, pt.REPORT_MAP))   # bus 5 = Bluetooth
outputs, kernel_events = [], []


def uhid_reader():
    while True:
        try:
            ev = os.read(fd, EVENT_SIZE)
        except OSError:
            return
        kind = struct.unpack_from("<I", ev)[0]
        kernel_events.append(kind)
        if kind == UHID_OUTPUT:
            size = struct.unpack_from("<H", ev, 4 + 4096)[0]
            outputs.append(ev[4:4 + size])
        elif kind == UHID_GET_REPORT:       # no feature reports: say so at once
            rid = struct.unpack_from("<I", ev, 4)[0]
            os.write(fd, struct.pack("<IIHH4096s", UHID_GET_REPORT_REPLY, rid, 5, 0, b""))
        elif kind == UHID_SET_REPORT:
            rid = struct.unpack_from("<I", ev, 4)[0]
            os.write(fd, struct.pack("<IIH4096s", UHID_SET_REPORT_REPLY, rid, 5, b""))


threading.Thread(target=uhid_reader, daemon=True).start()

event_path = None
for _ in range(50):
    for block in open("/proc/bus/input/devices").read().split("\n\n"):
        if NAME.decode() in block and "Vendor=045e Product=0b13" in block:
            m = re.search(r"\b(event\d+)", block)
            if m:
                event_path = "/dev/input/" + m.group(1)
    if event_path:
        break
    time.sleep(.1)
chk("kernel made an input device", event_path, open("/proc/bus/input/devices").read()[-600:])
if not event_path:
    sys.exit(1)
drivers = [os.path.basename(os.readlink(p)) for p in glob.glob("/sys/bus/hid/devices/0005:045E:0B13.*/driver")]
print("kernel driver:", drivers, " kernel:", os.uname().release)
chk("the Xbox driver took it (as on Android)", drivers == ["microsoft"], drivers)

ev_fd = os.open(event_path, os.O_RDWR | os.O_NONBLOCK)
INPUT_EVENT = struct.Struct("llHHi")


def bits(kind, size=96):
    buf = bytearray(size)
    fcntl.ioctl(ev_fd, relay._ior(0x20 + kind, size), buf)
    return {i for i in range(size * 8) if buf[i // 8] >> (i % 8) & 1}


def absinfo(code):
    buf = bytearray(24)
    fcntl.ioctl(ev_fd, relay._ior(0x40 + code, 24), buf)
    return struct.unpack("<6i", buf)    # value, min, max, fuzz, flat, resolution


keys, axes = bits(EV_KEY), bits(EV_ABS, 8)
chk("all 15 buttons and Share exist", set(range(304, 319)) | {167} <= keys, sorted(keys))
chk("sticks, triggers and hat exist", {0, 1, 2, 5, 9, 10, 16, 17} <= axes, sorted(axes))
chk("no extra axes that Android could misread", axes <= {0, 1, 2, 5, 9, 10, 16, 17}, sorted(axes))
RANGE = {code: absinfo(code)[1:3] for code in axes}


def state_after(report):
    while True:          # drop what is queued
        try:
            os.read(ev_fd, INPUT_EVENT.size * 64)
        except BlockingIOError:
            break
    os.write(fd, struct.pack("<IH4096s", UHID_INPUT2, len(report) + 1, bytes([pt.INPUT_REPORT_ID]) + report))
    time.sleep(.05)
    pressed, moved = set(), {}
    while True:
        try:
            data = os.read(ev_fd, INPUT_EVENT.size * 64)
        except BlockingIOError:
            break
        for i in range(0, len(data), INPUT_EVENT.size):
            _, _, kind, code, value = INPUT_EVENT.unpack_from(data, i)
            if kind == EV_KEY and value:
                pressed.add(code)
            elif kind == EV_ABS:
                moved[code] = value
    return pressed, moved


def android_axis(code, raw):
    """Android's scaling: sticks and hat to -1..1, triggers to 0..1."""
    lo, hi = RANGE[code]
    if GENERIC_KL_AXES[code].endswith("TRIGGER"):
        return round((raw - lo) / (hi - lo), 2)
    return round((raw - lo) * 2 / (hi - lo) - 1, 2)


state_after(pt.make_input_report())          # everything at rest first
want = {"A": "BUTTON_A", "B": "BUTTON_B", "X": "BUTTON_X", "Y": "BUTTON_Y", "LB": "BUTTON_L1",
        "RB": "BUTTON_R1", "View": "BUTTON_SELECT", "Menu": "BUTTON_START", "Xbox": "BUTTON_MODE",
        "LS": "BUTTON_THUMBL", "RS": "BUTTON_THUMBR"}
for name, bit in (("A", pt.BTN_A), ("B", pt.BTN_B), ("X", pt.BTN_X), ("Y", pt.BTN_Y), ("LB", pt.BTN_LB),
                  ("RB", pt.BTN_RB), ("View", pt.BTN_VIEW), ("Menu", pt.BTN_MENU), ("Xbox", pt.BTN_XBOX),
                  ("LS", pt.BTN_LS), ("RS", pt.BTN_RS)):
    pressed, _ = state_after(pt.make_input_report(buttons=[bit]))
    got = [GENERIC_KL_KEYS.get(c, "code %d" % c) for c in sorted(pressed)]
    chk("%s is %s on Android" % (name, want[name]), got == [want[name]], got)
    state_after(pt.make_input_report())
pressed, _ = state_after(pt.make_input_report(share=True))
chk("Share is MEDIA_RECORD on Android", [GENERIC_KL_KEYS.get(c) for c in pressed] == ["MEDIA_RECORD"], pressed)
state_after(pt.make_input_report())

# Report values as the relay makes them: left stick right and up, right stick left and down.
_, moved = state_after(pt.make_input_report(lx=65535, ly=0, rx=0, ry=65535, lt=1023, rt=512, hat=1))
seen = {GENERIC_KL_AXES[c]: android_axis(c, v) for c, v in moved.items()}
chk("left stick right is AXIS_X +1", seen.get("X") == 1.0, seen)
chk("left stick up is AXIS_Y -1 (Android's up)", seen.get("Y") == -1.0, seen)
chk("right stick left is AXIS_Z -1", seen.get("Z") == -1.0, seen)
chk("right stick down is AXIS_RZ +1", seen.get("RZ") == 1.0, seen)
chk("left trigger full is LTRIGGER 1", seen.get("LTRIGGER") == 1.0, seen)
chk("right trigger half is RTRIGGER 0.5", seen.get("RTRIGGER") == 0.5, seen)
chk("D-pad up is HAT_Y -1", seen.get("HAT_Y") == -1.0 and seen.get("HAT_X", 0.0) == 0.0, seen)
_, moved = state_after(pt.make_input_report(hat=3))
chk("D-pad right is HAT_X +1", android_axis(0x10, moved.get(0x10, 0)) == 1.0 and android_axis(0x11, moved.get(0x11, 0)) == 0.0, moved)
_, moved = state_after(pt.make_input_report())
rest = {GENERIC_KL_AXES[c]: android_axis(c, v) for c, v in moved.items()}
chk("back at rest: sticks centred, triggers 0, hat 0", all(abs(v) <= 0.01 for v in rest.values()), rest)

# Rumble, the way Android's vibrator asks for it.
def motors(report):
    parsed = relay.parse_rumble(report[1:])
    return parsed[:2] if parsed else None


chk("the kernel offers rumble", FF_RUMBLE in bits(EV_FF, 16))
effect = bytearray(relay.FF_EFFECT.pack(FF_RUMBLE, -1, 0, 0, 0, 1000, 0, 0xFFFF, 0x8000))
try:
    fcntl.ioctl(ev_fd, relay.EVIOCSFF, effect)
    effect_id = struct.unpack_from("<h", effect, 2)[0]
    outputs.clear()
    os.write(ev_fd, INPUT_EVENT.pack(0, 0, EV_FF, effect_id, 1))
    for _ in range(40):
        if outputs:
            break
        time.sleep(.05)
    chk("rumble reaches the controller as report 3", outputs and outputs[0][0] == pt.OUTPUT_REPORT_ID and len(outputs[0]) == 9,
        [o.hex() for o in outputs])
    if outputs:
        parsed = relay.parse_rumble(outputs[0][1:])
        print("rumble report:", outputs[0].hex(), "->", parsed)
        chk("relay reads it: strong 100 %, weak 50 %", parsed and parsed[:2] == (100, 50), parsed)
    outputs.clear()
    os.write(ev_fd, INPUT_EVENT.pack(0, 0, EV_FF, effect_id, 0))
    for _ in range(40):
        if any(motors(o) == (0, 0) for o in outputs):
            break
        time.sleep(.05)
    chk("stopping it turns the motors off", any(motors(o) == (0, 0) for o in outputs),
        [o.hex() for o in outputs])
except OSError as e:
    chk("rumble", False, e)

os.close(ev_fd)
os.write(fd, struct.pack("<I", UHID_DESTROY) + bytes(EVENT_SIZE - 4))
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
