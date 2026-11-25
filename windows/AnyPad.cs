// AnyPad.exe: the window for normal use. One file; the WSL scripts are inside it.
// With arguments it is the same program as controller.exe (that is how it starts itself).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("AnyPad")]
[assembly: AssemblyProduct("anypad-ios")]
[assembly: AssemblyVersion("0.1.0.0")]
[assembly: AssemblyFileVersion("0.1.0.0")]

static class Gui
{
    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length > 0) return Program.Main(args);
        bool first;
        using (var single = new Mutex(true, "Local\\anypad-windows-gui", out first))
        {
            if (!first)
            {
                MessageBox.Show("AnyPad is already open.", "AnyPad");
                return 3;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Theme.Load();
            Application.Run(new MainForm());
        }
        return 0;
    }
}

class Check
{
    public bool Shown;
    public Label Mark, Text;
    public LinkLabel Fix;
}

class MainForm : Form
{
    readonly Header header;
    readonly PathView path = new PathView();
    readonly Label status = new Label(), hint = new Label();
    readonly BigButton main = new BigButton();
    readonly TextBox log = new TextBox();
    readonly LinkLabel details = new LinkLabel(), forget = new LinkLabel(), rumble = new LinkLabel(), setup = new LinkLabel();
    readonly Dictionary<string, Check> checks = new Dictionary<string, Check>();
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    readonly string files = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "anypad-ios", "app");

    Process engine;
    bool looking, lookAgain, stopping, closeAfter, played, busy, filesOk, phoneOn, pcOn, padOn;
    int rows = -1;
    DateTime lastLook;
    int packages = -1;      // -1 not checked yet, 0 missing, 1 ready, 2 no WSL
    string problem;

    public MainForm()
    {
        Text = "AnyPad";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Font = new Font("Segoe UI", 9.5f);
        BackColor = Theme.Back;
        // All sizes below are for 100 % scaling; Place() enlarges them on sharper screens.
        AutoScaleMode = AutoScaleMode.None;
        using (var g = CreateGraphics()) scale = g.DpiX / 96f;
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;

        header = new Header(Logo());
        Place(header, 0, 0, 440, 96);
        Place(path, 10, 112, 420, 84);
        Place(status, 16, 202, 408, 34);
        status.Font = new Font("Segoe UI Semibold", 15f);
        status.TextAlign = ContentAlignment.MiddleCenter;
        Place(hint, 24, 236, 392, 42);
        hint.TextAlign = ContentAlignment.TopCenter;
        hint.ForeColor = Theme.Dim;
        Controls.AddRange(new Control[] { header, path, status, hint });

        foreach (var name in new[] { "usbipd", "wsl", "adapter", "bluetooth", "phones", "pad" }) AddCheck(name);

        main.Font = new Font("Segoe UI Semibold", 12f);
        main.Click += (s, e) => { if (engine == null) Start(); else StopEngine(); };
        Controls.Add(main);
        AcceptButton = main;

        Link(details, "Details", () => ToggleLog());
        Link(setup, "Gamepad buttons", () => SetUpPad());
        Link(rumble, "Test rumble", () => TestRumble());
        Link(forget, "Forget phones", () => Forget());

        log.Multiline = true;
        log.ReadOnly = true;
        log.ScrollBars = ScrollBars.Vertical;
        log.BorderStyle = BorderStyle.FixedSingle;
        log.BackColor = Theme.Card;
        log.ForeColor = Theme.Text;
        log.Font = new Font("Consolas", 8.5f);
        log.Visible = false;
        log.AccessibleName = "Details";
        Controls.Add(log);

        // Device changes and coming back to the window trigger a look; the timer is only a fallback.
        timer.Interval = 20000;
        timer.Tick += (s, e) => { if (engine == null && WindowState != FormWindowState.Minimized) Look(); };
        Activated += (s, e) => { if (engine == null && (DateTime.Now - lastLook).TotalSeconds > 2) Look(); };
        Shown += (s, e) => { Theme.TitleBar(this); Unpack(); Look(); CheckPackages(); timer.Start(); };
        FormClosing += OnClosing;
        setup.Visible = rumble.Visible = forget.Visible = false;
        Show("Checking your PC...", Theme.Dim, "");
        Arrange(0);
        Refresh(null);
    }

    static Image Logo()
    {
        using (var st = Assembly.GetExecutingAssembly().GetManifestResourceStream("logo.png"))
        using (var img = Image.FromStream(st)) return new Bitmap(img);
    }

    const int WM_DEVICECHANGE = 0x219;
    readonly System.Windows.Forms.Timer settle = new System.Windows.Forms.Timer { Interval = 900 };

    protected override void WndProc(ref Message m)
    {
        if (m.Msg == WM_DEVICECHANGE && engine == null && IsHandleCreated)
        {
            settle.Stop();
            settle.Tick -= OnSettled;
            settle.Tick += OnSettled;
            settle.Start();
        }
        base.WndProc(ref m);
    }

    void OnSettled(object sender, EventArgs e)
    {
        settle.Stop();
        Look();
    }

    // Only what needs attention takes up room.
    void Arrange(int count)
    {
        if (count == rows) return;
        rows = count;
        int y = 282, n = 0;
        foreach (var name in checks.Keys)
        {
            var c = checks[name];
            c.Mark.Visible = c.Text.Visible = c.Shown;
            if (!c.Shown) { c.Fix.Visible = false; continue; }
            Place(c.Mark, 26, y, 24, 26);
            Place(c.Text, 50, y + 3, 270, 24);
            Place(c.Fix, 322, y + 3, 92, 24);
            y += 30;
            n++;
        }
        y += n > 0 ? 6 : 0;
        Place(main, 22, y, 396, 48);
        Place(details, 22, y + 60, 110, 22);
        Place(setup, 150, y + 60, 140, 22);
        Place(rumble, 150, y + 60, 140, 22);
        Place(forget, 308, y + 60, 110, 22);
        Place(log, 22, y + 90, 396, 160);
        Fit();
    }

    void Fit()
    {
        ClientSize = new Size(Px(440), (log.Visible ? log.Bottom : details.Bottom) + Px(12));
    }

    float scale = 1f;

    int Px(int size)
    {
        return (int)Math.Round(size * scale);
    }

    void Place(Control c, int x, int y, int w, int h)
    {
        c.SetBounds(Px(x), Px(y), Px(w), Px(h));
    }

    void AddCheck(string name)
    {
        var c = new Check { Mark = new Label(), Text = new Label(), Fix = new LinkLabel() };
        c.Mark.Font = new Font("Segoe UI", 11f, FontStyle.Bold);
        c.Text.AutoEllipsis = true;
        c.Text.ForeColor = Theme.Text;
        c.Fix.LinkColor = c.Fix.ActiveLinkColor = Theme.Link;
        c.Fix.TextAlign = ContentAlignment.TopRight;
        c.Fix.Visible = c.Mark.Visible = c.Text.Visible = false;
        c.Fix.LinkClicked += (s, e) => Fix(name);
        Controls.AddRange(new Control[] { c.Mark, c.Text, c.Fix });
        checks[name] = c;
    }

    void Link(LinkLabel l, string text, Action click)
    {
        l.Text = text;
        l.LinkColor = l.ActiveLinkColor = Theme.Link;
        l.DisabledLinkColor = Theme.Dim;
        l.LinkBehavior = LinkBehavior.HoverUnderline;
        l.TextAlign = ContentAlignment.TopCenter;
        l.LinkClicked += (s, e) => click();
        Controls.Add(l);
    }

    void Show(string text, Color color, string more)
    {
        status.Text = text;
        status.ForeColor = color;
        hint.Text = more;
    }

    void Set(string name, bool? ok, string text, string fix)
    {
        var c = checks[name];
        c.Shown = ok != true && engine == null;
        c.Mark.Text = ok == null ? "\u2022" : ok.Value ? "\u2713" : "\u2717";
        c.Mark.ForeColor = ok == null ? Theme.Dim : ok.Value ? Theme.Good : Theme.Bad;
        c.Text.Text = text;
        c.Fix.Text = fix ?? "";
        c.Fix.Visible = c.Shown && fix != null && !busy;
    }

    // ---- The scripts inside this exe ----

    void Unpack()
    {
        try
        {
            Directory.CreateDirectory(files);
            foreach (var name in new[] { "in_wsl.sh", "relay.py", "pairing_test.py" })
                using (var from = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
                using (var to = File.Create(Path.Combine(files, name)))
                    from.CopyTo(to);
            filesOk = true;
        }
        catch (Exception e)
        {
            Append("Could not write the program's files: " + e.Message);
        }
    }

    // ---- Checks ----

    void Look()
    {
        if (looking) { lookAgain = true; return; }
        looking = true;
        lastLook = DateTime.Now;
        Task.Run(() =>
        {
            Program.Checks c = null;
            try { c = Program.Look(); } catch (Exception e) { Post(() => Append("Check failed: " + e.Message)); }
            Post(() =>
            {
                looking = false;
                if (c != null) Refresh(c);
                if (lookAgain) { lookAgain = false; Look(); }
            });
        });
    }

    void CheckPackages()
    {
        if (!filesOk) return;
        Task.Run(() =>
        {
            int result = 2;
            try
            {
                bool ok = false;
                int code = Program.RunCaptured("wsl.exe", "-u root -- bash \"" + Program.ToWsl(Path.Combine(files, "in_wsl.sh")) + "\" check",
                    l => { if (l.Contains("anypad-packages-ok")) ok = true; });
                // The script ran if bash was there, whatever it found.
                int bash = Program.RunCaptured("wsl.exe", "-u root -- bash -c \"exit 7\"", l => { });
                result = ok ? 1 : bash == 7 ? 0 : 2;
            }
            catch (Exception) { }
            Post(() => { packages = result; Look(); });
        });
    }

    void Refresh(Program.Checks c)
    {
        main.Quiet = engine != null;
        if (c == null || engine != null)
        {
            if (engine != null) foreach (var k in checks.Values) k.Shown = false;
            main.Enabled = engine != null && !stopping;
            main.Text = engine == null ? "Start" : stopping ? "Stopping..." : "Stop";
            main.Invalidate();
            Arrange(checks.Values.Count(k => k.Shown));
            path.Set(padOn, pcOn, phoneOn);
            return;
        }
        padOn = c.Pad > 0;
        Set("pad", padOn && c.Pad != 3 ? true : padOn ? (bool?)null : false,
            padOn ? "Gamepad buttons mixed up?" : "No gamepad: plug it in and turn it on", c.Pad == 3 ? "Set up" : null);
        Set("usbipd", c.Usbipd, "usbipd-win is not installed", "Get it");
        Set("wsl", packages == -1 ? (bool?)null : packages == 1,
            packages == -1 ? "Checking WSL..." : packages == 0 ? "WSL needs 3 packages" : "WSL with Ubuntu is not set up",
            packages == 0 ? "Install" : packages == 2 ? "How to" : null);
        Set("adapter", c.Adapters == 1, c.Adapters > 1 ? "More than one Intel Bluetooth adapter" : c.Usbipd ? "No supported (Intel) Bluetooth adapter" : "Bluetooth adapter not checked yet", null);
        bool off = c.Radio == "Off" || c.Attached;
        Set("bluetooth", off, c.Radio == null ? "Windows shows no Bluetooth: restart the PC" : "Turn Bluetooth off in Windows", c.Radio == null ? null : "Settings");
        Set("phones", c.Phones.Count == 0, "Remove from Windows: " + string.Join(", ", c.Phones), "Settings");

        bool ready = filesOk && c.Usbipd && packages == 1 && c.Adapters == 1 && off && c.Phones.Count == 0;
        pcOn = ready;
        phoneOn = false;
        path.Set(padOn, pcOn, phoneOn);
        main.Text = "Start";
        main.Enabled = ready && !busy;
        main.Invalidate();
        setup.Visible = c.Pad >= 2;
        rumble.Visible = c.Pad == 1;
        forget.Visible = true;
        // The same number of different rows still needs a new layout.
        rows = -1;
        Arrange(checks.Values.Count(k => k.Shown));
        if (busy) return;
        if (problem != null) Show("It stopped", Theme.Bad, problem);
        else if (ready) Show("Ready to start", Theme.Good, c.Attached ? "Start releases the adapter from the earlier run first; then press Start again."
            : c.Audio.Count > 0 ? "Switch off your Bluetooth headphones first; they can block the adapter." : "Windows has no Bluetooth while AnyPad runs.");
        else Show("Almost there", Theme.Wait, "Sort out the items marked \u2717 below.");
    }

    void Fix(string name)
    {
        if (name == "usbipd") Open("https://github.com/dorssel/usbipd-win/releases/latest");
        else if (name == "bluetooth" || name == "phones") Open("ms-settings:bluetooth");
        else if (name == "wsl" && packages == 2) Open("https://learn.microsoft.com/windows/wsl/install");
        else if (name == "wsl") InstallPackages();
        else if (name == "pad") SetUpPad();
    }

    void InstallPackages()
    {
        if (MessageBox.Show(this, "This installs bluez, python3-dbus and python3-gi in your default WSL distro, from Ubuntu's own servers.\n\nContinue?",
            "AnyPad", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        busy = true;
        Show("Installing...", Theme.Wait, "This can take a few minutes.");
        checks["wsl"].Fix.Visible = false;
        Task.Run(() =>
        {
            int code = -1;
            try { code = Program.RunCaptured("wsl.exe", "-u root -- bash \"" + Program.ToWsl(Path.Combine(files, "in_wsl.sh")) + "\" install", l => Post(() => Append(l))); }
            catch (Exception e) { Post(() => Append(e.Message)); }
            Post(() => { busy = false; if (code != 0) { problem = "The packages could not be installed. See the details."; ShowLog(); } packages = -1; CheckPackages(); });
        });
    }

    void Open(string target)
    {
        try { Process.Start(new ProcessStartInfo(target) { UseShellExecute = true }); }
        catch (Exception e) { Append(e.Message); }
    }

    // ---- Start, stop ----

    void Start()
    {
        if (MessageBox.Show(this, "Until you press Stop, Windows has no Bluetooth: earbuds, and Bluetooth mice and keyboards, disconnect.\n\n"
            + "Windows will ask for admin approval now, and again when you stop. It says \"unknown publisher\" because AnyPad isn't signed.\n\n"
            + "Only pair your own phone: for 3 minutes, one phone can pair without a code.", "Start AnyPad?",
            MessageBoxButtons.OKCancel, MessageBoxIcon.Information) != DialogResult.OK) return;
        problem = null;
        played = stopping = false;
        log.Clear();
        engine = Launch("--gui --parent " + Process.GetCurrentProcess().Id + " --files \"" + files + "\"", OnLine, OnEngineExit);
        Show("Starting...", Theme.Wait, "Approve the admin prompt. It may be behind other windows.");
        Refresh(null);
        forget.Visible = rumble.Visible = setup.Visible = false;
    }

    Process Launch(string arguments, Action<string> line, Action<int> exited)
    {
        var p = new Process();
        p.StartInfo = new ProcessStartInfo(Application.ExecutablePath, arguments)
        {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
        };
        p.OutputDataReceived += (s, e) => { if (e.Data != null) Post(() => line(e.Data)); };
        p.ErrorDataReceived += (s, e) => { if (e.Data != null) Post(() => line(e.Data)); };
        p.Start();
        p.BeginOutputReadLine();
        p.BeginErrorReadLine();
        Task.Run(() => { p.WaitForExit(); int code = p.ExitCode; Post(() => exited(code)); });
        return p;
    }

    void StopEngine()
    {
        if (stopping) return;
        stopping = true;
        Show("Stopping...", Theme.Wait, "Approve the admin prompt, so Windows gets its Bluetooth back. It may be behind other windows.");
        Refresh(null);
        // Before the relay is up there is nothing listening yet, so keep asking.
        var target = engine;
        Task.Run(() =>
        {
            for (int i = 0; i < 240 && target != null && !target.HasExited; i++) { Program.RequestStop(); Thread.Sleep(500); }
        });
    }

    void OnLine(string line)
    {
        Append(line);
        if (line.StartsWith("FAIL") || line.StartsWith("STOP") || line.StartsWith("Windows would not release") || line.StartsWith("Missing packages")
            || line.StartsWith("The adapter was not shared") || line.StartsWith("Not done")) problem = line;
        if (line.StartsWith("Released. Run this again")) problem = "The adapter was left over from an earlier run and is released now. Press Start again.";
        if (line.Contains("controller connected in Windows")) padOn = true;
        else if (line.Contains("controller not connected in Windows")) padOn = false;
        else if (line.Contains("ready: on the phone")) pcOn = true;
        else if (line.Contains("phone is listening") || (played && line.EndsWith("phone connected"))) phoneOn = true;
        else if (line.Contains("phone DISCONNECTED")) phoneOn = false;
        path.Set(padOn, pcOn, phoneOn);
        if (stopping) return;
        if (line.Contains("ready: on the phone")) Show("Waiting for your iPhone or iPad", Theme.Wait, "On it, open Settings > Bluetooth and tap Xbox Wireless Controller.");
        else if (line.Contains("accepting pairing")) Show("Pairing...", Theme.Wait, "Tap Pair on the iPhone or iPad if it asks.");
        else if (line.Contains("phone is listening") || (played && line.EndsWith("phone connected"))) { played = true; Show("Connected: play!", Theme.Good, "Open a game that supports controllers."); }
        else if (line.EndsWith("phone connected")) Show("Connecting...", Theme.Wait, "");
        else if (line.Contains("phone DISCONNECTED")) Show("Disconnected", Theme.Wait, "Open Bluetooth settings on the iPhone or iPad to reconnect.");
        else if (line.Contains("removed an out-of-date pairing")) Show("Pair it again", Theme.Wait, "Forget Xbox Wireless Controller on the iPhone or iPad, then tap it again.");
        else if (line.Contains("pairing is closed (time is up)") && !played) Show("Pairing closed", Theme.Wait, "Press Stop, then Start, to pair a phone. One that is already paired can still connect.");
    }

    void OnEngineExit(int code)
    {
        engine = null;
        stopping = false;
        phoneOn = false;
        if (code != 0 && problem == null) problem = "Something went wrong. See the details.";
        if (problem != null) ShowLog();
        if (closeAfter) { Close(); return; }
        Look();
    }

    void OnClosing(object sender, FormClosingEventArgs e)
    {
        if (engine == null) return;
        if (e.CloseReason == CloseReason.WindowsShutDown) { Program.RequestStop(); return; }
        e.Cancel = true;
        closeAfter = true;
        StopEngine();
    }

    // ---- Extras ----

    void Forget()
    {
        if (MessageBox.Show(this, "Forget every phone saved in WSL? They are moved aside, not deleted. Each one has to pair again.", "AnyPad",
            MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        Launch("--gui --files \"" + files + "\" --forget", Append, code => ShowLog());
    }

    void TestRumble()
    {
        rumble.Enabled = false;
        Launch("--gui --test-rumble", Append, code => { rumble.Enabled = engine == null; });
        ShowLog();
    }

    void SetUpPad()
    {
        string id;
        int device = Joy.Find(out id);
        if (device < 0) { Look(); return; }
        using (var f = new SetupForm(device, id, scale)) f.ShowDialog(this);
        Look();
    }

    void ToggleLog()
    {
        log.Visible = !log.Visible;
        details.Text = log.Visible ? "Hide details" : "Details";
        Fit();
    }

    void ShowLog()
    {
        if (!log.Visible) ToggleLog();
    }

    void Append(string line)
    {
        if (log.TextLength > 60000) log.Text = log.Text.Substring(30000);
        log.AppendText(line + Environment.NewLine);
    }

    void Post(Action action)
    {
        try { if (IsHandleCreated && !IsDisposed) BeginInvoke(action); }
        catch (InvalidOperationException) { }
    }
}
