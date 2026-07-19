using System.Globalization;
using System.Runtime.InteropServices;
using System.Text;

namespace SnowrunnerTelemetryAgent.Input;

public readonly record struct WinMmThrottleSample(
    bool Connected,
    int JoyId,
    string DeviceName,
    string Value,
    string Axis,
    uint RawAxis);

public static class WinMmJoystickReader
{
    // Eje Rz en reposo suele quedar en el centro (p. ej. 32767/65535 ≈ 0.5); no es pedal pisado.
    private const double NeutralBandLow = 0.35;
    private const double NeutralBandHigh = 0.75;
    private const int MinRejectedScore = -50;
    private const int MaxJoyId = 16;
    private const uint JoyReturnR = 0x00000008;

    public static WinMmThrottleSample Read()
    {
        var best = default(WinMmThrottleSample);
        var bestScore = int.MinValue;

        for (var joyId = 0; joyId < MaxJoyId; joyId++)
        {
            if (Probe(joyId) is not { } candidate || candidate.Score <= bestScore)
            {
                continue;
            }

            bestScore = candidate.Score;
            best = candidate.Sample;
        }

        return bestScore > int.MinValue
            ? best
            : new WinMmThrottleSample(false, -1, "", "", "", 0);
    }

    public static string ListDevicesReport()
    {
        var sb = new StringBuilder();
        var found = 0;
        sb.AppendLine("[WinMM] joyGetPosEx (funciona con SnowRunner abierto):");

        for (var joyId = 0; joyId < MaxJoyId; joyId++)
        {
            if (!TryGetCaps(joyId, out var caps))
            {
                continue;
            }

            found++;
            var name = DeviceName(caps, joyId);
            sb.AppendLine($"  joy={joyId,2} score={ScoreDevice(name),4} {name}");
            if (TryReadThrottle(joyId, caps, out var axis, out var raw, out var value))
            {
                sb.AppendLine($"    {axis} raw={raw,5} throttle={value}  (SnowRunner: pedal=Eje RZ)");
            }
            else
            {
                sb.AppendLine("    [sin lectura de ejes]");
            }
        }

        if (found == 0)
        {
            sb.AppendLine("  (ningun joystick winmm)");
        }

        return sb.ToString().TrimEnd();
    }

    public static void WatchInputLoop(int intervalMs = 250)
    {
        using var cancel = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true;
            cancel.Cancel();
        };

        Console.WriteLine("[watch-winmm] Pisa/suelta el gas (Eje RZ). Ctrl+C para salir.");
        var last = new Dictionary<int, uint>();

        while (!cancel.Token.IsCancellationRequested)
        {
            for (var joyId = 0; joyId < MaxJoyId; joyId++)
            {
                if (!TryGetCaps(joyId, out var caps)
                    || !TryReadThrottle(joyId, caps, out var axis, out var raw, out var value))
                {
                    continue;
                }

                if (!last.TryGetValue(joyId, out var prev))
                {
                    last[joyId] = raw;
                    Console.WriteLine($"[joy{joyId} {caps.szPname}] base {axis}={raw} ({value})");
                    continue;
                }

                if (Math.Abs((int)raw - (int)prev) > 800)
                {
                    Console.WriteLine($"{DateTime.Now:HH:mm:ss} [joy{joyId}] {axis}={raw} throttle={value}");
                    last[joyId] = raw;
                }
            }

            Thread.Sleep(intervalMs);
        }
    }

    private static (WinMmThrottleSample Sample, int Score)? Probe(int joyId)
    {
        if (!TryGetCaps(joyId, out var caps))
        {
            return null;
        }

        var name = DeviceName(caps, joyId);
        var score = ScoreDevice(name);
        if (score < MinRejectedScore
            || !TryReadThrottle(joyId, caps, out var axis, out var raw, out var value))
        {
            return null;
        }

        return (new WinMmThrottleSample(true, joyId, name, value, axis, raw), score);
    }

    private static bool TryReadThrottle(int joyId, JoyCaps caps, out string axis, out uint raw, out string value)
    {
        axis = "Rz";
        raw = 0;
        value = "";

        var info = new JoyInfoEx
        {
            dwSize = (uint)Marshal.SizeOf<JoyInfoEx>(),
            dwFlags = JoyReturnR,
        };

        if (joyGetPosEx(joyId, ref info) != 0)
        {
            return false;
        }

        raw = info.dwRpos;
        value = FormatThrottle(raw, caps.wRmin, caps.wRmax);
        return true;
    }

    private static string FormatThrottle(uint raw, uint min, uint max)
    {
        var normalized = max > min
            ? (raw - min) / (double)(max - min)
            : raw / 65535.0;
        normalized = Math.Clamp(normalized, 0, 1);

        if (normalized > NeutralBandLow && normalized < NeutralBandHigh)
        {
            return "0.000";
        }

        return F3(normalized);
    }

    private static string DeviceName(JoyCaps caps, int joyId) =>
        caps.szPname ?? $"joystick_{joyId}";

    private static bool TryGetCaps(int joyId, out JoyCaps caps)
    {
        caps = new JoyCaps();
        return joyGetDevCapsW(joyId, ref caps, Marshal.SizeOf<JoyCaps>()) == 0;
    }

    private static string F3(double value) => value.ToString("F3", CultureInfo.InvariantCulture);

    private static int ScoreDevice(string name)
    {
        var score = 0;
        if (name.Contains("velocity", StringComparison.OrdinalIgnoreCase))
        {
            score += 120;
        }

        if (name.Contains("flightstick", StringComparison.OrdinalIgnoreCase))
        {
            score -= 200;
        }

        if (name.Contains("race", StringComparison.OrdinalIgnoreCase))
        {
            score += 150;
        }

        if (name.Contains("turtle", StringComparison.OrdinalIgnoreCase))
        {
            score += 100;
        }

        if (name.Contains("wheel", StringComparison.OrdinalIgnoreCase))
        {
            score += 80;
        }

        return score;
    }

    [DllImport("winmm.dll")]
    private static extern uint joyGetPosEx(int joyId, ref JoyInfoEx info);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    private static extern uint joyGetDevCapsW(int joyId, ref JoyCaps caps, int size);

    [StructLayout(LayoutKind.Sequential)]
    private struct JoyInfoEx
    {
        public uint dwSize;
        public uint dwFlags;
        public uint dwXpos;
        public uint dwYpos;
        public uint dwZpos;
        public uint dwRpos;
        public uint dwUpos;
        public uint dwVpos;
        public uint dwButtons;
        public uint dwButtonNumber;
        public uint dwPOV;
        public uint dwReserved1;
        public uint dwReserved2;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct JoyCaps
    {
        public ushort wMid;
        public ushort wPid;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string szPname;
        public uint wXmin;
        public uint wXmax;
        public uint wYmin;
        public uint wYmax;
        public uint wZmin;
        public uint wZmax;
        public uint wNumButtons;
        public uint wPeriodMin;
        public uint wPeriodMax;
        public uint wRmin;
        public uint wRmax;
        public uint wUmin;
        public uint wUmax;
        public uint wVmin;
        public uint wVmax;
        public uint wCaps;
        public uint wMaxAxes;
        public uint wNumAxes;
        public uint wMaxButtons;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string szRegKey;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string szOEMVxD;
    }
}
