// Checks the DirectInput mapping and the setup wizard without a gamepad.
using System;

static class PadsTest
{
    static bool ok = true;

    static void Chk(string name, bool good)
    {
        ok &= good;
        Console.WriteLine((good ? "PASS " : "FAIL ") + name);
    }

    static RawPad Raw(uint buttons = 0, int pov = -1, int axis = -1, int value = 32768)
    {
        var r = new RawPad { Buttons = buttons, Pov = pov };
        if (axis >= 0) r.Axes[axis] = value;
        return r;
    }

    static int Main()
    {
        var d = PadMap.Default();
        Chk("rest is neutral", d.Apply(Raw()).Same(new Gamepad()));
        Chk("slightly off centre is still neutral", d.Apply(Raw(0, -1, 0, 32767)).Same(new Gamepad()));
        int[] order = { 0x4000, 0x1000, 0x2000, 0x8000, 0x100, 0x200, -1, -1, 0x20, 0x10, 0x40, 0x80, 0x400 };
        for (int i = 0; i < order.Length; i++)
            if (order[i] > 0) Chk("button " + (i + 1), d.Apply(Raw(1u << i)).Buttons == order[i]);
        Chk("triggers as buttons", d.Apply(Raw(1u << 6)).LT == 255 && d.Apply(Raw(1u << 7)).RT == 255);
        Chk("left stick right", d.Apply(Raw(0, -1, 0, 65535)).LX == 32767);
        Chk("left stick up", d.Apply(Raw(0, -1, 1, 0)).LY == 32767);
        Chk("left stick down", d.Apply(Raw(0, -1, 1, 65535)).LY <= -32766);
        Chk("right stick", d.Apply(Raw(0, -1, 2, 0)).RX == -32768 && d.Apply(Raw(0, -1, 3, 0)).RY == 32767);
        int[] hats = { 1, 9, 8, 10, 2, 6, 4, 5 };
        for (int i = 0; i < 8; i++) Chk("hat " + i * 45, d.Apply(Raw(0, i * 4500)).Buttons == hats[i]);
        Chk("hat just below 360", d.Apply(Raw(0, 35900)).Buttons == 1);

        Chk("map survives saving", PadMap.Parse(d.ToString()).ToString() == d.ToString());
        Chk("bad entries are ignored", PadMap.Parse("A=b99 B=q C X=b0 Y=xx LB=--x RB=b3").ToString() == "RB=b3");

        // A pad unlike the default: odd button order, analog triggers, inverted right stick, d-pad as buttons.
        var rest = new RawPad();
        rest.Axes[4] = 0;       // trigger resting at the bottom of its axis
        rest.Axes[5] = 65535;   // and one resting at the top
        var l = new PadLearner(rest);
        Func<uint, RawPad> press = b => { var r = Raw(b); r.Axes[4] = 0; r.Axes[5] = 65535; return r; };
        Func<int, int, RawPad> move = (a, v) => { var r = press(0); r.Axes[a] = v; return r; };
        Action<RawPad> step = r => { l.Feed(r); l.Feed(r); l.Feed(press(0)); };
        uint[] first = { 1u << 8, 1u << 3, 1u << 1, 1u << 0, 1u << 20, 1u << 21 };
        foreach (var b in first) step(press(b));
        step(move(4, 65535));
        step(move(5, 0));
        l.Feed(move(0, 40000));     // a nudge too small to count
        Chk("small movement is not learned", l.Prompt.Contains("View"));
        l.Feed(press(3));           // two buttons at once
        Chk("two buttons at once are not learned", l.Prompt.Contains("View"));
        l.Feed(press(0));
        step(press(1u << 4));
        step(press(1u << 5));
        l.Skip(); l.Feed(press(0));
        l.Skip(); l.Feed(press(0));
        step(move(0, 65535));
        step(move(1, 65535));
        step(move(2, 0));
        step(move(3, 0));
        foreach (var b in new[] { 1u << 10, 1u << 11, 1u << 12, 1u << 13 }) step(press(b));
        l.Skip();
        Chk("wizard finishes", l.Finished);
        Chk("learned map", l.Map.ToString() == "A=b9 B=b4 X=b2 Y=b1 LB=b21 RB=b22 LT=u RT=-v View=b5 Menu=b6 LX=x LY=y RX=-z RY=-r Up=b11 Down=b12 Left=b13 Right=b14");
        Chk("learned pad at rest", l.Map.Apply(press(0)).Same(new Gamepad()));
        Chk("learned A", l.Map.Apply(press(1u << 8)).Buttons == 0x1000);
        Chk("learned triggers", l.Map.Apply(move(4, 65535)).LT == 255 && l.Map.Apply(move(5, 0)).RT == 255 && l.Map.Apply(move(4, 32768)).LT == 128);
        Chk("learned inverted stick", l.Map.Apply(move(2, 0)).RX == 32767 && l.Map.Apply(move(3, 0)).RY <= -32766);
        Chk("learned d-pad", l.Map.Apply(press(1u << 12)).Buttons == 4);

        var h = new PadLearner(new RawPad());
        while (!h.Prompt.Contains("up on the D-pad")) { h.Skip(); h.Feed(Raw()); }
        h.Feed(Raw(0, 0));
        Chk("a hat fills all four directions", h.Map.ToString() == "Pad=pov" && h.Prompt.Contains("Home"));

        Console.WriteLine(ok ? "ALL PASS" : "SOME FAILED");
        return ok ? 0 : 1;
    }
}
