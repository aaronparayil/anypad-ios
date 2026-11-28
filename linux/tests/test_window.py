"""The Linux app's real GTK window, with a stand-in relay: python3 test_window.py KIT TESTS ios|android [shots dir]

Needs GTK 3 and a display (in CI: xvfb-run). Saves a screenshot of each step if a folder is given.
"""
import os, sys, threading
KIT, SP, PHONE = sys.argv[1], sys.argv[2], sys.argv[3]
SHOTS = sys.argv[4] if len(sys.argv) > 4 else None
sys.path.insert(0, KIT)
sys.dont_write_bytecode = True
import anypad
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

ok = True
WORDS = anypad.PHONES[PHONE]


def chk(n, c, extra=""):
    global ok
    ok &= bool(c)
    print("PASS" if c else "FAIL", PHONE + ":", n, "" if c else extra, flush=True)


anypad.look = lambda: dict(modules=True, bluez=True, pkexec=True, adapter=True, pad=True)
started = []


class FakeEngine:
    """Stands in for the relay: the test feeds it lines; Stop ends it."""
    def __init__(self, on_line, on_end, command=None, phone="ios"):
        self.on_line, self.on_end = on_line, on_end
        started.append(phone)

    def say(self, text):
        threading.Thread(target=self.on_line, args=("[relay 1.0s] " + text,)).start()

    def stop(self):
        threading.Thread(target=self.on_end, args=(0,)).start()


anypad.Engine = FakeEngine


def labels(widget):
    found = []
    if isinstance(widget, Gtk.Label):
        found.append(widget.get_text())
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found += labels(child)
    return found


def shot(win, name):
    if not SHOTS:
        return
    os.makedirs(SHOTS, exist_ok=True)
    gdk = win.get_window()
    pix = Gdk.pixbuf_get_from_window(gdk, 0, 0, gdk.get_width(), gdk.get_height())
    if pix:
        pix.savev(os.path.join(SHOTS, "%s-%s.png" % (PHONE, name)), "png", [], [])


steps = []


def step(f):
    steps.append(f)
    return f


@step
def ready(win):
    chk("window title", win.get_title() == WORDS["app"], win.get_title())
    text = labels(win)
    chk("header names the phone", "Any gamepad, on your " + WORDS["phone"] in text, text)
    chk("phone under the path", WORDS["short"] in text, text)
    chk("ready to start", win.model.title == "Ready to start" and win.go.get_label() == "Start"
        and win.go.get_sensitive(), (win.model.title, win.go.get_label()))
    chk("LE-only note only for Android", ("LE only" in win.hint.get_text()) == (PHONE == "android"), win.hint.get_text())
    other = "iPhone" if PHONE == "android" else "Android"
    chk("the other phone is not mentioned", not any(other in t for t in text), text)
    shot(win, "1-ready")
    win.go.clicked()


@step
def starting(win):
    chk("engine started for this phone", started == [PHONE], started)
    chk("button turns into Stop", win.go.get_label() == "Stop", win.go.get_label())
    win.engine.say("controller found: Test Pad (/dev/input/event3), rumble offered by driver")
    win.engine.say("ready: on the phone, open whatever and tap 'Xbox Wireless Controller'")


@step
def waiting(win):
    chk("waiting for the phone", win.title.get_text() == "Waiting for your " + WORDS["phone"], win.title.get_text())
    chk("pairing steps shown", win.hint.get_text() == WORDS["pair"], win.hint.get_text())
    shot(win, "2-waiting")
    win.engine.say("phone is listening: play!")


@step
def playing(win):
    chk("connected", win.title.get_text() == "Connected: play!", win.title.get_text())
    lit = [n.get_style_context().has_class("on") for n in win.nodes]
    chk("gamepad, laptop and phone lit", lit == [True, True, True], lit)
    shot(win, "3-playing")
    win.go.clicked()


@step
def stopped(win):
    chk("stopped cleanly", win.engine is None and win.go.get_label() == "Start" and win.model.title == "Ready to start",
        (win.engine, win.go.get_label(), win.model.title))
    win.close()


def run_steps():
    app = Gio.Application.get_default()
    wins = app.get_windows() if app else []
    if not wins:
        return True
    win = wins[0]
    if steps:
        try:
            steps.pop(0)(win)
        except Exception as e:      # a broken step must not hang the test
            chk("step ran", False, repr(e))
            win.destroy()
            return False
        return True
    return False


GLib.timeout_add(700, run_steps)
GLib.timeout_add_seconds(30, lambda: (chk("finished in time", False), os._exit(1)))
code = anypad.run_window(PHONE)
chk("window closed and app ended", code == 0 and not steps, (code, len(steps)))
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
