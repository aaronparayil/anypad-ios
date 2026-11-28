"""The Android apps: their words, the phone choice, and Bluetooth LE only while running.

No Bluetooth needed. The relay part needs dbus-daemon (it uses mock_bluez.py).
"""
import os, signal, subprocess, sys, tempfile, threading, time
KIT, SP = sys.argv[1], sys.argv[2]
sys.path.insert(0, KIT)
sys.dont_write_bytecode = True
import anypad

ok = True


def chk(n, c, extra=""):
    global ok
    ok &= bool(c)
    print("PASS" if c else "FAIL", n, extra, flush=True)


print("== words")
good = dict(modules=True, bluez=True, pkexec=True, adapter=True, pad=True)
for phone, name, steps in (("ios", "iPhone or iPad", "Settings > Bluetooth"),
                           ("android", "Android phone or tablet", "Pair new device")):
    m = anypad.Model(phone)
    m.checks(good)
    le = "LE only" in m.hint
    chk(phone + ": ready hint", le == (phone == "android"), m.hint)
    m.started()
    m.line("[relay 0.2s] ready: on the phone, open whatever and tap 'Xbox Wireless Controller'")
    chk(phone + ": waiting", m.title == "Waiting for your " + name and steps in m.hint, (m.title, m.hint))
    m.line("[relay 5.1s] accepting pairing")
    chk(phone + ": pairing", name in m.hint, m.hint)
    m.line("[relay 6.0s] phone is listening: play!")
    m.line("[relay 9.0s] phone DISCONNECTED")
    chk(phone + ": disconnected", name in m.hint, m.hint)
    m.line("[relay 9.5s] removed an out-of-date pairing")
    chk(phone + ": pair again", name in m.hint, m.hint)
chk("other phones' names never appear", "iPhone" not in str(anypad.PHONES["android"]) and
    "Android" not in str(anypad.PHONES["ios"]))

print("== which phone")
chk("--android", anypad.pick_phone(["--android"]) == "android")
chk("--ios", anypad.pick_phone(["--ios"]) == "ios")
real_here = anypad.HERE
with tempfile.TemporaryDirectory() as d:
    anypad.HERE = d
    chk("no file: iOS", anypad.pick_phone([]) == "ios")
    open(os.path.join(d, "phone"), "w").write("android\n")
    chk("phone file says android", anypad.pick_phone([]) == "android")
    chk("--ios beats the file", anypad.pick_phone(["--ios"]) == "ios")
    open(os.path.join(d, "phone"), "w").write("something else")
    chk("unknown file content: iOS", anypad.pick_phone([]) == "ios")
anypad.HERE = real_here

seen = []
real_popen = anypad.subprocess.Popen


class FakePopen:
    def __init__(self, command, **kw):
        seen.append(command)
        self.stdout, self.stdin = iter([]), open(os.devnull, "w")

    def wait(self):
        return 0


anypad.subprocess.Popen = FakePopen
anypad.Engine(lambda t: None, lambda c: None, phone="android")
anypad.Engine(lambda t: None, lambda c: None)
anypad.subprocess.Popen = real_popen
time.sleep(.2)
chk("window starts the engine for Android", seen[0][-2:] == ["run", "android"], seen[0])
chk("and for iOS by default", seen[1][-2:] == ["run", "ios"], seen[1])

print("== relay instructions")
d = subprocess.Popen(["dbus-daemon", "--session", "--print-address", "--nofork"], stdout=subprocess.PIPE, text=True)
env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS=d.stdout.readline().strip(), PYTHONDONTWRITEBYTECODE="1", REFUSE="0")
mock = subprocess.Popen([sys.executable, SP + "/mock_bluez.py", SP + "/android_out.jsonl"], env=env)
time.sleep(1)
try:
    for phone, steps in (("android", "open Bluetooth settings, tap Pair new device, then tap 'Xbox Wireless Controller'"),
                         ("ios", "open Settings > Bluetooth and tap 'Xbox Wireless Controller'")):
        r = subprocess.Popen([sys.executable, "-u", "-W", "ignore", KIT + "/relay.py", "--stdin", "--phone", phone],
                             env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        lines = []
        threading.Thread(target=lambda: [lines.append(x.decode().rstrip()) for x in r.stdout], daemon=True).start()
        for _ in range(50):
            if any("ready: on the phone" in x for x in lines):
                break
            time.sleep(.1)
        r.stdin.close()
        r.wait(10)
        ready = [x for x in lines if "ready: on the phone" in x]
        chk("relay --phone " + phone, ready and ready[0].endswith("ready: on the phone, " + steps), ready or lines[-5:])
    p = subprocess.run([sys.executable, KIT + "/relay.py", "--phone", "nokia"], capture_output=True, text=True, env=env)
    chk("unknown phone refused", p.returncode == 2 and "invalid choice" in p.stderr)
finally:
    mock.terminate()
    d.terminate()

print("== Bluetooth LE only while the Android app runs")
tmp = tempfile.mkdtemp()
stubs = os.path.join(tmp, "bin")
os.mkdir(stubs)
calls = os.path.join(tmp, "calls")


def stub(name, body):
    path = os.path.join(stubs, name)
    with open(path, "w") as f:
        f.write("#!/bin/bash\n" + body + "\n")
    os.chmod(path, 0o755)


for name in ("systemctl", "rfkill", "modprobe", "sleep"):
    stub(name, 'echo "%s $*" >> "%s"' % (name, calls))
stub("systemd-inhibit", 'while [[ "$1" == --* ]]; do shift; done; exec "$@"')
# Stands in for python3: shows the Bluetooth mode it ran under, then waits or ends.
stub("fakepy", 'echo "mode=[$(grep ControllerMode "$XBOX_BRIDGE_CONF")] args=$*"\n'
               '[ -n "$WAIT" ] && { trap "exit 0" INT; while true; do /bin/sleep 0.1; done; }\nexit 7')


def engine(phone, conf_extra, how="play", wait=False):
    conf = os.path.join(tmp, "main.conf")
    with open(conf, "w") as f:
        f.write("[General]\nDeviceID = usb:045e:0b13:0509\nJustWorksRepairing = confirm\n" + conf_extra + "[Policy]\n")
    open(calls, "w").close()
    e = dict(os.environ, PATH=stubs + ":" + os.environ["PATH"], XBOX_BRIDGE_CONF=conf,
             ANYPAD_PYTHON=os.path.join(stubs, "fakepy"), WAIT="1" if wait else "")
    cmd = ["bash", KIT + "/app_engine.sh", how, phone, "--rumble", "50"]
    if not wait:
        p = subprocess.run(cmd, env=e, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        out, code = p.stdout, p.returncode
    else:
        p = subprocess.Popen(cmd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        time.sleep(1.5)
        os.killpg(p.pid, signal.SIGINT)       # what Ctrl+C in a terminal does
        out, code = p.communicate(timeout=10)[0], p.returncode
    return out, code, open(conf).read(), open(calls).read()


out, code, conf, made = engine("android", "")
chk("Android: LE only during the run", "mode=[ControllerMode = le]" in out, out)
chk("Android: put back afterwards", "ControllerMode" not in conf, conf)
chk("Android: Bluetooth restarted twice", made.count("systemctl restart bluetooth") == 2, made)
chk("Android: relay told the phone and the options", "args=-u -W ignore relay.py --phone android --rumble 50" in out, out)
chk("relay's exit code kept", code == 7, code)

out, code, conf, made = engine("android", "ControllerMode = bredr\n")
chk("an earlier mode is put back exactly", "mode=[ControllerMode = le]" in out and "ControllerMode = bredr" in conf
    and conf.count("ControllerMode") == 1, conf)
chk("and in the [General] section", conf.index("ControllerMode") < conf.index("[Policy]"), conf)

out, code, conf, made = engine("android", "ControllerMode = le\n")
chk("already LE only: left alone, no restart", "ControllerMode = le" in conf and "systemctl" not in made, made)

out, code, conf, made = engine("ios", "")
chk("iOS: mode not touched", "mode=[]" in out and "ControllerMode" not in conf and "systemctl" not in made, (out, made))
chk("iOS: relay told", "--phone ios" in out, out)

out, code, conf, made = engine("android", "", how="run")
chk("window run stops at end of input", "--quit-on-eof" in out, out)

out, code, conf, made = engine("android", "", wait=True)
chk("Ctrl+C: Bluetooth still put back", "mode=[ControllerMode = le]" in out and "ControllerMode" not in conf
    and made.count("systemctl restart bluetooth") == 2, (out, conf, made))

out, code, conf, made = engine("windows-phone", "")
chk("unknown phone refused", code == 2 and "unknown phone" in out, out)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
