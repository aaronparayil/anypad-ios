// Reading gamepads: XInput pads directly, every other pad (DirectInput) through Windows'
// joystick interface with a button map, which the setup wizard can learn.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;

[StructLayout(LayoutKind.Sequential)]
struct Gamepad
{
    public ushort Buttons;
    public byte LT, RT;
    public short LX, LY, RX, RY;

    public bool Same(Gamepad o)
    {
        return Buttons == o.Buttons && LT == o.LT && RT == o.RT && LX == o.LX && LY == o.LY && RX == o.RX && RY == o.RY;
    }
}

// What a DirectInput pad reports, before mapping. Axes are X Y Z R U V, each 0..65535.
class RawPad
{
    public uint Buttons;
    public int[] Axes = { 32768, 32768, 32768, 32768, 32768, 32768 };
    public int Pov = -1;        // hundredths of a degree, or -1
}

static class Joy
{
    [StructLayout(LayoutKind.Sequential)]
    struct Info { public uint Size, Flags, X, Y, Z, R, U, V, Buttons, Number, Pov, Reserved1, Reserved2; }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct Caps
    {
        public ushort Mid, Pid;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string Name;
        public uint XMin, XMax, YMin, YMax, ZMin, ZMax, NumButtons, PeriodMin, PeriodMax, RMin, RMax, UMin, UMax, VMin, VMax, Flags, MaxAxes, NumAxes, MaxButtons;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string RegKey;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string Oem;
    }

    [DllImport("winmm.dll")] static extern uint joyGetNumDevs();
    [DllImport("winmm.dll")] static extern uint joyGetPosEx(uint id, ref Info info);
    [DllImport("winmm.dll", CharSet = CharSet.Unicode, EntryPoint = "joyGetDevCapsW")]
    static extern uint joyGetDevCaps(UIntPtr id, ref Caps caps, uint size);

    static Caps caps;

    // The first pad there is, or -1. Looking through all slots is slow, so call it rarely.
    public static int Find(out string id)
    {
        id = null;
        uint n = Math.Min(16, joyGetNumDevs());
        for (uint i = 0; i < n; i++)
        {
            var info = NewInfo();
            if (joyGetPosEx(i, ref info) != 0) continue;
            caps = new Caps();
            if (joyGetDevCaps((UIntPtr)i, ref caps, (uint)Marshal.SizeOf(caps)) != 0 || caps.NumButtons < 4 || caps.NumAxes < 2) continue;
            id = caps.Mid.ToString("x4") + ":" + caps.Pid.ToString("x4");
            return (int)i;
        }
        return -1;
    }

    public static bool Read(int device, RawPad into)
    {
        var info = NewInfo();
        if (joyGetPosEx((uint)device, ref info) != 0) return false;
        into.Buttons = info.Buttons;
        // Axes the pad does not have rest at the centre.
        into.Axes[0] = Scale(info.X, caps.XMin, caps.XMax, true);
        into.Axes[1] = Scale(info.Y, caps.YMin, caps.YMax, true);
        into.Axes[2] = Scale(info.Z, caps.ZMin, caps.ZMax, (caps.Flags & 1) != 0);
        into.Axes[3] = Scale(info.R, caps.RMin, caps.RMax, (caps.Flags & 2) != 0);
        into.Axes[4] = Scale(info.U, caps.UMin, caps.UMax, (caps.Flags & 4) != 0);
        into.Axes[5] = Scale(info.V, caps.VMin, caps.VMax, (caps.Flags & 8) != 0);
        into.Pov = info.Pov >= 36000 ? -1 : (int)info.Pov;
        return true;
    }

    static Info NewInfo()
    {
        return new Info { Size = (uint)Marshal.SizeOf(typeof(Info)), Flags = 0xFF };
    }

    static int Scale(uint v, uint min, uint max, bool present)
    {
        if (!present || max <= min) return 32768;
        v = Math.Min(Math.Max(v, min), max);
        return (int)((long)(v - min) * 65535 / (max - min));
    }
}

// Where each Xbox control comes from: "b3" button, "x" or "-x" axis, "+x" upper half, "~x" lower half, "pov".
class PadMap
{
    public static readonly string[] Buttons = { "A", "B", "X", "Y", "LB", "RB", "View", "Menu", "LS", "RS", "Xbox" };
    static readonly int[] Bits = { 0x1000, 0x2000, 0x4000, 0x8000, 0x100, 0x200, 0x20, 0x10, 0x40, 0x80, 0x400 };
    const string AxisNames = "xyzruv";
    public readonly Dictionary<string, string> From = new Dictionary<string, string>();

    // The order most DirectInput pads use: X A B Y LB RB LT RT View Menu LS RS.
    public static PadMap Default()
    {
        return Parse("X=b1 A=b2 B=b3 Y=b4 LB=b5 RB=b6 LT=b7 RT=b8 View=b9 Menu=b10 LS=b11 RS=b12 Xbox=b13 LX=x LY=y RX=z RY=r Pad=pov");
    }

    public static PadMap Parse(string text)
    {
        var m = new PadMap();
        foreach (var part in text.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries))
        {
            int cut = part.IndexOf('=');
            if (cut > 0 && Valid(part.Substring(cut + 1))) m.From[part.Substring(0, cut)] = part.Substring(cut + 1);
        }
        return m;
    }

    static bool Valid(string source)
    {
        int n;
        if (source == "pov") return true;
        if (source.StartsWith("b")) return int.TryParse(source.Substring(1), NumberStyles.None, CultureInfo.InvariantCulture, out n) && n >= 1 && n <= 32;
        string axis = source.TrimStart('-', '+', '~');
        return axis.Length == 1 && AxisNames.IndexOf(axis[0]) >= 0 && source.Length <= 2;
    }

    public override string ToString()
    {
        return string.Join(" ", From.Select(p => p.Key + "=" + p.Value));
    }

    public Gamepad Apply(RawPad r)
    {
        var g = new Gamepad();
        for (int i = 0; i < Buttons.Length; i++)
            if (Level(r, Buttons[i], 0) > 0.5) g.Buttons |= (ushort)Bits[i];
        g.LT = (byte)Math.Round(255 * Level(r, "LT", 0));
        g.RT = (byte)Math.Round(255 * Level(r, "RT", 0));
        g.LX = Stick(r, "LX", false);
        g.LY = Stick(r, "LY", true);       // DirectInput's down is positive, XInput's up is
        g.RX = Stick(r, "RX", false);
        g.RY = Stick(r, "RY", true);
        string pad;
        if (From.TryGetValue("Pad", out pad) && pad == "pov" && r.Pov >= 0)
        {
            int eighth = ((r.Pov + 2250) / 4500) % 8;
            if (eighth == 7 || eighth <= 1) g.Buttons |= 1;
            if (eighth >= 3 && eighth <= 5) g.Buttons |= 2;
            if (eighth >= 5 && eighth <= 7) g.Buttons |= 4;
            if (eighth >= 1 && eighth <= 3) g.Buttons |= 8;
        }
        if (Level(r, "Up", 0) > 0.5) g.Buttons |= 1;
        if (Level(r, "Down", 0) > 0.5) g.Buttons |= 2;
        if (Level(r, "Left", 0) > 0.5) g.Buttons |= 4;
        if (Level(r, "Right", 0) > 0.5) g.Buttons |= 8;
        return g;
    }

    // 0..1 for a button, a trigger or half an axis.
    double Level(RawPad r, string name, double rest)
    {
        string f;
        if (!From.TryGetValue(name, out f)) return rest;
        if (f[0] == 'b') return (r.Buttons >> (int.Parse(f.Substring(1), CultureInfo.InvariantCulture) - 1) & 1) != 0 ? 1 : 0;
        if (f == "pov") return 0;
        int v = r.Axes[AxisNames.IndexOf(f[f.Length - 1])];
        if (f[0] == '+') return Math.Max(0, v - 32768) / 32767.0;
        if (f[0] == '~') return Math.Max(0, 32768 - v) / 32768.0;
        return f[0] == '-' ? 1 - v / 65535.0 : v / 65535.0;
    }

    short Stick(RawPad r, string name, bool flip)
    {
        string f;
        if (!From.TryGetValue(name, out f) || f[0] == 'b' || f == "pov") return 0;
        int v = r.Axes[AxisNames.IndexOf(f[f.Length - 1])] - 32768;
        if (Math.Abs(v) < 400) v = 0;       // the joystick interface rests a little off centre
        if (f[0] == '-') v = -v;
        if (flip) v = -v;
        return (short)Math.Max(-32768, Math.Min(32767, v));
    }

    // ---- Saved maps, one line per pad: "046d:c216 A=b2 B=b3 ..." ----

    static string FilePath()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "anypad-ios", "pads.txt");
    }

    public static PadMap Load(string id, out bool saved)
    {
        saved = false;
        try
        {
            foreach (var line in File.ReadAllLines(FilePath()))
                if (line.StartsWith(id + " ")) { saved = true; return Parse(line.Substring(id.Length)); }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        return Default();
    }

    public void Save(string id)
    {
        string path = FilePath();
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        var lines = File.Exists(path) ? File.ReadAllLines(path).Where(l => !l.StartsWith(id + " ")).ToList() : new List<string>();
        lines.Add(id + " " + this);
        File.WriteAllLines(path, lines);
    }
}

// The setup wizard's logic, without its window: feed it readings, it says what was moved.
class PadLearner
{
    public static readonly string[,] Steps =
    {
        { "A", "Press A (the bottom button)" }, { "B", "Press B (the right button)" }, { "X", "Press X (the left button)" }, { "Y", "Press Y (the top button)" },
        { "LB", "Press the left shoulder button (LB)" }, { "RB", "Press the right shoulder button (RB)" },
        { "LT", "Pull the left trigger (LT) all the way" }, { "RT", "Pull the right trigger (RT) all the way" },
        { "View", "Press View / Select / Back" }, { "Menu", "Press Menu / Start" },
        { "LS", "Click the left stick in" }, { "RS", "Click the right stick in" },
        { "LX", "Push the left stick all the way right" }, { "LY", "Push the left stick all the way down" },
        { "RX", "Push the right stick all the way right" }, { "RY", "Push the right stick all the way down" },
        { "Up", "Press up on the D-pad" }, { "Down", "Press down on the D-pad" }, { "Left", "Press left on the D-pad" }, { "Right", "Press right on the D-pad" },
        { "Xbox", "Press the Home / Xbox button, or skip" }
    };

    readonly int[] rest;
    readonly uint restButtons;
    public readonly PadMap Map = new PadMap();
    public int Step;
    bool waitRelease;

    public PadLearner(RawPad atRest)
    {
        rest = (int[])atRest.Axes.Clone();
        restButtons = atRest.Buttons;
    }

    public bool Finished { get { return Step >= Steps.GetLength(0); } }
    public string Prompt { get { return Finished ? "" : Steps[Step, 1]; } }

    public void Skip()
    {
        Next();
        waitRelease = true;
    }

    // Returns true when a step was learned.
    public bool Feed(RawPad r)
    {
        if (Finished) return false;
        uint pressed = r.Buttons & ~restButtons;
        int axis = -1, most = 0;
        for (int i = 0; i < 6; i++)
        {
            int d = Math.Abs(r.Axes[i] - rest[i]);
            if (d > most) { most = d; axis = i; }
        }
        bool moved = most > 20000, still = pressed == 0 && most < 8000 && r.Pov < 0;
        if (waitRelease) { if (still) waitRelease = false; return false; }

        string name = Steps[Step, 0], source = null;
        bool stick = name == "LX" || name == "LY" || name == "RX" || name == "RY";
        bool dpad = name == "Up" || name == "Down" || name == "Left" || name == "Right";
        if (stick)
        {
            if (moved) source = (r.Axes[axis] < rest[axis] ? "-" : "") + "xyzruv"[axis];
        }
        else if (dpad && r.Pov >= 0)
        {
            // A hat gives all four directions at once.
            Map.From["Pad"] = "pov";
            while (!Finished && (Steps[Step, 0] == "Up" || Steps[Step, 0] == "Down" || Steps[Step, 0] == "Left" || Steps[Step, 0] == "Right")) Next();
            waitRelease = true;
            return true;
        }
        else if (pressed != 0 && (pressed & (pressed - 1)) == 0)
        {
            int n = 1;
            while ((pressed >> (n - 1) & 1) == 0) n++;
            source = "b" + n;
        }
        else if (pressed == 0 && moved)
        {
            char a = "xyzruv"[axis];
            bool up = r.Axes[axis] > rest[axis];
            // A trigger resting at one end uses the whole axis, one resting in the middle half of it.
            bool end = rest[axis] < 12000 || rest[axis] > 53000;
            source = end ? (up ? "" : "-") + a : (up ? "+" : "~") + a;
        }
        if (source == null) return false;
        Map.From[name] = source;
        Next();
        waitRelease = true;
        return true;
    }

    void Next()
    {
        if (!Finished) Step++;
    }
}
