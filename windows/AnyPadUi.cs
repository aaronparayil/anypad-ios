// The look of AnyPad: colors that follow Windows' light or dark setting, and three drawn controls.
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;

static class Theme
{
    public static bool Dark;
    public static Color Back, Card, Text, Dim, Line, Good, Bad, Wait, Accent, AccentHover, Link;
    public static readonly Color HeadTop = Color.FromArgb(79, 70, 229), HeadBottom = Color.FromArgb(14, 165, 233);

    [DllImport("dwmapi.dll")]
    static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);

    public static void Load()
    {
        object v = Microsoft.Win32.Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", 1);
        Dark = v is int && (int)v == 0 && !SystemInformation.HighContrast;
        Back = Dark ? Color.FromArgb(24, 24, 27) : Color.FromArgb(250, 250, 252);
        Card = Dark ? Color.FromArgb(38, 38, 43) : Color.White;
        Text = Dark ? Color.FromArgb(240, 240, 243) : Color.FromArgb(24, 24, 27);
        Dim = Dark ? Color.FromArgb(165, 165, 175) : Color.FromArgb(92, 92, 102);
        Line = Dark ? Color.FromArgb(63, 63, 70) : Color.FromArgb(222, 222, 230);
        Good = Dark ? Color.FromArgb(74, 222, 128) : Color.FromArgb(21, 128, 61);
        Bad = Dark ? Color.FromArgb(252, 129, 129) : Color.FromArgb(190, 30, 45);
        Wait = Dark ? Color.FromArgb(250, 204, 21) : Color.FromArgb(146, 94, 0);
        Accent = Color.FromArgb(79, 70, 229);
        AccentHover = Color.FromArgb(67, 56, 202);
        Link = Dark ? Color.FromArgb(147, 170, 255) : Color.FromArgb(67, 56, 202);
    }

    public static void TitleBar(Form form)
    {
        int on = Dark ? 1 : 0;
        try { DwmSetWindowAttribute(form.Handle, 20, ref on, 4); } catch (Exception) { }
    }

    public static GraphicsPath Round(RectangleF r, float radius)
    {
        var p = new GraphicsPath();
        float d = radius * 2;
        p.AddArc(r.X, r.Y, d, d, 180, 90);
        p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
        p.CloseFigure();
        return p;
    }
}

class Header : Control
{
    readonly Image logo;
    readonly Font title = new Font("Segoe UI Semibold", 19f), sub = new Font("Segoe UI", 10f);

    public Header(Image logo)
    {
        this.logo = logo;
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);
        SetStyle(ControlStyles.Selectable, false);
        AccessibleName = "AnyPad. Use any gamepad with your iPhone or iPad.";
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        float k = g.DpiX / 96f;
        using (var b = new LinearGradientBrush(new Rectangle(0, 0, Math.Max(1, Width), Math.Max(1, Height)), Theme.HeadTop, Theme.HeadBottom, 20f)) g.FillRectangle(b, ClientRectangle);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        using (var plate = Theme.Round(new RectangleF(20 * k, 18 * k, 60 * k, 60 * k), 15 * k))
        using (var w = new SolidBrush(Color.FromArgb(60, 255, 255, 255))) g.FillPath(w, plate);
        g.DrawImage(logo, 23 * k, 21 * k, 54 * k, 54 * k);
        TextRenderer.DrawText(g, "AnyPad", title, new Point((int)(90 * k), (int)(15 * k)), Color.White);
        TextRenderer.DrawText(g, "Any gamepad, on your iPhone or iPad", sub, new Point((int)(92 * k), (int)(52 * k)), Color.FromArgb(235, 243, 255));
    }
}

// Gamepad -- this PC -- iPhone or iPad, with the working parts lit.
class PathView : Control
{
    public bool Pad, Pc, Phone;
    readonly Font font = new Font("Segoe UI", 9f);

    public PathView()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);
        SetStyle(ControlStyles.Selectable, false);
    }

    public void Set(bool pad, bool pc, bool phone)
    {
        if (pad == Pad && pc == Pc && phone == Phone) return;
        Pad = pad;
        Pc = pc;
        Phone = phone;
        AccessibleName = "Gamepad " + (pad ? "connected" : "not connected") + ", this PC " + (pc ? "ready" : "not ready") + ", iPhone or iPad " + (phone ? "connected" : "not connected");
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        g.Clear(Theme.Back);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        float k = g.DpiX / 96f, r = 25 * k, cy = 30 * k;
        float[] cx = { Width * 0.17f, Width * 0.5f, Width * 0.83f };
        bool[] on = { Pad, Pc, Phone };
        string[] names = { "Gamepad", "This PC", "iPhone / iPad" };
        for (int i = 0; i < 2; i++)
            using (var pen = new Pen(on[i] && on[i + 1] ? Theme.Good : Theme.Line, 3 * k))
            {
                pen.StartCap = pen.EndCap = LineCap.Round;
                if (!(on[i] && on[i + 1])) pen.DashStyle = DashStyle.Dot;
                g.DrawLine(pen, cx[i] + r + 9 * k, cy, cx[i + 1] - r - 9 * k, cy);
            }
        for (int i = 0; i < 3; i++)
        {
            var box = new RectangleF(cx[i] - r, cy - r, 2 * r, 2 * r);
            using (var fill = new SolidBrush(Theme.Card)) g.FillEllipse(fill, box);
            using (var pen = new Pen(on[i] ? Theme.Good : Theme.Line, 2 * k)) g.DrawEllipse(pen, box);
            Draw(g, i, cx[i], cy, k, on[i] ? Theme.Good : Theme.Dim);
            TextRenderer.DrawText(g, names[i], font, new Rectangle((int)(cx[i] - 60 * k), (int)(cy + r + 4 * k), (int)(120 * k), (int)(20 * k)),
                on[i] ? Theme.Text : Theme.Dim, TextFormatFlags.HorizontalCenter);
        }
    }

    static void Draw(Graphics g, int what, float x, float y, float k, Color c)
    {
        using (var pen = new Pen(c, 2 * k))
        using (var fill = new SolidBrush(c))
        {
            pen.LineJoin = LineJoin.Round;
            if (what == 0)
            {
                using (var p = Theme.Round(new RectangleF(x - 14 * k, y - 8 * k, 28 * k, 17 * k), 8 * k)) g.DrawPath(pen, p);
                g.FillRectangle(fill, x - 10 * k, y - 1 * k, 7 * k, 2.2f * k);
                g.FillRectangle(fill, x - 7.6f * k, y - 3.4f * k, 2.2f * k, 7 * k);
                g.FillEllipse(fill, x + 3 * k, y - 0.5f * k, 3.4f * k, 3.4f * k);
                g.FillEllipse(fill, x + 7.5f * k, y - 3.4f * k, 3.4f * k, 3.4f * k);
            }
            else if (what == 1)
            {
                using (var p = Theme.Round(new RectangleF(x - 12 * k, y - 11 * k, 24 * k, 16 * k), 2.5f * k)) g.DrawPath(pen, p);
                g.DrawLine(pen, x - 16 * k, y + 9 * k, x + 16 * k, y + 9 * k);
            }
            else
            {
                using (var p = Theme.Round(new RectangleF(x - 8 * k, y - 13 * k, 16 * k, 26 * k), 3.5f * k)) g.DrawPath(pen, p);
                g.DrawLine(pen, x - 3 * k, y + 9 * k, x + 3 * k, y + 9 * k);
            }
        }
    }
}

class BigButton : Button
{
    bool hover, down;
    public bool Quiet;      // outlined, for Stop

    public BigButton()
    {
        SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint, true);
        Cursor = Cursors.Hand;
    }

    protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { hover = down = false; Invalidate(); base.OnMouseLeave(e); }
    protected override void OnMouseDown(MouseEventArgs e) { down = true; Invalidate(); base.OnMouseDown(e); }
    protected override void OnMouseUp(MouseEventArgs e) { down = false; Invalidate(); base.OnMouseUp(e); }

    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics;
        float k = g.DpiX / 96f;
        g.Clear(Theme.Back);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        var r = new RectangleF(1.5f * k, 1.5f * k, Width - 3 * k, Height - 3 * k);
        Color back = !Enabled ? Theme.Line : Quiet ? (hover ? Theme.Line : Theme.Card) : hover || down ? Theme.AccentHover : Theme.Accent;
        Color text = !Enabled ? Theme.Dim : Quiet ? Theme.Text : Color.White;
        using (var p = Theme.Round(r, 10 * k))
        {
            using (var b = new SolidBrush(back)) g.FillPath(b, p);
            if (Quiet && Enabled) using (var pen = new Pen(Theme.Dim, 1.2f * k)) g.DrawPath(pen, p);
        }
        if (Focused && ShowFocusCues)
            using (var p = Theme.Round(new RectangleF(r.X + 4 * k, r.Y + 4 * k, r.Width - 8 * k, r.Height - 8 * k), 7 * k))
            using (var pen = new Pen(text, 1.4f * k)) g.DrawPath(pen, p);
        TextRenderer.DrawText(g, Text, Font, ClientRectangle, text, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
    }
}

// Learns a DirectInput pad's buttons, one at a time.
class SetupForm : Form
{
    readonly Label big = new Label(), small = new Label();
    readonly BigButton skip = new BigButton(), cancel = new BigButton();
    readonly Timer timer = new Timer();
    readonly RawPad raw = new RawPad();
    readonly int device;
    readonly string id;
    PadLearner learner;
    int quiet;

    public SetupForm(int device, string id, float k)
    {
        this.device = device;
        this.id = id;
        Text = "Set up this gamepad";
        Font = new Font("Segoe UI", 9.5f);
        BackColor = Theme.Back;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = MinimizeBox = ShowInTaskbar = false;
        StartPosition = FormStartPosition.CenterParent;
        AutoScaleMode = AutoScaleMode.None;
        ClientSize = new Size((int)(400 * k), (int)(190 * k));
        big.SetBounds((int)(20 * k), (int)(24 * k), (int)(360 * k), (int)(58 * k));
        big.Font = new Font("Segoe UI Semibold", 14f);
        big.ForeColor = Theme.Text;
        big.TextAlign = ContentAlignment.MiddleCenter;
        small.SetBounds((int)(20 * k), (int)(86 * k), (int)(360 * k), (int)(24 * k));
        small.ForeColor = Theme.Dim;
        small.TextAlign = ContentAlignment.MiddleCenter;
        skip.Text = "I don't have this one";
        skip.Quiet = cancel.Quiet = true;
        skip.SetBounds((int)(20 * k), (int)(128 * k), (int)(220 * k), (int)(42 * k));
        cancel.Text = "Cancel";
        cancel.SetBounds((int)(250 * k), (int)(128 * k), (int)(130 * k), (int)(42 * k));
        skip.Click += (s, e) => { if (learner != null) { learner.Skip(); Step(); } };
        cancel.Click += (s, e) => Close();
        Controls.AddRange(new Control[] { big, small, skip, cancel });
        big.Text = "Leave the gamepad alone for a moment";
        timer.Interval = 20;
        timer.Tick += Tick;
        Shown += (s, e) => { Theme.TitleBar(this); timer.Start(); };
        FormClosed += (s, e) => timer.Dispose();
    }

    void Tick(object sender, EventArgs e)
    {
        if (!Joy.Read(device, raw)) { timer.Stop(); big.Text = "The gamepad was unplugged"; return; }
        if (learner == null)
        {
            if (++quiet < 50) return;
            learner = new PadLearner(raw);
            Step();
        }
        else if (learner.Feed(raw)) Step();
    }

    void Step()
    {
        if (!learner.Finished)
        {
            big.Text = learner.Prompt;
            small.Text = (learner.Step + 1) + " of " + PadLearner.Steps.GetLength(0);
            return;
        }
        timer.Stop();
        try { learner.Map.Save(id); DialogResult = DialogResult.OK; }
        catch (Exception x) { MessageBox.Show(this, "Could not save it: " + x.Message, "AnyPad"); }
        Close();
    }
}
