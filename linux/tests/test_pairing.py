import json, os, signal, subprocess, sys, time
KIT, SP = sys.argv[1], sys.argv[2]
OUT = SP + "/gate_out.jsonl"
A, B = ["/org/bluez/hci0/dev_" + "_".join([x * 2] * 6) for x in "AB"]
ok = True


def chk(n, c, extra=""):
    global ok
    ok &= bool(c)
    print("PASS" if c else "FAIL", n, extra, flush=True)


class Run:
    def __init__(self, *args, script="relay.py", old="0"):
        self.d = subprocess.Popen(["dbus-daemon", "--session", "--print-address", "--nofork"],
                                  stdout=subprocess.PIPE, text=True)
        self.env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS=self.d.stdout.readline().strip(),
                        PYTHONDONTWRITEBYTECODE="1", REFUSE="0", OLD_PAIRABLE=old)
        self.m = subprocess.Popen([sys.executable, SP + "/mock_bluez.py", OUT], env=self.env)
        time.sleep(1)
        self.r = subprocess.Popen([sys.executable, "-W", "ignore", KIT + "/" + script, *args],
                                  env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(1.5)

    def log(self):
        return [json.loads(x) for x in open(OUT)]

    def pairable(self):
        return [x["val"] for x in self.log() if x["ev"] == "set" and x["prop"] == "Pairable"]

    def send(self, dest, path, method, *args):
        p = subprocess.run(["dbus-send", "--bus=" + self.env["DBUS_SYSTEM_BUS_ADDRESS"], "--print-reply",
                            "--dest=" + dest, path, method, *args], capture_output=True, text=True)
        return "ok" if p.returncode == 0 else ("rejected" if "org.bluez.Error.Rejected" in p.stderr else p.stderr)

    def agent(self, method, *args):
        a = [x for x in self.log() if x["ev"] == "agent"][0]
        return self.send(a["sender"], a["path"], "org.bluez.Agent1." + method, *args)

    def ask(self, dev):
        return self.agent("RequestAuthorization", "objpath:" + dev)

    def pair(self, dev):
        self.send("org.bluez", dev, "test.Dev.Pair")
        time.sleep(.2)

    def stop(self):
        self.r.send_signal(signal.SIGINT)
        try:
            o, _ = self.r.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.r.kill()
            o, _ = self.r.communicate()
        p = self.pairable()
        self.m.kill()
        self.d.kill()
        return o, self.r.returncode, p


for script in ("relay.py", "pairing_test.py"):
    print("==", script)
    t = Run(script=script)
    p = t.pairable()
    chk("locked first, then opened", p == ["0", "1"], p)
    chk("first phone allowed", t.ask(A) == "ok")
    chk("same phone asks again", t.ask(A) == "ok")
    chk("second device refused meanwhile", t.ask(B) == "rejected")
    chk("numeric confirmation from second device refused",
        t.agent("RequestConfirmation", "objpath:" + B, "uint32:123456") == "rejected")
    t.pair(A)
    chk("refused at once after pairing", t.ask(B) == "rejected" and t.ask(A) == "rejected")
    chk("switch still on while keys settle", t.pairable()[-1] == "1")
    time.sleep(6)
    chk("switch off after pairing", t.pairable()[-1] == "0")
    chk("still refused", t.ask(B) == "rejected")
    chk("audio refused", t.agent("AuthorizeService", "objpath:" + A,
                                 "string:0000110d-0000-1000-8000-00805f9b34fb") == "rejected")
    chk("PIN and passkey refused", t.agent("RequestPinCode", "objpath:" + A) == "rejected"
        and t.agent("RequestPasskey", "objpath:" + A) == "rejected")
    o, rc, p = t.stop()
    chk("clean exit, switch restored off", rc == 0 and p[-1] == "0" and "Traceback" not in o, (rc, p))
    chk("nothing marked trusted", "Trusted" not in json.dumps(p) and "rusted" not in o)
    print(o)

print("== kernel-accepted pairing (agent never asked)")
t = Run()
t.pair(B)
time.sleep(6)
chk("locks anyway", t.pairable()[-1] == "0" and t.ask(A) == "rejected")
t.pair(A)
o, rc, p = t.stop()
chk("warns about pairing while closed", "paired while pairing was closed" in o and "AA:AA:AA:AA:AA:AA" in o)

print("== cancelled attempt frees the slot")
t = Run()
chk("A asks", t.ask(A) == "ok")
chk("B refused", t.ask(B) == "rejected")
t.agent("Cancel")
chk("B allowed after cancel", t.ask(B) == "ok")
t.stop()

print("== window times out; previous setting was on")
t = Run("--pair-seconds", "3", old="1")
chk("open", t.pairable()[-1] == "1")
time.sleep(3)
chk("closed on time", t.pairable()[-1] == "0" and t.ask(A) == "rejected")
o, rc, p = t.stop()
chk("previous setting restored", p[-1] == "1", p)

print("== phone mid-pairing when the timer runs out")
t = Run("--pair-seconds", "3")
chk("A starts", t.ask(A) == "ok")
time.sleep(4)
chk("still open for A, not for B", t.pairable()[-1] == "1" and t.ask(B) == "rejected")
t.pair(A)
time.sleep(6)
o, rc, p = t.stop()
chk("locked afterwards, no false warning", p[-2:] == ["0", "0"] and "WARNING: dev" not in o and "closed (a phone" in o, p)

print("== pairing off")
t = Run("--pair-seconds", "0")
chk("never opened", "1" not in t.pairable() and t.ask(A) == "rejected", t.pairable())
o, rc, p = t.stop()
chk("says so", "pairing is off" in o)


def flap(t, dev, n, secs):
    for _ in range(n):
        t.send("org.bluez", dev, "test.Dev.Link", "boolean:true")
        time.sleep(secs)
        t.send("org.bluez", dev, "test.Dev.Link", "boolean:false")
        time.sleep(.15)


def removed(t):
    return [x["path"] for x in t.log() if x["ev"] == "removed"]


print("== a known phone pairs again")
t = Run()
t.send("org.bluez", A, "test.Dev.SetPaired", "boolean:true")
t.send("org.bluez", A, "test.Dev.Link", "boolean:true")
chk("re-pairing allowed", t.ask(A) == "ok")
chk("not for a second device", t.ask(B) == "rejected")
time.sleep(9.5)
chk("locks once it stayed connected", t.pairable()[-1] == "0" and t.ask(B) == "rejected" and t.ask(A) == "rejected")
o, rc, p = t.stop()
chk("says so", "pairing again from a known phone" in o and "has paired again" in o and "Traceback" not in o)

print("== re-pairing that fails does not lock")
t = Run()
t.send("org.bluez", A, "test.Dev.SetPaired", "boolean:true")
chk("allowed", t.ask(A) == "ok")
time.sleep(9.5)
chk("still open for that phone", t.pairable()[-1] == "1" and t.ask(A) == "ok" and t.ask(B) == "rejected")
t.stop()

print("== re-pairing refused when pairing is off")
t = Run("--pair-seconds", "0")
t.send("org.bluez", A, "test.Dev.SetPaired", "boolean:true")
chk("refused", t.ask(A) == "rejected")
t.stop()

print("== out-of-date pairing")
t = Run()
t.send("org.bluez", A, "test.Dev.SetPaired", "boolean:true")
flap(t, A, 3, .2)
chk("three drops: not yet", removed(t) == [])
flap(t, A, 1, .2)
chk("fourth short drop removes it", removed(t) == [A], removed(t))
flap(t, A, 6, .2)
chk("removed only once", removed(t) == [A])
chk("pairing still open for the phone", t.ask(A) == "ok")
o, rc, p = t.stop()
chk("tells the user", "removed an out-of-date pairing" in o and "Traceback" not in o)

print("== not a stale pairing")
t = Run()
t.send("org.bluez", A, "test.Dev.SetPaired", "boolean:false")
flap(t, A, 6, .2)
chk("unpaired device is left alone", removed(t) == [])
t.send("org.bluez", B, "test.Dev.SetPaired", "boolean:true")
flap(t, B, 2, .2); flap(t, B, 1, 8.4); flap(t, B, 2, .2)
chk("a long connection resets the count", removed(t) == [], removed(t))
t.stop()

print("== the reason for a drop is logged")
t = Run()
t.send("org.bluez", A, "test.Dev.Drop")
time.sleep(.3)
o, rc, p = t.stop()
chk("reason and link", "LE link down" in o and "LE link dropped: Timeout (Connection timeout)" in o and "Traceback" not in o, o[-300:])

print("== pairing closed: advice only")
t = Run("--pair-seconds", "0")
t.send("org.bluez", A, "test.Dev.SetPaired", "boolean:true")
flap(t, A, 5, .2)
o, rc, p = t.stop()
chk("not removed, advice given", "removed an out" not in o and "keeps dropping" in o)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
