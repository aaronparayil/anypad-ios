"""The Linux app without its window: what it shows, and starting and stopping the relay."""
import os, sys, threading, time
KIT, SP = sys.argv[1], sys.argv[2]
sys.path.insert(0, KIT)
sys.dont_write_bytecode = True
import anypad

ok = True


def chk(n, c, extra=""):
    global ok
    ok &= bool(c)
    print("PASS" if c else "FAIL", n, extra, flush=True)


good = dict(modules=True, bluez=True, pkexec=True, adapter=True, pad=True)
m = anypad.Model()
chk("all good", m.checks(good) == (True, []) and m.title == "Ready to start" and m.laptop and m.pad)
r, todo = m.checks(dict(good, pad=False))
chk("no gamepad does not block Start", r and len(todo) == 1 and not m.pad)
for k in ("modules", "bluez", "pkexec", "adapter"):
    r, todo = m.checks(dict(good, **{k: False}))
    chk("missing %s blocks Start" % k, not r and len(todo) == 1 and m.title == "Almost there")

m = anypad.Model()
m.checks(good)
m.started()
say = [("[relay 0.0s] waiting for the controller (045e:028e)", "Starting...", False),
       ("[relay 0.1s] controller found: Some Pad (/dev/input/event3), rumble not available", "Starting...", False),
       ("[relay 0.2s] ready: on the phone, open Settings > Bluetooth and tap 'X'", "Waiting for your iPhone or iPad", False),
       ("[relay 5.0s] phone connected", "Connecting...", False),
       ("[relay 5.1s] accepting pairing", "Pairing...", False),
       ("[relay 6.0s] phone is listening: play!", "Connected: play!", True),
       ("[relay 9.0s] phone DISCONNECTED", "Disconnected", False),
       ("[relay 12.0s] phone connected", "Connected: play!", True)]
for text, title, phone in say:
    m.line(text)
    chk("after '%s'" % text[12:40], m.title == title and m.phone == phone, (m.title, m.phone))
chk("gamepad lit", m.pad)
m.line("[relay 13.0s] controller disconnected; released all buttons")
chk("gamepad out", not m.pad)
m.stop_asked()
m.line("[relay 14.0s] phone is listening: play!")
chk("messages do not undo Stopping", m.title == "Stopping...")
m.ended(0)
chk("clean end", not m.running and m.problem is None)
m.started(); m.ended(126)
chk("declined password explained", "Permission" in m.problem)
m.checks(good)
chk("and shown", m.title == "It stopped")
m.started()
chk("a new start clears it", m.problem is None)
m.line("[relay 0.1s] FAIL: no usable Bluetooth adapter found")
m.ended(1)
chk("failure reason kept", m.problem == "no usable Bluetooth adapter found")

lines, ended = [], threading.Event()
code = []
e = anypad.Engine(lines.append, lambda c: (code.append(c), ended.set()),
                  ["/bin/bash", "-c", "echo hello; while read -r x; do :; done; echo bye; exit 0"])
time.sleep(.5)
chk("engine output arrives", lines == ["hello"], lines)
t = time.time()
e.stop()
chk("closing stdin ends it", ended.wait(5) and code == [0] and lines[-1] == "bye", (code, lines))
f = anypad.look()
chk("look() works here", set(f) == set(good), f)
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
