import os, select, struct, sys, time
n = {"S": 0, "N": 0}
buf = b""
end = time.time() + 4
bad = 0
last = None
print("child started", flush=True)
while time.time() < end:
    if select.select([0], [], [], .2)[0]:
        data = os.read(0, 4096)
        if not data:
            print("stdin closed by Windows", flush=True)
            break
        buf += data
        while len(buf) >= 14:
            f = struct.unpack_from("<BBHBBhhhh", buf)
            buf = buf[14:]
            if f[0] != 0xA5 or chr(f[1]) not in n:
                bad += 1
                continue
            n[chr(f[1])] += 1
            last = f[2:]
print("@rumble 0 0 100", flush=True)
print("frames", n, "bad", bad, "leftover", len(buf), "last", last, flush=True)
