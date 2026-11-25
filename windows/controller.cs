// Plays iPhone/iPad games with an Xbox-type gamepad plugged into this Windows PC.
// Windows reads the gamepad; the Linux relay in WSL poses as the Bluetooth controller.
//
//   controller.exe                 play (asks before taking Bluetooth from Windows)
//   controller.exe --check         show what the gamepad is doing
//   controller.exe --test-rumble   run the gamepad's motors
//   options: --busid 1-14   --rumble PERCENT   --pair-seconds N
//   --why                      show why Windows last refused to release the adapter
//   --forget                   move saved phone pairings aside, so a phone can pair afresh
//   --preflight                only check whether it is safe to start; changes nothing
//
// Build with build.cmd (the C# compiler that ships with Windows; nothing is downloaded).
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Management;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Windows.Devices.Radios;
using Windows.Foundation;

// Small stand-in for a Windows SDK helper, so no SDK is needed to build.
static class WinRt
{
    public static TaskAwaiter<T> GetAwaiter<T>(this IAsyncOperation<T> operation)
    {
        var done = new TaskCompletionSource<T>();
        operation.Completed = (op, status) =>
        {
            try
            {
                if (status == AsyncStatus.Completed) done.TrySetResult(op.GetResults());
                else done.TrySetException(op.ErrorCode ?? new Exception("Windows reported an unknown error"));
            }
            catch (Exception e) { done.TrySetException(e); }
        };
        return done.Task.GetAwaiter();
    }
}

static class Program
{
    [StructLayout(LayoutKind.Sequential)]
    struct Gamepad { public ushort Buttons; public byte LT, RT; public short LX, LY, RX, RY; }
    [StructLayout(LayoutKind.Sequential)]
    struct State { public uint Packet; public Gamepad Pad; }
    [StructLayout(LayoutKind.Sequential)]
    struct Vibration { public ushort Strong, Weak; }

    // Entry 100 also reports the Xbox button; the documented one does not.
    [DllImport("xinput1_4.dll", EntryPoint = "#100")]
    static extern uint XInputGetStateEx(uint slot, ref State state);
    [DllImport("xinput1_4.dll")]
    static extern uint XInputSetState(uint slot, ref Vibration vibration);
    [DllImport("winmm.dll")]
    static extern uint timeBeginPeriod(uint ms);
    delegate bool CtrlHandler(uint type);
    [DllImport("kernel32.dll")]
    static extern bool SetConsoleCtrlHandler(CtrlHandler handler, bool add);

    const string Usbipd = @"C:\Program Files\usbipd-win\usbipd.exe";
    static readonly object Out = new object();
    static readonly object CleanupLock = new object();
    static volatile bool stop;
    static CtrlHandler keepHandler;
    static string busId = "1-14";
    static bool attached, prepared, sharedByUs, cleaned;
    static Process relay;

    static void Say(string text)
    {
        lock (Out) Console.WriteLine(text);
    }

    static int Main(string[] args)
    {
        if (Opt(args, "--busid") != null) busId = Opt(args, "--busid");
        if (!Regex.IsMatch(busId, @"^\d+-\d+$")) { Say("--busid must look like 1-14"); return 2; }
        timeBeginPeriod(1);
        Console.CancelKeyPress += (s, e) => { e.Cancel = true; stop = true; };
        if (args.Contains("--check")) return Check();
        if (args.Contains("--test-rumble")) return TestRumble();
        if (args.Contains("--why")) { Say(WhyRefused(DateTime.Now.AddDays(-1)) ?? "No refusal in the last 24 hours."); return 0; }
        if (args.Contains("--forget"))
            return Run("wsl.exe", "-u root -- bash \"" + Wsl(Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, @"in_wsl.sh"))) + "\" forget");
        if (args.Contains("--preflight")) return Preflight(true) ? 0 : 1;

        var relayArgs = new List<string>();
        foreach (var name in new[] { "--rumble", "--pair-seconds" })
        {
            string v = Opt(args, name);
            if (v == null) continue;
            int n;
            if (!int.TryParse(v, out n) || n < 0) { Say(name + " needs a number"); return 2; }
            relayArgs.Add(name + " " + n);
        }

        bool first;
        var single = new Mutex(true, "Local\\anypad-windows-controller", out first);
        if (!first) { Say("It is already running in another window."); return 3; }

        // Closing the window gives a few seconds: at least hand the adapter back to WSL's host.
        keepHandler = type => { if (type == 2 || type == 5 || type == 6) { stop = true; Cleanup(true); } return false; };
        SetConsoleCtrlHandler(keepHandler, true);
        try
        {
            // For testing: run any program in place of WSL, without touching Bluetooth.
            string child = Opt(args, "--child");
            if (child != null)
            {
                int cut = child.IndexOf(' ');
                return Bridge(cut < 0 ? child : child.Substring(0, cut), cut < 0 ? "" : child.Substring(cut + 1));
            }
            return Play(string.Join(" ", relayArgs));
        }
        catch (Exception e)
        {
            Say("FAIL: " + e.Message);
            return 1;
        }
        finally
        {
            Cleanup(false);
            GC.KeepAlive(single);
        }
    }

    static string Opt(string[] args, string name)
    {
        int i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    // ---- Play ----

    static int Play(string relayArgs)
    {
        if (!File.Exists(Usbipd)) { Say("usbipd-win is not installed."); return 1; }
        string here = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.GetFullPath(Path.Combine(here, @"in_wsl.sh"));
        string kit = Path.GetFullPath(Path.Combine(here, @"..\linux"));
        if (!File.Exists(script) || !File.Exists(Path.Combine(kit, "relay.py"))) { Say("Missing " + script + " or the linux folder next to this one."); return 1; }

        string line = DeviceLine();
        if (line == null) { Say("No USB device " + busId + ". See: usbipd list"); return 1; }
        if (line.IndexOf("8087:", StringComparison.Ordinal) < 0)
        {
            Say(busId + " does not look like the Intel Bluetooth adapter:\n  " + line.Trim());
            return 1;
        }
        if (FirstPad() < 0) Say("No gamepad seen yet. Plug in the dongle and turn the Redgear on; you can do it now.");

        bool shared = line.IndexOf("Not shared", StringComparison.OrdinalIgnoreCase) < 0;
        if (line.IndexOf("forced", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            Say("The adapter is force-shared. Undo that first, in an admin terminal, then restart:  usbipd unbind --busid " + busId);
            return 1;
        }
        if (line.IndexOf("Attached", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            // Only one copy runs at a time, so this is left over from a run that was cut off.
            Say("The adapter was left attached by an earlier run. Releasing it first...");
            Run("wsl.exe", "-u root -- bash \"" + Wsl(script) + "\" restore");
            Run(Usbipd, "detach --busid " + busId);
            Say("Released. Run this again.");
            return 1;
        }
        Say("");
        Say("This takes Bluetooth away from Windows until you stop: earbuds, Bluetooth mouse and keyboard disconnect.");
        Say("While it is shared, other devices on your network could try to use the adapter, so avoid public Wi-Fi.");
        Say("");
        if (!Preflight(false)) return 1;
        Say("Windows cannot release the adapter while one of its own Bluetooth devices is in use.");
        if (!Ask("Type y to continue" + (shared ? "" : " (Windows will ask for admin approval)") + " [y/N] ")) { Say("Nothing was changed."); return 0; }
        if (!shared)
        {
            if (!Elevated("bind --busid " + busId)) { Say("The adapter was not shared. Nothing was changed."); return 1; }
            sharedByUs = true;
            for (int i = 0; i < 20 && !stop; i++)
            {
                line = DeviceLine();
                if (line != null && line.IndexOf("Not shared", StringComparison.OrdinalIgnoreCase) < 0) break;
                Thread.Sleep(500);
            }
        }
        if (stop) return 0;

        prepared = true;
        if (Run("wsl.exe", "-u root -- bash \"" + Wsl(script) + "\" prepare") != 0) { Say("FAIL: preparing WSL"); return 1; }
        if (stop) return 0;
        if (!Attach()) return stop ? 0 : 1;
        attached = true;
        if (stop) return 0;
        return Bridge("wsl.exe", "-u root -- bash \"" + Wsl(script) + "\" relay \"" + Wsl(kit) + "\" " + relayArgs);
    }

    // Everything that blocked earlier tries, checked before anything is changed.
    static bool Preflight(bool reportOnly)
    {
        bool ok = true;
        string radio = RadioState().GetAwaiter().GetResult();
        if (radio == null)
        {
            string line = DeviceLine();
            Say(line != null && line.IndexOf("Attached", StringComparison.OrdinalIgnoreCase) >= 0
                ? "STOP: WSL is using the adapter. If no controller.exe is running, start it to release the adapter."
                : "STOP: Windows lists no Bluetooth radio. Restart the PC before trying again.");
            ok = false;
        }
        else if (radio != "Off")
        {
            Say("STOP: Bluetooth is " + radio + " in Windows. Turn it OFF first (Win+A, then Bluetooth), then run this again.");
            ok = false;
        }
        var phones = new List<string>();
        var audio = new List<string>();
        try
        {
            // 111F is a phone's hands-free audio; 110A/110B/111E are headphones and music.
            using (var q = new ManagementObjectSearcher("SELECT Name, PNPDeviceID FROM Win32_PnPEntity WHERE PNPDeviceID LIKE 'BTHENUM%'"))
                foreach (ManagementObject o in q.Get())
                {
                    var m = Regex.Match((string)o["PNPDeviceID"] ?? "", @"^BTHENUM\\\{0000(110A|110B|111E|111F)-", RegexOptions.IgnoreCase);
                    if (!m.Success) continue;
                    string id = (string)o["PNPDeviceID"];
                    string name = DeviceName(id) ?? "\"" + (string)o["Name"] + "\"";
                    var list = m.Groups[1].Value.ToUpperInvariant() == "111F" ? phones : audio;
                    if (!list.Contains(name)) list.Add(name);
                }
        }
        catch (Exception e) { Say("Could not list Bluetooth devices: " + e.Message); }
        if (phones.Count > 0)
        {
            Say("STOP: these phones are paired with Windows and have blocked the adapter: " + string.Join(", ", phones)
                + ". Remove them in Settings > Bluetooth & devices.");
            ok = false;
        }
        if (audio.Count > 0)
            Say("Note: paired audio devices can block it too if they are in use: " + string.Join(", ", audio.Except(phones)) + ".");
        if (ok && reportOnly) Say("Ready to start: Bluetooth is off and no phone is paired with Windows.");
        return ok;
    }

    static async Task<string> RadioState()
    {
        foreach (var r in await Radio.GetRadiosAsync())
            if (r.Kind == RadioKind.Bluetooth) return r.State.ToString();
        return null;
    }

    static bool Attach()
    {
        for (int attempt = 1; attempt <= 2 && !stop; attempt++)
        {
            var started = DateTime.Now.AddSeconds(-2);
            if (Run(Usbipd, "attach --wsl --busid " + busId) == 0) return true;
            Thread.Sleep(1000);
            string why = WhyRefused(started);
            Say("");
            Say(why ?? "Windows did not say why it refused.");
            if (attempt == 2) break;
            Say("Check that Bluetooth is OFF in Windows, and close apps that use it (Phone Link, sound settings).");
            if (!Ask("Type y to try again, or anything else to stop [y/N] ")) return false;
        }
        Say("FAIL: attaching the adapter. Removing the device named above in Settings > Bluetooth & devices, or restarting, may help.");
        return false;
    }

    static bool Ask(string question)
    {
        lock (Out) Console.Write(question);
        string answer = Console.ReadLine();
        return !stop && answer != null && answer.Trim().ToLowerInvariant() == "y";
    }

    // usbipd records the real reason in the Windows event log, not on the screen.
    static string WhyRefused(DateTime since)
    {
        try
        {
            using (var log = new EventLog("Application"))
            {
                for (int i = log.Entries.Count - 1, seen = 0; i >= 0 && seen < 3000; i--, seen++)
                {
                    var e = log.Entries[i];
                    if (e.TimeGenerated < since) break;
                    if (e.Source != "usbipd-win" || e.Message.IndexOf("REMOVE_VETOED", StringComparison.Ordinal) < 0) continue;
                    var m = Regex.Match(e.Message, @"CR_REMOVE_VETOED: (\w+), (\S+)");
                    string id = m.Success ? m.Groups[2].Value : "";
                    return "Windows would not release the adapter: " + (DeviceName(id) ?? "a Bluetooth device")
                        + " is in use (" + (m.Success ? m.Groups[1].Value : "unknown reason") + ", " + e.TimeGenerated.ToString("HH:mm:ss") + ").";
                }
            }
        }
        catch (Exception) { }
        return null;
    }

    // The instance ID holds the device's address; Windows stores its name under that address.
    static string DeviceName(string instanceId)
    {
        var m = Regex.Match(instanceId, @"&([0-9A-Fa-f]{12})_C");
        if (!m.Success) return null;
        try
        {
            using (var k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                @"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices\" + m.Groups[1].Value.ToLowerInvariant()))
            {
                var bytes = k == null ? null : k.GetValue("Name") as byte[];
                return bytes == null ? null : "\"" + Encoding.UTF8.GetString(bytes).TrimEnd('\0') + "\"";
            }
        }
        catch (Exception) { return null; }
    }

    static string Wsl(string path)
    {
        return "/mnt/" + char.ToLowerInvariant(path[0]) + path.Substring(2).Replace('\\', '/');
    }

    static string DeviceLine()
    {
        var p = new Process();
        p.StartInfo = new ProcessStartInfo(Usbipd, "list") { UseShellExecute = false, RedirectStandardOutput = true, CreateNoWindow = true };
        p.Start();
        string all = p.StandardOutput.ReadToEnd();
        p.WaitForExit();
        return all.Split('\n').FirstOrDefault(l => Regex.IsMatch(l, @"^\s*" + Regex.Escape(busId) + @"\s"));
    }

    static int Run(string exe, string arguments)
    {
        using (var p = Process.Start(new ProcessStartInfo(exe, arguments) { UseShellExecute = false }))
        {
            p.WaitForExit();
            return p.ExitCode;
        }
    }

    // Windows shows its own admin prompt; nothing is changed if you decline.
    static bool Elevated(string arguments)
    {
        try
        {
            using (var p = Process.Start(new ProcessStartInfo(Usbipd, arguments) { UseShellExecute = true, Verb = "runas", WindowStyle = ProcessWindowStyle.Hidden }))
            {
                p.WaitForExit();
                return p.ExitCode == 0;
            }
        }
        catch (Win32Exception) { return false; }
    }

    static void Cleanup(bool closing)
    {
        lock (CleanupLock)
        {
            if (cleaned) return;
            cleaned = true;
            StopRelay(closing ? 1500 : 8000);
            if (attached) Run(Usbipd, "detach --busid " + busId);
            if (closing) return;
            if (prepared)
            {
                string script = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, @"in_wsl.sh"));
                Run("wsl.exe", "-u root -- bash \"" + Wsl(script) + "\" restore");
            }
            if (sharedByUs)
            {
                Say("Giving Bluetooth back to Windows (admin approval again)...");
                Say(Elevated("unbind --busid " + busId)
                    ? "Done. Turn Bluetooth back on in Windows. If it does not come back within a minute, restart the PC."
                    : "Not done. In an admin terminal run:  usbipd unbind --busid " + busId);
            }
            else if (attached) Say("The adapter was already shared before this started, so it still is. To give it back, in an admin terminal:  usbipd unbind --busid " + busId);
        }
    }

    // ---- Gamepad to relay, rumble back ----

    static volatile int rumbleStrong, rumbleWeak;
    static long rumbleEnd;     // Stopwatch milliseconds, guarded by RumbleLock
    static readonly object RumbleLock = new object();
    static readonly Stopwatch Clock = Stopwatch.StartNew();
    static bool rumbleDirty;

    static int Bridge(string exe, string arguments)
    {
        // Otherwise .NET writes a 3-byte UTF-8 marker into the pipe before the first frame.
        try { Console.InputEncoding = new UTF8Encoding(false); } catch (IOException) { }
        relay = new Process();
        relay.StartInfo = new ProcessStartInfo(exe, arguments)
        {
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            StandardOutputEncoding = Encoding.UTF8
        };
        relay.OutputDataReceived += (s, e) => { if (e.Data != null) OnRelayLine(e.Data); };
        relay.Start();
        relay.BeginOutputReadLine();
        var pipe = relay.StandardInput.BaseStream;

        int slot = -1;
        uint lastPacket = 0;
        bool haveLast = false;
        long nextSearch = 0;
        var frame = new byte[14];
        try
        {
            Send(pipe, frame, 'N', new Gamepad());
            while (!stop && !relay.HasExited)
            {
                long now = Clock.ElapsedMilliseconds;
                if (slot < 0 && now >= nextSearch)
                {
                    slot = FirstPad();
                    nextSearch = now + 1000;
                    haveLast = false;
                }
                if (slot >= 0)
                {
                    var st = new State();
                    if (XInputGetStateEx((uint)slot, ref st) != 0)
                    {
                        slot = -1;
                        nextSearch = now + 1000;
                        Send(pipe, frame, 'N', new Gamepad());
                    }
                    else if (!haveLast || st.Packet != lastPacket)
                    {
                        lastPacket = st.Packet;
                        haveLast = true;
                        Send(pipe, frame, 'S', st.Pad);
                    }
                }
                ApplyRumble(slot, now);
                Thread.Sleep(2);
            }
        }
        catch (IOException) { }     // the relay went away; its messages say why
        finally
        {
            if (slot >= 0) { var off = new Vibration(); XInputSetState((uint)slot, ref off); }
        }
        StopRelay(8000);
        return stop ? 0 : 1;
    }

    static void Send(Stream pipe, byte[] f, char kind, Gamepad g)
    {
        f[0] = 0xA5;
        f[1] = (byte)kind;
        f[2] = (byte)g.Buttons; f[3] = (byte)(g.Buttons >> 8);
        f[4] = g.LT; f[5] = g.RT;
        Put(f, 6, g.LX); Put(f, 8, g.LY); Put(f, 10, g.RX); Put(f, 12, g.RY);
        pipe.Write(f, 0, 14);
        pipe.Flush();
    }

    static void Put(byte[] f, int i, short v)
    {
        f[i] = (byte)v;
        f[i + 1] = (byte)((ushort)v >> 8);
    }

    static void OnRelayLine(string line)
    {
        var m = Regex.Match(line, @"^@rumble (\d+) (\d+) (\d+)$");
        if (!m.Success) { Say(line); return; }
        int ms = Math.Min(5000, int.Parse(m.Groups[3].Value));
        lock (RumbleLock)
        {
            rumbleStrong = ms == 0 ? 0 : Math.Min(100, int.Parse(m.Groups[1].Value));
            rumbleWeak = ms == 0 ? 0 : Math.Min(100, int.Parse(m.Groups[2].Value));
            rumbleEnd = Clock.ElapsedMilliseconds + ms;
            rumbleDirty = true;
        }
    }

    static void ApplyRumble(int slot, long now)
    {
        lock (RumbleLock)
        {
            if ((rumbleStrong > 0 || rumbleWeak > 0) && now >= rumbleEnd)
            {
                rumbleStrong = rumbleWeak = 0;
                rumbleDirty = true;
            }
            if (!rumbleDirty || slot < 0) return;
            var v = new Vibration { Strong = (ushort)(rumbleStrong * 65535 / 100), Weak = (ushort)(rumbleWeak * 65535 / 100) };
            XInputSetState((uint)slot, ref v);
            rumbleDirty = false;
        }
    }

    static void StopRelay(int wait)
    {
        var p = relay;
        if (p == null) return;
        try
        {
            if (!p.HasExited)
            {
                try { p.StandardInput.Close(); } catch (Exception) { }
                if (!p.WaitForExit(wait)) p.Kill();
            }
        }
        catch (Exception) { }
        relay = null;
    }

    // ---- Checks ----

    static int FirstPad()
    {
        for (uint i = 0; i < 4; i++)
        {
            var s = new State();
            if (XInputGetStateEx(i, ref s) == 0) return (int)i;
        }
        return -1;
    }

    static readonly KeyValuePair<int, string>[] Names =
    {
        new KeyValuePair<int, string>(0x1000, "A"), new KeyValuePair<int, string>(0x2000, "B"),
        new KeyValuePair<int, string>(0x4000, "X"), new KeyValuePair<int, string>(0x8000, "Y"),
        new KeyValuePair<int, string>(0x100, "LB"), new KeyValuePair<int, string>(0x200, "RB"),
        new KeyValuePair<int, string>(0x40, "LS"), new KeyValuePair<int, string>(0x80, "RS"),
        new KeyValuePair<int, string>(0x20, "View"), new KeyValuePair<int, string>(0x10, "Menu"),
        new KeyValuePair<int, string>(0x400, "Xbox"), new KeyValuePair<int, string>(1, "Up"),
        new KeyValuePair<int, string>(2, "Down"), new KeyValuePair<int, string>(4, "Left"), new KeyValuePair<int, string>(8, "Right")
    };

    static int Check()
    {
        Say("Move and press everything; Ctrl+C stops.");
        string last = "";
        while (!stop)
        {
            int slot = FirstPad();
            string line = "no gamepad";
            if (slot >= 0)
            {
                var s = new State();
                XInputGetStateEx((uint)slot, ref s);
                line = string.Format("L({0,6},{1,6}) R({2,6},{3,6}) LT {4,3} RT {5,3}  {6}", s.Pad.LX, s.Pad.LY, s.Pad.RX, s.Pad.RY,
                    s.Pad.LT, s.Pad.RT, string.Join(" ", Names.Where(n => (s.Pad.Buttons & n.Key) != 0).Select(n => n.Value)));
            }
            if (line != last) Say(line);
            last = line;
            Thread.Sleep(slot < 0 ? 500 : 20);
        }
        return 0;
    }

    static int TestRumble()
    {
        int slot = FirstPad();
        if (slot < 0) { Say("no gamepad"); return 1; }
        foreach (var step in new[] { new { Name = "STRONG (left) motor", S = 65535, W = 0 }, new { Name = "WEAK (right) motor", S = 0, W = 65535 }, new { Name = "BOTH", S = 65535, W = 65535 } })
        {
            if (stop) break;
            Say(step.Name + " for 1.5 seconds");
            var on = new Vibration { Strong = (ushort)step.S, Weak = (ushort)step.W };
            XInputSetState((uint)slot, ref on);
            for (int i = 0; i < 15 && !stop; i++) Thread.Sleep(100);
            var off = new Vibration();
            XInputSetState((uint)slot, ref off);
            for (int i = 0; i < 8 && !stop; i++) Thread.Sleep(100);
        }
        return 0;
    }
}
