import threading, fcntl, json, os, signal, struct, subprocess, sys, time
KIT, SP = sys.argv[1], sys.argv[2]
OUT = SP + "/mock_out.jsonl"
KEYS = [0x130, 0x131, 0x133, 0x134, 0x136, 0x137, 0x13a, 0x13b, 0x13c, 0x13d, 0x13e]


FF_ON = True
FF = []


def ffthread(fd):
    while True:
        try:
            _, _, t, c, v = struct.unpack("llHHi", os.read(fd, 24))
        except (OSError, struct.error):
            return
        if t == 0x101 and c == 1:
            b = bytearray(struct.pack("Ii96x", v, 0))
            fcntl.ioctl(fd, (3 << 30) | (104 << 16) | (ord('U') << 8) | 200, b)
            typ, eid = struct.unpack_from("Hh", b, 8)
            ln = struct.unpack_from("H", b, 8 + 10)[0]
            st, wk = struct.unpack_from("HH", b, 8 + 16)
            FF.append(("up", typ, eid, ln, st, wk))
            fcntl.ioctl(fd, (1 << 30) | (104 << 16) | (ord('U') << 8) | 201, b)
        elif t == 0x101 and c == 2:
            b = bytearray(struct.pack("IiI", v, 0, 0))
            fcntl.ioctl(fd, (3 << 30) | (12 << 16) | (ord('U') << 8) | 202, b)
            fcntl.ioctl(fd, (1 << 30) | (12 << 16) | (ord('U') << 8) | 203, b)
        elif t == 0x15:
            FF.append(("play", c, v))


def unplug(fd):
    fcntl.ioctl(fd, (ord('U') << 8) | 2)
    time.sleep(.6)


def rum(hexs):
    a = [x for x in L() if x["ev"] == "app"][0]
    data = ",".join("0x" + hexs[i:i + 2] for i in range(0, len(hexs), 2))
    p = subprocess.run(["dbus-send", "--bus=" + env["DBUS_SYSTEM_BUS_ADDRESS"], "--print-reply",
                        "--dest=" + a["sender"], a["chars"][-1][0],
                        "org.bluez.GattCharacteristic1.WriteValue",
                        "array:byte:" + data, "dict:string:variant:"],
                       capture_output=True, text=True)
    time.sleep(.2)
    return p.returncode == 0


def mkpad():
    fd = os.open("/dev/uinput", os.O_RDWR)

    def io(n, v):
        fcntl.ioctl(fd, (1 << 30) | (4 << 16) | (ord('U') << 8) | n, v)
    io(100, 1)
    io(100, 3)
    if FF_ON:
        io(100, 0x15)
        io(107, 0x50)
    for k in KEYS:
        io(101, k)
    absr = {0: (-32768, 32767), 1: (-32768, 32767), 3: (-32768, 32767), 4: (-32768, 32767),
            2: (0, 255), 5: (0, 255), 16: (-1, 1), 17: (-1, 1)}
    mx, mn = [0] * 64, [0] * 64
    for a, (lo, hi) in absr.items():
        io(103, a)
        mn[a], mx[a] = lo, hi
    os.write(fd, struct.pack("80sHHHHI64i64i64i64i", b"Microsoft X-Box 360 pad",
                             3, 0x045e, 0x028e, 0x110, 16 if FF_ON else 0, *mx, *mn, *([0] * 128)))
    fcntl.ioctl(fd, (ord('U') << 8) | 1)
    threading.Thread(target=ffthread, args=(fd,), daemon=True).start()
    time.sleep(.5)
    return fd


def ev(fd, *evs):
    for t, c, v in evs + ((0, 0, 0),):
        os.write(fd, struct.pack("llHHi", 0, 0, t, c, v))


d = subprocess.Popen(["dbus-daemon", "--session", "--print-address", "--nofork"],
                     stdout=subprocess.PIPE, text=True)
env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS=d.stdout.readline().strip(),
           PYTHONDONTWRITEBYTECODE="1")
m = subprocess.Popen([sys.executable, SP + "/mock_bluez.py", OUT], env=env)
time.sleep(1)
r = subprocess.Popen([sys.executable, KIT + "/relay.py"], env=env, stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT, text=True)
time.sleep(5)
ok = True


def L():
    return [json.loads(x) for x in open(OUT)]


def last():
    return bytes.fromhex([x for x in L() if x["ev"] == "rep"][-1]["v"])


def dec(b):
    return struct.unpack("<6HBHB", b)


def chk(n, c, extra=""):
    global ok
    ok &= bool(c)
    print("PASS" if c else "FAIL", n, extra, flush=True)


N = (32768,) * 4 + (0, 0, 0, 0, 0)
try:
    chk("subscribed, neutral sent with no pad", dec(last()) == N)
    fd = mkpad()
    time.sleep(1.5)
    for k, bit in zip(KEYS, [0, 1, 3, 4, 6, 7, 10, 11, 12, 13, 14]):
        ev(fd, (1, k, 1)); time.sleep(.06); x = dec(last())
        ev(fd, (1, k, 0)); time.sleep(.06)
        chk("key %x" % k, x == N[:7] + (1 << bit, 0) and dec(last()) == N)
    for (x, y), h in {(0, -1): 1, (1, -1): 2, (1, 0): 3, (1, 1): 4, (0, 1): 5, (-1, 1): 6,
                      (-1, 0): 7, (-1, -1): 8}.items():
        ev(fd, (3, 16, x), (3, 17, y)); time.sleep(.06)
        chk("dpad %s" % ((x, y),), dec(last())[6] == h)
        ev(fd, (3, 16, 0), (3, 17, 0)); time.sleep(.06)
    for i, (a, v, e) in enumerate([(0, 32767, 65535), (1, -32768, 0), (3, -32768, 0),
                                   (4, 32767, 65535), (2, 255, 1023), (5, 255, 1023)]):
        ev(fd, (3, a, v)); time.sleep(.06)
        chk("axis %d" % a, dec(last())[i] == e, dec(last()))
        ev(fd, (3, a, 0)); time.sleep(.06)
    chk("neutral after axes", dec(last()) == N, dec(last()))
    n0, t = len(L()), time.time()
    for i in range(1000):
        ev(fd, (3, 0, i * 30 + 1)); time.sleep(.001)
    dt = time.time() - t
    time.sleep(.2)
    n = len(L()) - n0
    chk("rate limit", n / dt <= 110, "%d reports in %.2fs" % (n, dt))
    chk("final stick value delivered", dec(last())[0] == 999 * 30 + 1 + 32768)
    ev(fd, (3, 0, 0)); time.sleep(.1)
    n0 = len(L())
    for i in range(50):
        ev(fd, (1, 0x130, 1)); ev(fd, (1, 0x130, 0)); time.sleep(.002)
    time.sleep(.3)
    got = sum(1 for x in L()[n0:] if x["ev"] == "rep")
    chk("no lost fast taps", got == 100, got)
    ev(fd, (1, 0x130, 1)); time.sleep(.1)
    held = dec(last())[7] == 1
    FF.clear(); rum("0f000063150a0000")
    eid = FF[0][2] if FF else -1
    chk("rumble from photo: strong 99 weak 21, 100 ms", FF == [
        ("up", 0x50, eid, 100, 99 * 0xffff // 100, 21 * 0xffff // 100), ("play", eid, 1)], FF)
    FF.clear(); rum("0f000000110a0000")
    chk("update reuses effect", FF == [
        ("up", 0x50, eid, 100, 0, 17 * 0xffff // 100), ("play", eid, 1)], FF)
    FF.clear(); rum("0f000000000a0000")
    chk("zero strength stops", FF == [("play", eid, 0)], FF)
    FF.clear(); rum("020000646" + "4ff00ff")
    chk("enable bits, long loop capped", FF == [
        ("up", 0x50, eid, 2550, 0xffff, 0), ("play", eid, 1)], FF)
    FF.clear(); rum("0f00006464000000")
    chk("zero length stops, never endless", FF == [("play", eid, 0)], FF)
    FF.clear()
    chk("odd sizes ignored", rum("0f00") and rum("0f000063150a000000") and not FF, FF)
    chk("button still held through rumble", dec(last())[7] == 1)
    unplug(fd)
    chk("unplug releases held button", held and dec(last()) == N, dec(last()))
    fd = mkpad(); time.sleep(1.5)
    ev(fd, (1, 0x131, 1)); time.sleep(.1)
    chk("replug works", dec(last())[7] == 2, dec(last()))
    FF.clear(); rum("0f000063150a0000")
    chk("rumble after replug", [x[0] for x in FF] == ["up", "play"], FF)
    unplug(fd)
    FF_ON = False
    fd = mkpad(); time.sleep(1.5); FF.clear()
    chk("pad without rumble: no error to phone",
        rum("0f000063150a0000") and rum("0f000063150a0000") and not FF)
    ev(fd, (1, 0x131, 1)); time.sleep(.1)
    chk("pad without rumble: buttons fine", dec(last())[7] == 2)
    unplug(fd)
    FF_ON = True
    fd = mkpad(); time.sleep(1.5); FF.clear()
    tr = subprocess.run([sys.executable, "-W", "ignore", KIT + "/relay.py", "--test-rumble"],
                        env=env, capture_output=True, text=True, timeout=30)
    print(tr.stdout, tr.stderr[-300:])
    chk("--test-rumble", tr.returncode == 0 and [(x[4], x[5]) for x in FF if x[0] == "up"] == [
        (0xffff, 0), (0, 0xffff), (0xffff, 0xffff)], FF)
except Exception as e:
    chk("test run", False, repr(e))
r.send_signal(signal.SIGINT)
try:
    o, _ = r.communicate(timeout=10)
except subprocess.TimeoutExpired:
    r.kill()
    o, _ = r.communicate()
chk("clean exit", r.returncode == 0 and dec(last()) == N, r.returncode)
evs = [x["ev"] for x in L()]
chk("cleanup calls", all(e in evs for e in ("unadv", "unapp", "unagent")) and "err" not in evs)
print([x for x in L() if x["ev"] in ("app", "err")])
print(o)
m.kill()
d.kill()
print("ALL PASS" if ok else "SOME FAILED")
