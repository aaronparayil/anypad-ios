import sys, time, json, dbus, dbus.service, dbus.mainloop.glib
from gi.repository import GLib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()
name = dbus.service.BusName("org.bluez", bus)
out = open(sys.argv[1], "w")


def w(**k):
    out.write(json.dumps(k) + "\n")
    out.flush()


P = "org.freedesktop.DBus.Properties"


class Root(dbus.service.Object):
    @dbus.service.method("org.freedesktop.DBus.ObjectManager", out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        e = dbus.Dictionary({}, signature="sv")
        return {dbus.ObjectPath("/org/bluez/hci0"): {
            "org.bluez.Adapter1": e, "org.bluez.GattManager1": e,
            "org.bluez.LEAdvertisingManager1": e}}


class Org(dbus.service.Object):
    @dbus.service.method("org.bluez.AgentManager1", in_signature="os", sender_keyword="sender")
    def RegisterAgent(self, p, c, sender=None):
        w(ev="agent", cap=str(c), sender=str(sender), path=str(p))

    @dbus.service.method("org.bluez.AgentManager1", in_signature="o")
    def RequestDefaultAgent(self, p):
        pass

    @dbus.service.method("org.bluez.AgentManager1", in_signature="o")
    def UnregisterAgent(self, p):
        w(ev="unagent")


import os
LAST_PAIRABLE = 0.0
POWER = {"on": False, "refuse": int(os.environ.get("REFUSE", "2"))}


class Ad(dbus.service.Object):
    @dbus.service.method(P, in_signature="ss", out_signature="v")
    def Get(self, i, p):
        if p == "Pairable":
            return dbus.Boolean(os.environ.get("OLD_PAIRABLE", "0") == "1")
        return dbus.Boolean(POWER["on"]) if p == "Powered" else "ubuntu"

    @dbus.service.method(P, in_signature="ssv")
    def Set(self, i, p, v):
        global LAST_PAIRABLE
        if p == "Pairable":
            # like real BlueZ: Busy while the previous change is still being applied
            if time.time() - LAST_PAIRABLE < 0.5:
                w(ev="busy")
                raise dbus.exceptions.DBusException("", name="org.bluez.Error.Busy")
            LAST_PAIRABLE = time.time()
        w(ev="set", prop=str(p), val=str(v))
        if p == "Powered":
            POWER["refuse"] -= 1
            if POWER["refuse"] >= 0:
                raise dbus.exceptions.DBusException("Failed", name="org.bluez.Error.Failed")
            POWER["on"] = True

    @dbus.service.method("org.bluez.GattManager1", in_signature="oa{sv}", sender_keyword="sender")
    def RegisterApplication(self, path, o, sender=None):
        def go():
            om = dbus.Interface(bus.get_object(sender, path, introspect=False),
                                "org.freedesktop.DBus.ObjectManager")
            om.GetManagedObjects(reply_handler=got,
                                 error_handler=lambda e: w(ev="err", e=str(e)))
            return False

        def got(objs):
            chars = []
            for p, i in sorted(objs.items()):
                c = i.get("org.bluez.GattCharacteristic1")
                if c:
                    chars.append([str(p), str(c["UUID"])[4:8], [str(f) for f in c["Flags"]]])
            w(ev="app", n=len(objs), chars=chars, sender=str(sender))
            inp = [c for c in chars if c[1] == "2a4d" and "notify" in c[2]][0][0]
            bus.add_signal_receiver(
                lambda i, c, inv: w(ev="rep", t=time.time(), v=bytes(c["Value"]).hex()),
                dbus_interface=P, signal_name="PropertiesChanged", path=inp)
            dbus.Interface(bus.get_object(sender, inp, introspect=False),
                           "org.bluez.GattCharacteristic1").StartNotify(
                reply_handler=lambda: w(ev="sub"), error_handler=lambda e: w(ev="err", e=str(e)))
        GLib.idle_add(go)

    @dbus.service.method("org.bluez.Adapter1", in_signature="o")
    def RemoveDevice(self, p):
        w(ev="removed", path=str(p))

    @dbus.service.method("org.bluez.GattManager1", in_signature="o")
    def UnregisterApplication(self, p):
        w(ev="unapp")

    @dbus.service.method("org.bluez.LEAdvertisingManager1", in_signature="oa{sv}")
    def RegisterAdvertisement(self, p, o):
        w(ev="adv")

    @dbus.service.method("org.bluez.LEAdvertisingManager1", in_signature="o")
    def UnregisterAdvertisement(self, p):
        w(ev="unadv")


class Dev(dbus.service.Object):
    @dbus.service.signal(P, signature="sa{sv}as")
    def PropertiesChanged(self, i, c, inv):
        pass

    paired = True

    @dbus.service.method(P, in_signature="ss", out_signature="v")
    def Get(self, i, p):
        return dbus.Boolean(self.paired)

    @dbus.service.method("test.Dev", in_signature="b")
    def SetPaired(self, on):
        self.paired = bool(on)

    @dbus.service.method("test.Dev", in_signature="b")
    def Link(self, on):
        self.PropertiesChanged("org.bluez.Device1", {"Connected": dbus.Boolean(on)}, [])

    @dbus.service.method("test.Dev")
    def Pair(self):
        self.PropertiesChanged("org.bluez.Device1", {"Paired": dbus.Boolean(True)}, [])


devs = [Dev(bus, "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_AA"), Dev(bus, "/org/bluez/hci0/dev_BB_BB_BB_BB_BB_BB")]
objs = (Root(bus, "/"), Org(bus, "/org/bluez"), Ad(bus, "/org/bluez/hci0"))
GLib.MainLoop().run()
