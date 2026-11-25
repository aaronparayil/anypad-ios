// Windows pairing test: does a phone accept this PC as a Bluetooth LE keyboard or gamepad?
//
//   pairing_test.exe keyboard    types a short line on the phone when you press Enter
//   pairing_test.exe gamepad     taps the A button every 2 seconds
//   add --seconds N to stop by itself, --battery to also offer a Battery service,
//   --dry-run to create the services without advertising anything
//
// Build with build.cmd. It uses only the C# compiler and Bluetooth API that ship with Windows.
// Pairing is not accepted by this program: Windows itself asks you, if it asks at all.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.GenericAttributeProfile;
using Windows.Foundation;
using Windows.Storage.Streams;

// Small stand-ins for the Windows SDK helpers, so no SDK is needed to build.
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
                else if (status == AsyncStatus.Canceled) done.TrySetCanceled();
                else done.TrySetException(op.ErrorCode ?? new Exception("Windows reported an unknown error"));
            }
            catch (Exception e) { done.TrySetException(e); }
        };
        return done.Task.GetAwaiter();
    }

    public static IBuffer AsBuffer(this byte[] bytes)
    {
        var writer = new DataWriter();
        writer.WriteBytes(bytes);
        return writer.DetachBuffer();
    }

    public static byte[] ToArray(this IBuffer buffer)
    {
        var bytes = new byte[buffer.Length];
        DataReader.FromBuffer(buffer).ReadBytes(bytes);
        return bytes;
    }
}

static class Program
{
    const string Typed = "hello from windows";
    const byte ReportId = 1, RumbleReportId = 3;

    // Boot-style keyboard, report 1: modifiers, reserved, six keys (8 bytes).
    const string KeyboardMap =
        "05010906A1018501050719E029E71500250175019508810295017508810195067508150025650507190029658100C0";

    // The gamepad layout iOS accepted from the Linux test (copied from pairing_test.py).
    const string GamepadMap = 
        "05010905A10185010901A10009300931150027FFFF0000950275108102C00901A100093209351500" +
        "27FFFF0000950275108102C0050209C5150026FF039501750A810215002500750695018103050209" +
        "C4150026FF039501750A81021500250075069501810305010939150125083500463B016614007504" +
        "950181427504950115002500350045006500810305091901290F150025017501950F810215002500" +
        "750195018103050C0AB2001500250195017501810215002500750795018103050F09218503A10209" +
        "9715002501750495019102150025007504950191030970150025647508950491020950660110550E" +
        "150026FF0075089501910209A7150026FF0075089501910265005500097C150026FF007508950191" +
        "02C0C0";

    static readonly Stopwatch Clock = Stopwatch.StartNew();
    static readonly object LogLock = new object();
    static volatile bool stop;
    static volatile int subscribers;
    static byte[] current;
    static GattLocalCharacteristic input;
    static readonly List<GattServiceProvider> providers = new List<GattServiceProvider>();

    static void Log(string text)
    {
        lock (LogLock) Console.WriteLine("[{0,6:0.0}s] {1}", Clock.Elapsed.TotalSeconds, text);
    }

    static byte[] Hex(string s)
    {
        var b = new byte[s.Length / 2];
        for (int i = 0; i < b.Length; i++) b[i] = Convert.ToByte(s.Substring(i * 2, 2), 16);
        return b;
    }

    static Guid Uuid(uint shortId)
    {
        return BluetoothUuidHelper.FromShortId(shortId);
    }

    static int Main(string[] args)
    {
        string mode = args.Length > 0 ? args[0].ToLowerInvariant() : "";
        if (mode != "keyboard" && mode != "gamepad")
        {
            Console.WriteLine("Usage: pairing_test.exe keyboard | gamepad  [--seconds N] [--battery] [--dry-run]");
            return 2;
        }
        int seconds = 0;
        int at = Array.IndexOf(args, "--seconds");
        if (at >= 0 && (at + 1 >= args.Length || !int.TryParse(args[at + 1], out seconds)))
        {
            Console.WriteLine("--seconds needs a number");
            return 2;
        }
        // Two copies would fight over the same Bluetooth service and neither would work properly.
        bool first;
        var single = new Mutex(true, "Local\anypad-windows-pairing-test", out first);
        if (!first)
        {
            Console.WriteLine("Another copy of this test is running. Stop it with Ctrl+C first.");
            return 3;
        }
        Console.CancelKeyPress += (s, e) => { e.Cancel = true; stop = true; };
        try
        {
            return Run(mode == "gamepad", seconds, args.Contains("--battery"), args.Contains("--dry-run")).GetAwaiter().GetResult();
        }
        catch (Exception e)
        {
            Log("FAIL: " + e.GetType().Name + ": " + e.Message);
            return 1;
        }
        finally
        {
            foreach (var p in providers)
            {
                try { p.StopAdvertising(); } catch (Exception) { }
            }
            GC.KeepAlive(single);
        }
    }

    static async Task<int> Run(bool gamepad, int seconds, bool battery, bool dryRun)
    {
        var adapter = await BluetoothAdapter.GetDefaultAsync();
        if (adapter == null || !adapter.IsPeripheralRoleSupported)
        {
            Log("FAIL: no Bluetooth adapter that can act as a peripheral");
            return 1;
        }
        var radio = await adapter.GetRadioAsync();
        if (!dryRun && (radio == null || radio.State != Windows.Devices.Radios.RadioState.On))
        {
            Log("FAIL: Bluetooth is off. Turn it on in Windows Settings and run again");
            return 1;
        }

        current = gamepad ? Pad(false) : new byte[8];
        var hid = await CreateService("HID", Uuid(0x1812));
        if (hid == null) return 1;

        await Fixed(hid, 0x2A4A, "HID Information", new byte[] { 0x11, 0x01, 0x00, 0x02 });
        await Fixed(hid, 0x2A4B, "Report Map", Hex(gamepad ? GamepadMap : KeyboardMap));

        var control = await Create(hid, 0x2A4C, "HID Control Point", new GattLocalCharacteristicParameters
        {
            CharacteristicProperties = GattCharacteristicProperties.WriteWithoutResponse,
            WriteProtectionLevel = GattProtectionLevel.EncryptionRequired
        });
        control.WriteRequested += (s, e) => OnWrite("control point", e);

        input = await Create(hid, 0x2A4D, "Input Report", new GattLocalCharacteristicParameters
        {
            CharacteristicProperties = GattCharacteristicProperties.Read | GattCharacteristicProperties.Notify,
            ReadProtectionLevel = GattProtectionLevel.EncryptionRequired
        });
        await Reference(input, ReportId, 1);
        input.ReadRequested += (s, e) => OnRead("input report", e, () => current);
        input.SubscribedClientsChanged += (s, e) =>
        {
            subscribers = s.SubscribedClients.Count;
            Log(subscribers > 0
                ? "CONNECTED: the phone is listening for input (not a pass by itself)"
                : "the phone stopped listening");
        };

        if (gamepad)
        {
            var output = await Create(hid, 0x2A4D, "Output Report", new GattLocalCharacteristicParameters
            {
                CharacteristicProperties = GattCharacteristicProperties.Read | GattCharacteristicProperties.Write
                    | GattCharacteristicProperties.WriteWithoutResponse,
                ReadProtectionLevel = GattProtectionLevel.EncryptionRequired,
                WriteProtectionLevel = GattProtectionLevel.EncryptionRequired
            });
            await Reference(output, RumbleReportId, 2);
            output.ReadRequested += (s, e) => OnRead("output report", e, () => new byte[8]);
            output.WriteRequested += (s, e) => OnWrite("rumble", e);
        }

        if (battery)
        {
            var bat = await CreateService("Battery", Uuid(0x180F));
            if (bat == null) return 1;
            await Fixed(bat, 0x2A19, "Battery Level", new byte[] { 100 });
        }

        if (dryRun)
        {
            Log("dry run: Windows accepted every " + (gamepad ? "gamepad" : "keyboard") + " part; nothing was advertised");
            return 0;
        }

        if (!await Advertise()) return 1;
        Log("advertising this PC as a " + (gamepad ? "GAMEPAD" : "KEYBOARD"));
        Log("on the phone: Settings > Bluetooth, look for '" + Environment.MachineName + "'");
        Log("if Windows asks whether to pair or allow the device, accept only if it is your phone");
        Log(gamepad ? "Ctrl+C stops. A is tapped every 2 s once the phone is listening"
                    : "Ctrl+C stops. Open Notes on the phone, then press Enter here to type \"" + Typed + "\"");

        double lastTap = 0;
        bool announced = false;
        while (!stop && (seconds == 0 || Clock.Elapsed.TotalSeconds < seconds))
        {
            if (gamepad)
            {
                if (subscribers > 0 && Clock.Elapsed.TotalSeconds - lastTap >= 2)
                {
                    lastTap = Clock.Elapsed.TotalSeconds;
                    bool ok = await Send(Pad(true));
                    await Task.Delay(200);
                    ok &= await Send(Pad(false));
                    if (ok && !announced)
                    {
                        Log("sent the first A tap");
                        announced = true;
                    }
                }
            }
            else if (!Console.IsInputRedirected && Console.KeyAvailable
                     && Console.ReadKey(true).Key == ConsoleKey.Enter)
            {
                if (subscribers == 0) Log("the phone is not listening yet");
                else await TypeLine();
            }
            await Task.Delay(50);
        }
        await Send(gamepad ? Pad(false) : new byte[8]);     // release everything
        Log("stopping");
        return 0;
    }

    // Windows often reports Aborted for a moment before Started, so wait, then try again.
    static async Task<bool> Advertise()
    {
        for (int attempt = 1; attempt <= 5 && !stop; attempt++)
        {
            foreach (var p in providers)
                p.StartAdvertising(new GattServiceProviderAdvertisingParameters
                {
                    IsConnectable = true,
                    IsDiscoverable = p == providers[0]
                });
            for (int i = 0; i < 30 && !stop; i++)
            {
                if (providers[0].AdvertisementStatus.ToString().StartsWith("Started")) return true;
                await Task.Delay(100);
            }
            Log("advertising did not start (attempt " + attempt + " of 5: " + providers[0].AdvertisementStatus + ")");
            foreach (var p in providers)
            {
                try { p.StopAdvertising(); } catch (Exception) { }
            }
            await Task.Delay(1000);
        }
        if (!stop) Log("FAIL: Windows would not advertise. Turn Bluetooth off and on, then run again");
        return false;
    }

    static async Task<GattLocalService> CreateService(string name, Guid uuid)
    {
        var result = await GattServiceProvider.CreateAsync(uuid);
        if (result.Error != BluetoothError.Success)
        {
            Log("FAIL: Windows refused the " + name + " service: " + result.Error);
            return null;
        }
        var provider = result.ServiceProvider;
        provider.AdvertisementStatusChanged += (s, e) =>
            Log(name + " advertising: " + e.Status + (e.Error == BluetoothError.Success ? "" : " (" + e.Error + ")"));
        providers.Add(provider);
        return provider.Service;
    }

    static async Task<GattLocalCharacteristic> Create(GattLocalService service, uint id, string name,
                                                     GattLocalCharacteristicParameters p)
    {
        var result = await service.CreateCharacteristicAsync(Uuid(id), p);
        if (result.Error != BluetoothError.Success)
            throw new InvalidOperationException("Windows refused " + name + ": " + result.Error);
        return result.Characteristic;
    }

    static Task<GattLocalCharacteristic> Fixed(GattLocalService service, uint id, string name, byte[] value)
    {
        return Create(service, id, name, new GattLocalCharacteristicParameters
        {
            CharacteristicProperties = GattCharacteristicProperties.Read,
            ReadProtectionLevel = GattProtectionLevel.EncryptionRequired,
            StaticValue = value.AsBuffer()
        });
    }

    static async Task Reference(GattLocalCharacteristic c, byte id, byte type)
    {
        var result = await c.CreateDescriptorAsync(Uuid(0x2908), new GattLocalDescriptorParameters
        {
            ReadProtectionLevel = GattProtectionLevel.EncryptionRequired,
            StaticValue = new byte[] { id, type }.AsBuffer()
        });
        if (result.Error != BluetoothError.Success)
            throw new InvalidOperationException("Windows refused a Report Reference: " + result.Error);
    }

    static async void OnRead(string name, GattReadRequestedEventArgs e, Func<byte[]> value)
    {
        var deferral = e.GetDeferral();
        try
        {
            var request = await e.GetRequestAsync();
            if (request != null) request.RespondWithValue(value().AsBuffer());
            Log("phone read the " + name);
        }
        catch (Exception x) { Log("read failed: " + x.Message); }
        finally { deferral.Complete(); }
    }

    static bool writeSeen;

    static async void OnWrite(string name, GattWriteRequestedEventArgs e)
    {
        var deferral = e.GetDeferral();
        try
        {
            var request = await e.GetRequestAsync();
            if (request == null) return;
            if (request.Option == GattWriteOption.WriteWithResponse) request.Respond();
            if (name != "rumble" || !writeSeen) Log("phone wrote " + name + ": " + BitConverter.ToString(request.Value.ToArray()));
            if (name == "rumble") writeSeen = true;
        }
        catch (Exception x) { Log("write failed: " + x.Message); }
        finally { deferral.Complete(); }
    }

    static async Task<bool> Send(byte[] report)
    {
        current = report;
        if (subscribers == 0) return false;
        var results = await input.NotifyValueAsync(report.AsBuffer());
        foreach (var r in results)
            if (r.Status != GattCommunicationStatus.Success)
            {
                Log("sending input failed: " + r.Status);
                return false;
            }
        return true;
    }

    // Same 16-byte Xbox-style report as the Linux version; bit 0 of the buttons is A.
    static byte[] Pad(bool a)
    {
        var r = new byte[16];
        for (int i = 1; i < 8; i += 2) r[i] = 0x80;     // sticks centred at 32768
        r[13] = (byte)(a ? 1 : 0);
        return r;
    }

    static async Task TypeLine()
    {
        bool ok = true;
        foreach (char ch in Typed)
        {
            var r = new byte[8];
            r[2] = ch == ' ' ? (byte)0x2C : (byte)(0x04 + (ch - 'a'));
            ok &= await Send(r);
            await Task.Delay(30);
            ok &= await Send(new byte[8]);
            await Task.Delay(30);
        }
        Log(ok ? "typed \"" + Typed + "\"" : "typing did not fully go through");
    }
}
