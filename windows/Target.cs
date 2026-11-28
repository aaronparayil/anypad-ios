// Which kind of phone this build is for. AnyPad-Android.exe is built with /define:ANDROID;
// controller.exe takes --android. Only the words differ: the controller it shows is the same.
static class Target
{
#if ANDROID
    public static bool Android = true;
#else
    public static bool Android = false;
#endif

    public static string Phone { get { return Android ? "Android phone or tablet" : "iPhone or iPad"; } }
    public static string Short { get { return Android ? "Android" : "iPhone / iPad"; } }
    public static string App { get { return Android ? "AnyPad for Android" : "AnyPad for iPhone and iPad"; } }
    public static string PairSteps
    {
        get
        {
            return Android ? "On it, open Bluetooth settings, tap Pair new device, then Xbox Wireless Controller."
                : "On it, open Settings > Bluetooth and tap Xbox Wireless Controller.";
        }
    }
    public static string RelayArg { get { return Android ? "--phone android" : "--phone ios"; } }
}
