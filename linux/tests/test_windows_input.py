import json, os, signal, struct, subprocess, sys, threading, time
KIT, SP = sys.argv[1], sys.argv[2]
OUT = SP + "/stdin_out.jsonl"
ok = True


def chk(n, c, extra=""):
    global ok
    ok &= bool(c)
    print("PASS" if c else "FAIL", n, extra, flush=True)


d = subprocess.Popen(["dbus-daemon", "--session", "--print-address", "--nofork"], stdout=subprocess.PIPE, text=True)
env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS=d.stdout.readline().strip(), PYTHONDONTWRITEBYTECODE="1", REFUSE="0")
m = subprocess.Popen([sys.executable, SP + "/mock_bluez.py", OUT], env=env)
time.sleep(1)
r = subprocess.Popen([sys.executable, "-u", "-W", "ignore", KIT + "/relay.py", "--stdin"], env=env,
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
lines = []
threading.Thread(target=lambda: [lines.append(x.decode().rstrip()) for x in r.stdout], daemon=True).start()
time.sleep(2.5)


def L():
    return [json.loads(x) for x in open(OUT)]


def dec(b):
    return struct.unpack("<6HBHB", b)


def last():
    time.sleep(.06)
    return dec(bytes.fromhex([x for x in L() if x["ev"] == "rep"][-1]["v"]))


def frame(kind="S", b=0, lt=0, rt=0, lx=0, ly=0, rx=0, ry=0):
    return struct.pack("<BBHBBhhhh", 0xA5, ord(kind), b, lt, rt, lx, ly, rx, ry)


def send(raw):
    r.stdin.write(raw)
    r.stdin.flush()


C = 32768
N = (C, C, C, C, 0, 0, 0, 0, 0)
try:
    send(frame("N"))
    chk("neutral before any pad", last() == N, last())
    send(frame())
    chk("centred pad is neutral (Y inverted by one step)", last()[0] == C and abs(last()[1] - C) <= 1, last())
    NS = last()
    for bit, pos in {0x1000: 0, 0x2000: 1, 0x4000: 3, 0x8000: 4, 0x100: 6, 0x200: 7, 0x20: 10, 0x10: 11, 0x400: 12, 0x40: 13, 0x80: 14}.items():
        send(frame(b=bit))
        chk("button %x" % bit, last()[7] == 1 << pos, last()[7])
        send(frame())
    for bits, hat in {1: 1, 9: 2, 8: 3, 10: 4, 2: 5, 6: 6, 4: 7, 5: 8}.items():
        send(frame(b=bits))
        chk("dpad %d" % bits, last()[6] == hat, last()[6])
    send(frame(lx=32767, ly=32767, rx=-32768, ry=-32768))
    chk("sticks: right+up, left+down", last()[:4] == (65535, 0, 0, 65535), last()[:4])
    send(frame(lt=255, rt=128))
    chk("triggers", last()[4] == 1023 and last()[5] == 128 * 1023 // 255, last()[4:6])
    send(frame())
    n0 = len(L())
    for i in range(50):
        send(frame(b=0x1000) + frame())     # several frames in one write
    time.sleep(.3)
    got = sum(1 for x in L()[n0:] if x["ev"] == "rep")
    chk("no lost taps in a burst", got == 100, got)
    send(frame(b=0x2000)[:5]); time.sleep(.1); send(frame(b=0x2000)[5:])
    chk("split frame", last()[7] == 2)
    send(b"\x00\xA5garbage" + frame(b=0x4000))
    chk("recovers after garbage", last()[7] == 8, last()[7])
    send(frame("N"))
    chk("no controller releases everything", last() == N, last())
    send(frame(b=0x1000))
    a = [x for x in L() if x["ev"] == "app"][0]

    def rum(h):
        return subprocess.run(["dbus-send", "--bus=" + env["DBUS_SYSTEM_BUS_ADDRESS"], "--print-reply", "--dest=" + a["sender"],
                               a["chars"][-1][0], "org.bluez.GattCharacteristic1.WriteValue",
                               "array:byte:" + ",".join("0x" + h[i:i + 2] for i in range(0, len(h), 2)), "dict:string:variant:"],
                              capture_output=True).returncode == 0
    chk("rumble accepted", rum("0f000063150a0000") and rum("0f000000000a0000"))
    time.sleep(.3)
    chk("rumble lines sent back", "@rumble 99 21 100" in lines and "@rumble 0 0 100" in lines, [x for x in lines if x.startswith("@")])
except Exception as e:
    chk("test run", False, repr(e))
r.stdin.close()
try:
    rc = r.wait(timeout=10)
except subprocess.TimeoutExpired:
    rc = "timeout"
    r.kill()
chk("stops cleanly when Windows side closes", rc == 0 and last() == N, (rc, last()))
evs = [x["ev"] for x in L()]
chk("cleanup", all(e in evs for e in ("unadv", "unapp", "unagent")))
print("\n".join(x for x in lines if not x.startswith("@"))[-900:])
m.kill()
d.kill()
print("ALL PASS" if ok else "SOME FAILED")
