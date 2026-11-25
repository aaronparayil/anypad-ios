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
            Application.Run(new MainForm());
        }
        return 0;
    }
}

class Check
{
    public Label Mark, Text;
    public LinkLabel Fix;
}

class MainForm : Form
{
    static readonly Color Good = Color.FromArgb(22, 128, 61), Bad = Color.FromArgb(190, 30, 45), Wait = Color.FromArgb(160, 110, 0), Dim = Color.FromArgb(95, 95, 95);

    readonly Label status = new Label(), hint = new Label();
    readonly Button main = new Button();
    readonly TextBox log = new TextBox();
    readonly LinkLabel details = new LinkLabel(), forget = new LinkLabel(), rumble = new LinkLabel();
    readonly Dictionary<string, Check> checks = new Dictionary<string, Check>();
    readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    readonly string files = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "anypad-ios", "app");

    Process engine;
    bool looking, stopping, closeAfter, played, busy, filesOk;
    int packages = -1;      // -1 not checked yet, 0 missing, 1 ready, 2 no WSL
    string problem;

    public MainForm()
    {
        Text = "AnyPad";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Font = new Font("Segoe UI", 9.5f);
        BackColor = Color.White;
        // All sizes below are for 100 % scaling; Place() enlarges them on sharper screens.
        AutoScaleMode = AutoScaleMode.None;
        using (var g = CreateGraphics()) scale = g.DpiX / 96f;
        ClientSize = new Size(Px(470), Px(388));
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;

        Place(status, 17, 14, 436, 36);
        status.Font = new Font("Segoe UI Semibold", 15f);
        Place(hint, 21, 52, 430, 42);
        hint.ForeColor = Dim;
        Controls.Add(status);
        Controls.Add(hint);

        int y = 106;
        foreach (var name in new[] { "usbipd", "wsl", "adapter", "bluetooth", "phones", "pad" }) { AddCheck(name, y); y += 31; }

        Place(main, 20, y + 10, 430, 46);
        main.Font = new Font("Segoe UI Semibold", 12f);
        main.FlatStyle = FlatStyle.System;
        main.Click += (s, e) => { if (engine == null) Start(); else StopEngine(); };
        Controls.Add(main);
        AcceptButton = main;

        Link(details, "Show details", 20, y + 66, 110, () => ToggleLog());
        Link(forget, "Forget saved phones", 160, y + 66, 160, () => Forget());
        Link(rumble, "Test rumble", 340, y + 66, 110, () => TestRumble());
        rumble.TextAlign = ContentAlignment.TopRight;

        log.Multiline = true;
        log.ReadOnly = true;
        log.ScrollBars = ScrollBars.Vertical;
        log.BackColor = Color.FromArgb(246, 246, 246);
        log.Font = new Font("Consolas", 8.5f);
        Place(log, 20, y + 94, 430, 170);
        log.Visible = false;
        log.AccessibleName = "Details";
        Controls.Add(log);

        timer.Interval = 2500;
        timer.Tick += (s, e) => Look();
        Shown += (s, e) => { Unpack(); Look(); CheckPackages(); timer.Start(); };
        FormClosing += OnClosing;
        Show("Checking your PC...", Dim, "");
        Refresh(null);
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

    void AddCheck(string name, int y)
    {
        var c = new Check { Mark = new Label(), Text = new Label(), Fix = new LinkLabel() };
        Place(c.Mark, 20, y, 24, 24);
        c.Mark.Font = new Font("Segoe UI", 11f, FontStyle.Bold);
        Place(c.Text, 46, y + 2, 296, 24);
        c.Text.AutoEllipsis = true;
        Place(c.Fix, 344, y + 2, 106, 24);
        c.Fix.TextAlign = ContentAlignment.TopRight;
        c.Fix.Visible = false;
        c.Fix.LinkClicked += (s, e) => Fix(name);
        Controls.Add(c.Mark);
        Controls.Add(c.Text);
        Controls.Add(c.Fix);
        checks[name] = c;
    }

    void Link(LinkLabel l, string text, int x, int y, int w, Action click)
    {
        l.Text = text;
        Place(l, x, y, w, 22);
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
        c.Mark.Text = ok == null ? "•" : ok.Value ? "✓" : "✗";
        c.Mark.ForeColor = ok == null ? Dim : ok.Value ? Good : Bad;
        c.Text.Text = text;
        c.Fix.Text = fix ?? "";
        c.Fix.Visible = fix != null && engine == null && !busy;
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
        if (looking) return;
        looking = true;
        Task.Run(() =>
        {
            Program.Checks c = null;
            try { c = Program.Look(); } catch (Exception e) { Post(() => Append("Check failed: " + e.Message)); }
            Post(() => { looking = false; Refresh(c); });
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
        if (c == null)
        {
            foreach (var name in checks.Keys.ToList()) if (checks[name].Text.Text == "") Set(name, null, "Checking...", null);
            main.Enabled = engine != null && !stopping;
            main.Text = engine == null ? "Start" : stopping ? "Stopping..." : "Stop";
            return;
        }
        Set("pad", c.Pad, c.Pad ? "Gamepad connected" : "No gamepad: plug it in and turn it on", null);
        if (engine != null) { Refresh(null); return; }

        Set("usbipd", c.Usbipd, c.Usbipd ? "usbipd-win installed" : "usbipd-win is not installed", c.Usbipd ? null : "Get it");
        Set("wsl", packages == -1 ? (bool?)null : packages == 1,
            packages == -1 ? "Checking WSL..." : packages == 1 ? "WSL is ready" : packages == 0 ? "WSL needs 3 packages" : "WSL with Ubuntu is not set up",
            packages == 0 ? "Install" : packages == 2 ? "How to" : null);
        Set("adapter", c.Adapters == 1, c.Adapters == 1 ? "Intel Bluetooth adapter found" : c.Adapters > 1 ? "More than one Intel Bluetooth adapter" : c.Usbipd ? "No supported (Intel) Bluetooth adapter" : "Bluetooth adapter not checked yet", null);
        bool off = c.Radio == "Off" || c.Attached;
        Set("bluetooth", off, c.Attached ? "Adapter is in use by an earlier run" : off ? "Bluetooth is off in Windows" : c.Radio == null ? "Windows shows no Bluetooth: restart the PC" : "Turn Bluetooth off in Windows",
            off || c.Radio == null ? null : "Settings");
        Set("phones", c.Phones.Count == 0, c.Phones.Count == 0 ? "No phone is paired with Windows" : "Remove from Windows: " + string.Join(", ", c.Phones), c.Phones.Count == 0 ? null : "Settings");

        bool ready = filesOk && c.Usbipd && packages == 1 && c.Adapters == 1 && off && c.Phones.Count == 0;
        main.Text = "Start";
        main.Enabled = ready && !busy;
        if (busy) return;
        if (problem != null) Show("It stopped", Bad, problem);
        else if (ready) Show("Ready to start", Good, c.Attached ? "Start releases the adapter from the earlier run first; then press Start again."
            : c.Audio.Count > 0 ? "Switch off your Bluetooth headphones first; they can block the adapter." : "Windows has no Bluetooth while AnyPad runs.");
        else Show("Not ready yet", Wait, "Sort out the items marked ✗ below.");
    }

    void Fix(string name)
    {
        if (name == "usbipd") Open("https://github.com/dorssel/usbipd-win/releases/latest");
        else if (name == "bluetooth" || name == "phones") Open("ms-settings:bluetooth");
        else if (name == "wsl" && packages == 2) Open("https://learn.microsoft.com/windows/wsl/install");
        else if (name == "wsl") InstallPackages();
    }

    void InstallPackages()
    {
        if (MessageBox.Show(this, "This installs bluez, python3-dbus and python3-gi in your default WSL distro, from Ubuntu's own servers.\n\nContinue?",
            "AnyPad", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        busy = true;
        Show("Installing...", Wait, "This can take a few minutes.");
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
        Show("Starting...", Wait, "Approve the admin prompt. It may be behind other windows.");
        Refresh(null);
        foreach (var c in checks.Values) c.Fix.Visible = false;
        forget.Enabled = rumble.Enabled = false;
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
        Show("Stopping...", Wait, "Approve the admin prompt, so Windows gets its Bluetooth back. It may be behind other windows.");
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
        if (stopping) return;
        if (line.Contains("ready: on the phone")) Show("Waiting for your iPhone or iPad", Wait, "On it, open Settings > Bluetooth and tap Xbox Wireless Controller.");
        else if (line.Contains("accepting pairing")) Show("Pairing...", Wait, "Tap Pair on the iPhone or iPad if it asks.");
        else if (line.Contains("phone is listening") || (played && line.EndsWith("phone connected"))) { played = true; Show("Connected: play!", Good, "Open a game that supports controllers."); }
        else if (line.EndsWith("phone connected")) Show("Connecting...", Wait, "");
        else if (line.Contains("phone DISCONNECTED")) Show("Disconnected", Wait, "Open Bluetooth settings on the iPhone or iPad to reconnect.");
        else if (line.Contains("removed an out-of-date pairing")) Show("Pair it again", Wait, "Forget Xbox Wireless Controller on the iPhone or iPad, then tap it again.");
        else if (line.Contains("pairing is closed (time is up)") && !played) Show("Pairing closed", Wait, "Press Stop, then Start, to pair a phone. One that is already paired can still connect.");
    }

    void OnEngineExit(int code)
    {
        engine = null;
        stopping = false;
        forget.Enabled = rumble.Enabled = true;
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

    void ToggleLog()
    {
        log.Visible = !log.Visible;
        details.Text = log.Visible ? "Hide details" : "Show details";
        int bottom = log.Visible ? log.Bottom : details.Bottom;
        ClientSize = new Size(ClientSize.Width, bottom + Px(14));
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
