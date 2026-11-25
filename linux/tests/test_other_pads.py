"""Gamepads that are not Xbox-type, made with uinput. Run as root: test_other_pads.py KIT TESTS"""
import fcntl, json, os, signal, struct, subprocess, sys, time
KIT, SP = sys.argv[1], sys.argv[2]
OUT = SP + "/pads_out.jsonl"
ok = True
N = (32768,) * 4 + (0, 0, 0, 0, 0)


def chk(n, c, extra=""):
    global ok
    ok &= bool(c)
    print("PASS" if c else "FAIL", n, extra, flush=True)


def mkpad(name, vendor, product, keys, axes):
    fd = os.open("/dev/uinput", os.O_RDWR)

    def io(n, v):
        fcntl.ioctl(fd, (1 << 30) | (4 << 16) | (ord('U') << 8) | n, v)
    io(100, 1)
    if axes:
        io(100, 3)
    for k in keys:
        io(101, k)
    mx, mn = [0] * 64, [0] * 64
    for a, (lo, hi) in axes.items():
        io(103, a)
        mn[a], mx[a] = lo, hi
    os.write(fd, struct.pack("80sHHHHI64i64i64i64i", name, 3, vendor, product, 0x110, 0, *mx, *mn, *([0] * 128)))
    fcntl.ioctl(fd, (ord('U') << 8) | 1)
    time.sleep(.5)
    # rest the axes: centred sticks, released triggers
    ev(fd, *[(3, a, (lo + hi + 1) // 2 if a in (0, 1, 2, 3, 4, 5) and lo == 0 and hi == 255 else 0) for a, (lo, hi) in axes.items()])
    return fd


def ev(fd, *evs):
    for t, c, v in evs + ((0, 0, 0),):
        os.write(fd, struct.pack("llHHi", 0, 0, t, c, v))


def unplug(fd):
    fcntl.ioctl(fd, (ord('U') << 8) | 2)
    os.close(fd)
    time.sleep(1)


d = subprocess.Popen(["dbus-daemon", "--session", "--print-address", "--nofork"], stdout=subprocess.PIPE, text=True)
env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS=d.stdout.readline().strip(), PYTHONDONTWRITEBYTECODE="1", REFUSE="0")
m = subprocess.Popen([sys.executable, SP + "/mock_bluez.py", OUT], env=env)
time.sleep(1)
r = subprocess.Popen([sys.executable, "-u", "-W", "ignore", KIT + "/relay.py", "--quit-on-eof"], env=env, stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(3)


def last():
    time.sleep(.08)
    reps = [json.loads(x) for x in open(OUT)]
    return struct.unpack("<6HBHB", bytes.fromhex([x for x in reps if x["ev"] == "rep"][-1]["v"]))


def near(a, b):
    return all(abs(x - y) <= 400 for x, y in zip(a[:4], b[:4])) and a[4:] == b[4:]


ORDER = [3, 0, 1, 4, 6, 7, None, None, 10, 11, 13, 14, 12]     # X A B Y LB RB LT RT View Menu LS RS Xbox
HAT = {16: (-1, 1), 17: (-1, 1)}
try:
    # A mouse, a keyboard and a touchpad must not be taken for gamepads.
    decoys = [mkpad(b"Test Mouse", 0x1111, 1, [0x110, 0x111, 0x120], {0: (0, 1023), 1: (0, 1023)}),
              mkpad(b"Test Keyboard", 0x1111, 2, list(range(1, 100)), {}),
              mkpad(b"Test Touchpad", 0x1111, 3, [0x14A, 0x145, 0x130], {0: (0, 1023), 1: (0, 1023)})]
    time.sleep(2)
    chk("decoys ignored, neutral", near(last(), N), last())

    fd = mkpad(b"Generic USB Joystick", 0x0079, 0x0006, range(0x120, 0x12D), {**{a: (0, 255) for a in (0, 1, 2, 5)}, **HAT})
    time.sleep(2)
    chk("numbered buttons: at rest", near(last(), N), last())
    for i, bit in enumerate(ORDER):
        ev(fd, (1, 0x120 + i, 1))
        x = last()
        ev(fd, (1, 0x120 + i, 0))
        chk("numbered button %d" % (i + 1), x[7] == (1 << bit) if bit is not None else x[4 + (i - 6)] == 1023 and x[7] == 0, x)
    ev(fd, (3, 2, 255), (3, 5, 0))
    x = last()
    chk("right stick on Z/RZ", x[2] == 65535 and x[3] == 0 and x[4] == x[5] == 0, x)
    ev(fd, (3, 2, 128), (3, 5, 128), (3, 16, -1), (3, 17, 1))
    chk("hat down-left", last()[6] == 6)
    unplug(fd)

    fd = mkpad(b"Android Style Pad", 0x2DC8, 0x3106, [0x130, 0x131, 0x133, 0x134, 0x136, 0x137, 0x138, 0x139, 0x13A, 0x13B, 0x13C, 0x13D, 0x13E],
               {**{a: (0, 255) for a in (0, 1, 2, 5, 9, 10)}, **HAT})
    time.sleep(2)
    ev(fd, (1, 0x130, 1), (1, 0x133, 1))
    chk("Android A and X", last()[7] == (1 << 0 | 1 << 3), last())
    ev(fd, (1, 0x130, 0), (1, 0x133, 0), (3, 9, 255), (3, 10, 128))
    x = last()
    chk("gas is RT, brake is LT", x[5] == 1023 and 510 <= x[4] <= 516, x)
    ev(fd, (3, 9, 0), (3, 10, 0), (1, 0x138, 1))
    chk("trigger button ignored beside an analog one", last()[4] == 0, last())
    unplug(fd)

    fd = mkpad(b"Wireless Controller", 0x054C, 0x09CC, [0x130, 0x131, 0x133, 0x134, 0x136, 0x137, 0x138, 0x139, 0x13A, 0x13B, 0x13C, 0x13D, 0x13E],
               {**{a: (0, 255) for a in (0, 1, 2, 3, 4, 5)}, **HAT})
    time.sleep(1.5)
    ev(fd, (3, 2, 0), (3, 5, 0))
    ev(fd, (1, 0x133, 1))
    x = last()
    ev(fd, (1, 0x133, 0), (1, 0x134, 1))
    y = last()
    chk("PlayStation triangle is Y, square is X", x[7] == 1 << 4 and y[7] == 1 << 3, (x, y))
    ev(fd, (1, 0x134, 0), (3, 2, 255), (3, 3, 255))
    x = last()
    chk("PlayStation trigger and right stick", x[4] == 1023 and x[2] == 65535, x)
    unplug(fd)
    chk("unplugged is neutral", near(last(), N), last())
    for f in decoys:
        unplug(f)
except Exception as e:
    chk("test run", False, repr(e))
r.stdin.close()
try:
    rc = r.wait(timeout=10)
except subprocess.TimeoutExpired:
    rc = "timeout"
    r.kill()
chk("stops when stdin closes", rc == 0, rc)
print(r.stdout.read()[-1200:])
m.kill()
d.kill()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
