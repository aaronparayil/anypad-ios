#!/usr/bin/env python3
"""AnyPad for Linux: use any gamepad with your iPhone, iPad or Android device.

    python3 anypad.py             for an iPhone or iPad
    python3 anypad.py --android   for an Android phone or tablet
A file named "phone" next to this one, holding "android", makes --android the default.

A small window around relay.py. It runs as you; only the relay runs as root, through
the system's own password prompt (pkexec). Needs python3-gi, python3-dbus and GTK 3.
"""
import glob
import os
import shutil
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.realpath(__file__))
GOOD, BAD, WAIT = "good", "bad", "wait"

# The words for each kind of phone. The controller the phone sees is the same.
PHONES = {
    "ios": dict(app="AnyPad for iPhone and iPad", phone="iPhone or iPad", short="iPhone / iPad",
                pair="On it, open Settings > Bluetooth and tap Xbox Wireless Controller."),
    "android": dict(app="AnyPad for Android", phone="Android phone or tablet", short="Android",
                    pair="On it, open Bluetooth settings, tap Pair new device, then Xbox Wireless Controller."),
}


def pick_phone(argv):
    if "--android" in argv:
        return "android"
    if "--ios" in argv:
        return "ios"
    try:
        with open(os.path.join(HERE, "phone")) as f:
            return "android" if f.read().strip().lower() == "android" else "ios"
    except OSError:
        return "ios"


class Model:
    """What the window shows, worked out from the relay's messages. No GTK in here."""

    def __init__(self, phone="ios"):
        self.kind = phone
        self.words = PHONES[phone]
        self.running = self.stopping = self.played = False
        self.pad = self.laptop = self.phone = False
        self.title, self.hint, self.mood = "Checking...", "", WAIT
        self.problem = None

    def show(self, title, hint, mood):
        self.title, self.hint, self.mood = title, hint, mood

    def started(self):
        self.running, self.stopping, self.played = True, False, False
        self.phone, self.problem = False, None
        self.show("Starting...", "Enter your password if asked.", WAIT)

    def stop_asked(self):
        self.stopping = True
        self.show("Stopping...", "", WAIT)

    def ended(self, code):
        was_stopping = self.stopping
        self.running = self.stopping = self.phone = False
        if code in (126, 127) and not self.played:
            self.problem = "Permission was not given, so nothing was started."
        elif code != 0 and not was_stopping and not self.problem:
            self.problem = "Something went wrong. See the details."

    def line(self, text):
        if "controller found" in text:
            self.pad = True
        elif "waiting for the controller" in text or "controller disconnected" in text:
            self.pad = False
        if text.startswith("FAIL") or "] FAIL" in text:
            self.problem = text.split("FAIL:", 1)[-1].strip() or text
        if "the LAPTOP's Bluetooth was turned off" in text:
            self.problem = "Bluetooth was turned off on this laptop. Turn it on and start again."
        if "phone DISCONNECTED" in text:
            self.phone = False
        listening = "phone is listening" in text or (self.played and text.endswith("phone connected"))
        if listening:
            self.phone = self.played = True
        if "ready: on the phone" in text:
            self.laptop = True
        if self.stopping:
            return
        if listening:
            self.show("Connected: play!", "Open a game that supports controllers.", GOOD)
        elif "ready: on the phone" in text:
            self.show("Waiting for your " + self.words["phone"], self.words["pair"], WAIT)
        elif "accepting pairing" in text:
            self.show("Pairing...", "Tap Pair on the %s if it asks." % self.words["phone"], WAIT)
        elif text.endswith("phone connected"):
            self.show("Connecting...", "", WAIT)
        elif "phone DISCONNECTED" in text:
            self.show("Disconnected", "Open Bluetooth settings on the %s to reconnect." % self.words["phone"], WAIT)
        elif "removed an out-of-date pairing" in text:
            self.show("Pair it again", "Forget Xbox Wireless Controller on the %s, then pair it again." % self.words["phone"], WAIT)
        elif "pairing is closed (time is up)" in text and not self.played:
            self.show("Pairing closed", "Press Stop, then Start, to pair a phone. One that is already paired can still connect.", WAIT)

    def checks(self, facts):
        """facts -> list of (text, fix) for what still needs attention."""
        todo = []
        if not facts["modules"]:
            todo.append("Install python3-dbus and python3-gi")
        if not facts["bluez"]:
            todo.append("Install bluez")
        if not facts["pkexec"]:
            todo.append("Install pkexec (policykit)")
        if not facts["adapter"]:
            todo.append("No Bluetooth adapter found: turn Bluetooth on")
        if not facts["pad"]:
            todo.append("No gamepad yet: plug it in and turn it on")
        self.pad = facts["pad"]
        # A gamepad can be plugged in later, so it does not block Start.
        ready = all(facts[k] for k in ("modules", "bluez", "pkexec", "adapter"))
        self.laptop = ready
        if self.problem:
            self.show("It stopped", self.problem, BAD)
        elif ready:
            hint = "Only pair your own phone: one can pair without a code, for 3 minutes."
            if self.kind == "android":
                hint += " Bluetooth on this laptop is LE only while AnyPad runs."
            self.show("Ready to start", hint, GOOD)
        else:
            self.show("Almost there", "Sort out the items below.", WAIT)
        return ready, todo


def look():
    """Facts about this laptop. Cheap: no programs are started."""
    sys.path.insert(0, HERE)
    modules, pad = True, False
    try:
        import dbus      # noqa: F401
        import relay
        with open("/proc/bus/input/devices") as f:
            pad = relay.find_pad(f.read(), "045e:028e") is not None
    except ImportError:
        modules = False
    except OSError:
        pass
    return {
        "modules": modules, "pad": pad,
        "bluez": shutil.which("bluetoothctl") is not None,
        "pkexec": shutil.which("pkexec") is not None,
        "adapter": bool(glob.glob("/sys/class/bluetooth/hci*")),
    }


class Engine:
    """The relay as root; closing its stdin stops it cleanly."""

    def __init__(self, on_line, on_end, command=None, phone="ios"):
        command = command or ["pkexec", "/bin/bash", os.path.join(HERE, "app_engine.sh"), "run", phone]
        self.p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1)
        self.on_line, self.on_end = on_line, on_end
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for text in self.p.stdout:
            self.on_line(text.rstrip())
        self.on_end(self.p.wait())

    def stop(self):
        try:
            self.p.stdin.close()
        except OSError:
            pass


CSS = b"""
.head { background-image: linear-gradient(110deg, #4f46e5, #0ea5e9); padding: 18px 20px; }
.head label { color: white; }
.head .name { font-size: 22px; font-weight: 600; }
.node { font-size: 24px; padding: 8px 12px; border-radius: 30px; border: 2px solid alpha(currentColor, 0.25); opacity: 0.55; }
.node.on { border-color: #22a559; opacity: 1; }
.link { color: alpha(currentColor, 0.3); font-weight: 700; }
.link.on { color: #22a559; }
.small { font-size: 12px; }
.title { font-size: 19px; font-weight: 600; }
.title.good { color: #22a559; }
.title.bad { color: #d64550; }
.go { font-size: 16px; font-weight: 600; padding: 12px; border-radius: 12px; }
"""


def run_window(phone="ios"):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

    class Window(Gtk.ApplicationWindow):
        def __init__(self, app):
            words = PHONES[phone]
            super().__init__(application=app, title=words["app"], resizable=False)
            self.model, self.engine, self.close_after = Model(phone), None, False
            icon = os.path.join(HERE, "anypad.png")
            if os.path.exists(icon):
                self.set_icon_from_file(icon)
            css = Gtk.CssProvider()
            css.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.add(box)
            head = Gtk.Box(spacing=14)
            head.get_style_context().add_class("head")
            if os.path.exists(icon):
                head.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(icon, 56, 56)), False, False, 0)
            names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
            names.add(self.label("AnyPad", "name", 0))
            names.add(self.label("Any gamepad, on your " + words["phone"], None, 0))
            head.add(names)
            box.add(head)

            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=20)
            body.set_size_request(420, -1)
            box.add(body)
            row = Gtk.Box(halign=Gtk.Align.CENTER, spacing=10)
            self.nodes, self.links = [], []
            for i, (glyph, text) in enumerate((("\U0001F3AE", "Gamepad"), ("\U0001F4BB", "This laptop"), ("\U0001F4F1", words["short"]))):
                if i:
                    link = self.label("━━", "link", 0.5)
                    link.set_valign(Gtk.Align.START)
                    link.set_margin_top(16)
                    self.links.append(link)
                    row.add(link)
                node = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                face = self.label(glyph, "node", 0.5)
                face.set_halign(Gtk.Align.CENTER)
                node.add(face)
                node.add(self.label(text, "small", 0.5))
                self.nodes.append(face)
                row.add(node)
            body.add(row)
            self.title = self.label("", "title", 0.5)
            self.hint = self.label("", None, 0.5)
            self.hint.set_line_wrap(True)
            self.hint.set_max_width_chars(48)
            self.hint.set_justify(Gtk.Justification.CENTER)
            self.todo = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            self.go = Gtk.Button(label="Start")
            self.go.get_style_context().add_class("go")
            self.go.connect("clicked", self.on_go)
            for w in (self.title, self.hint, self.todo, self.go):
                body.add(w)
            self.details = Gtk.Expander(label="Details")
            scroll = Gtk.ScrolledWindow(min_content_height=150)
            self.log = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
            scroll.add(self.log)
            self.details.add(scroll)
            body.add(self.details)
            undo = Gtk.LinkButton(uri="undo:", label="Undo AnyPad's Bluetooth settings")
            undo.connect("activate-link", self.on_undo)
            self.undo = undo
            body.add(undo)

            self.connect("delete-event", self.on_close)
            self.connect("focus-in-event", lambda *a: self.refresh() and False)
            GLib.timeout_add_seconds(10, self.on_timer)
            self.show_all()
            self.refresh()

        def label(self, text, cls, xalign):
            w = Gtk.Label(label=text, xalign=xalign)
            if cls:
                w.get_style_context().add_class(cls)
            return w

        def on_timer(self):
            if self.engine is None and self.is_active():
                self.refresh()
            return True

        def refresh(self):
            m = self.model
            for w in self.todo.get_children():
                self.todo.remove(w)
            ready = True
            if not m.running:
                ready, todo = m.checks(look())
                for text in todo:
                    self.todo.add(self.label("•  " + text, None, 0))
                self.todo.show_all()
            self.go.set_sensitive(m.running and not m.stopping or (not m.running and ready))
            self.go.set_label("Stopping..." if m.stopping else "Stop" if m.running else "Start")
            ctx = self.go.get_style_context()
            (ctx.remove_class if m.running else ctx.add_class)("suggested-action")
            self.undo.set_visible(not m.running)
            self.title.set_text(m.title)
            self.hint.set_text(m.hint)
            for mood in (GOOD, BAD, WAIT):
                self.title.get_style_context().remove_class(mood)
            self.title.get_style_context().add_class(m.mood)
            lit = (m.pad, m.laptop, m.phone)
            for w, on in list(zip(self.nodes, lit)) + list(zip(self.links, (lit[0] and lit[1], lit[1] and lit[2]))):
                (w.get_style_context().add_class if on else w.get_style_context().remove_class)("on")

        def on_go(self, _):
            if self.engine:
                self.model.stop_asked()
                self.engine.stop()
            else:
                self.log.get_buffer().set_text("")
                self.model.started()
                try:
                    self.engine = Engine(lambda t: GLib.idle_add(self.on_line, t), lambda c: GLib.idle_add(self.on_end, c), phone=phone)
                except OSError as e:
                    self.model.running = False
                    self.model.problem = str(e)
            self.refresh()

        def on_line(self, text):
            self.append(text)
            self.model.line(text)
            self.refresh()

        def append(self, text):
            buf = self.log.get_buffer()
            buf.insert(buf.get_end_iter(), text + "\n")
            if buf.get_line_count() > 500:
                buf.delete(buf.get_start_iter(), buf.get_iter_at_line(200))

        def on_end(self, code):
            self.engine = None
            self.model.ended(code)
            if self.model.problem:
                self.details.set_expanded(True)
            if self.close_after:
                self.destroy()
                return
            self.refresh()

        def on_close(self, *_):
            if not self.engine:
                return False
            self.close_after = True
            self.model.stop_asked()
            self.engine.stop()
            self.refresh()
            return True

        def on_undo(self, *_):
            Engine(lambda t: GLib.idle_add(self.append, t), lambda c: GLib.idle_add(self.details.set_expanded, True),
                   ["pkexec", "/bin/bash", os.path.join(HERE, "app_engine.sh"), "restore"])
            return True

    app = Gtk.Application(application_id="io.github.aaronparayil.anypad")

    def activate(a):
        windows = a.get_windows()
        (windows[0].present() if windows else Window(a))
    app.connect("activate", activate)
    return app.run([])


if __name__ == "__main__":
    try:
        sys.exit(run_window(pick_phone(sys.argv[1:])))
    except (ImportError, ValueError) as e:
        print("AnyPad's window needs GTK 3: sudo apt install python3-gi gir1.2-gtk-3.0 (%s)" % e)
        print("Or play from the terminal: bash run.sh")
        sys.exit(1)
