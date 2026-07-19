using System.Globalization;
using System.Text;
using Vortice.DirectInput;

namespace SnowrunnerTelemetryAgent.Input;

public readonly record struct DirectInputThrottleSample(
    bool Connected,
    string DeviceName,
    string Value,
    string ThrottleAxis,
    int RawAxis);

public static class DirectInputReader
{
    private static readonly object Gate = new();
    private static IDirectInput8? _directInput;
    private static readonly List<BoundDevice> Bound = new();

    private static readonly string[] AxisNames = ["X", "Y", "Z", "Ry", "Rz", "S0", "S1"];

    public static DirectInputThrottleSample Read()
    {
        lock (Gate)
        {
            try
            {
                EnsureDevices();
                return ScanBestThrottle() ?? NotConnected();
            }
            catch
            {
                ResetDevices();
                return NotConnected();
            }
        }
    }

    public static bool TryDetect(out string deviceName)
    {
        var sample = Read();
        deviceName = sample.Connected ? sample.DeviceName : "";
        return sample.Connected;
    }

    public static string ListDevicesReport()
    {
        var sb = new StringBuilder();
        try
        {
            using var directInput = DInput.DirectInput8Create();
            var devices = directInput.GetDevices(DeviceClass.All, DeviceEnumerationFlags.AllDevices);
            if (devices.Count == 0)
            {
                return "[DI] Ningun dispositivo DirectInput enumerado.";
            }

            sb.AppendLine($"[DI] {devices.Count} dispositivo(s):");
            foreach (var (device, score) in RankAll(devices))
            {
                var label = Label(device);
                sb.AppendLine($"  score={score,4} type={device.Type,-10} {label}");
                try
                {
                    using var handle = OpenDevice(directInput, device.InstanceGuid);
                    if (handle is null)
                    {
                        sb.AppendLine("    [no readable]");
                        continue;
                    }

                    var state = handle.GetCurrentJoystickState();
                    sb.AppendLine(
                        $"    axes  X={state.X,6} Y={state.Y,6} Z={state.Z,6} Ry={state.RotationY,6} Rz={state.RotationZ,6} S0={state.Sliders[0],6} S1={state.Sliders[1],6}");
                    foreach (var obj in handle.GetObjects(DeviceObjectTypeFlags.Axis))
                    {
                        sb.AppendLine($"    obj   off=0x{unchecked((int)obj.Offset):X2} name={obj.Name}");
                    }
                }
                catch (Exception ex)
                {
                    sb.AppendLine($"    [no readable] {ex.Message}");
                }
            }

            sb.AppendLine();
            if (!devices.Any(d => IsRaceWheelLabel(Label(d))))
            {
                sb.AppendLine("[DI] VelocityOne Race Wheel NO aparece en la lista.");
                sb.AppendLine("     Con SnowRunner abierto usa WinMM: .\\run_agent.bat --list-devices");
            }
        }
        catch (Exception ex)
        {
            sb.AppendLine($"[DI] Error: {ex.Message}");
        }

        return sb.ToString().TrimEnd();
    }

    public static void WatchInputLoop(int intervalMs = 250)
    {
        using var directInput = DInput.DirectInput8Create();
        var devices = directInput.GetDevices(DeviceClass.All, DeviceEnumerationFlags.AttachedOnly)
            .Where(IsWatchTarget)
            .Select(d => (Device: d, Score: ScoreDevice(d)))
            .OrderByDescending(x => x.Score)
            .Select(x => x.Device)
            .ToList();

        if (devices.Count == 0)
        {
            Console.WriteLine("[watch-di] Ningun volante/mando DirectInput.");
            return;
        }

        Console.WriteLine($"[watch-di] {devices.Count} dispositivo(s). Pisa/suelta el gas. Ctrl+C para salir.");
        Console.WriteLine("        Ry=0x10 | Rz=0x14 (pedal VelocityOne en SnowRunner = winmm)");
        Console.WriteLine();

        var last = new Dictionary<Guid, int[]>();
        using var cancel = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true;
            cancel.Cancel();
        };

        while (!cancel.Token.IsCancellationRequested)
        {
            foreach (var device in devices)
            {
                var label = Label(device);
                try
                {
                    using var handle = OpenDevice(directInput, device.InstanceGuid);
                    if (handle is null)
                    {
                        continue;
                    }

                    var state = handle.GetCurrentJoystickState();
                    var vals = new[] { state.X, state.Y, state.Z, state.RotationY, state.RotationZ, state.Sliders[0], state.Sliders[1] };

                    if (!last.TryGetValue(device.InstanceGuid, out var prev))
                    {
                        last[device.InstanceGuid] = vals;
                        Console.WriteLine($"[{label}] base {FormatAxes(vals)}");
                        continue;
                    }

                    for (var i = 0; i < vals.Length; i++)
                    {
                        if (Math.Abs(vals[i] - prev[i]) >= 400)
                        {
                            Console.WriteLine(
                                $"{DateTime.Now:HH:mm:ss} [{label}] {AxisNames[i]}={vals[i],6} (delta {vals[i] - prev[i]:+0;-0})");
                        }
                    }

                    last[device.InstanceGuid] = vals;
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"[{label}] error: {ex.Message}");
                }
            }

            Thread.Sleep(intervalMs);
        }
    }

    private static void EnsureDevices()
    {
        if (Bound.Count > 0)
        {
            return;
        }

        _directInput ??= DInput.DirectInput8Create();
        var devices = _directInput.GetDevices(DeviceClass.All, DeviceEnumerationFlags.AttachedOnly);
        foreach (var (device, score) in PickBoundCandidates(devices))
        {
            if (score < -100)
            {
                continue;
            }

            try
            {
                var handle = OpenDevice(_directInput, device.InstanceGuid);
                if (handle is null)
                {
                    continue;
                }

                Bound.Add(new BoundDevice(handle, Label(device), DetectThrottleAxes(handle, Label(device))));
            }
            catch
            {
                // SnowRunner puede tener acceso exclusivo; probar otros.
            }
        }
    }

    private static DirectInputThrottleSample? ScanBestThrottle()
    {
        DirectInputThrottleSample? best = null;
        var bestValue = double.MinValue;

        foreach (var bound in Bound)
        {
            try
            {
                bound.Handle.Poll();
                var state = bound.Handle.GetCurrentJoystickState();
                foreach (var axis in bound.ThrottleAxes)
                {
                    var raw = ReadAxis(state, axis.Offset);
                    var value = FormatPedal(raw, axis.Invert);
                    if (!double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed)
                        || parsed <= bestValue)
                    {
                        continue;
                    }

                    bestValue = parsed;
                    best = new DirectInputThrottleSample(true, bound.Label, value, DiAxis.Label(axis.Offset), raw);
                }
            }
            catch
            {
                TryReacquire(bound.Handle);
            }
        }

        return best;
    }

    private static IDirectInputDevice8? OpenDevice(IDirectInput8 directInput, Guid instanceGuid)
    {
        try
        {
            var handle = directInput.CreateDevice(instanceGuid);
            handle.SetCooperativeLevel(IntPtr.Zero, CooperativeLevel.Background | CooperativeLevel.NonExclusive);
            handle.SetDataFormat<RawJoystickState>();
            handle.Acquire();
            handle.Poll();
            return handle;
        }
        catch
        {
            return null;
        }
    }

    private static IReadOnlyList<AxisBinding> DetectThrottleAxes(IDirectInputDevice8 device, string label)
    {
        var axes = device.GetObjects(DeviceObjectTypeFlags.Axis)
            .Where(obj => IsPedalAxisName(obj.Name ?? ""))
            .Select(obj => new AxisBinding(unchecked((int)obj.Offset), false))
            .ToList();

        if (axes.Count == 0)
        {
            var fallback = label.Contains("pedal", StringComparison.OrdinalIgnoreCase)
                ? DiAxis.Slider0
                : PreferRzAxis(label) ? DiAxis.Rz : DiAxis.Z;
            axes.Add(new AxisBinding(fallback, false));
        }

        device.Poll();
        var state = device.GetCurrentJoystickState();
        for (var i = 0; i < axes.Count; i++)
        {
            if (ReadAxis(state, axes[i].Offset) > 20000)
            {
                axes[i] = axes[i] with { Invert = true };
            }
        }

        return axes;
    }

    private static IEnumerable<(DeviceInstance Device, int Score)> PickBoundCandidates(
        IList<DeviceInstance> devices)
    {
        var ranked = RankAll(devices).ToList();
        var strong = ranked.Where(x => x.Score >= 50).Take(4).ToList();
        if (strong.Count > 0)
        {
            return strong;
        }

        return ranked
            .Where(x => x.Device.Type is DeviceType.Driving or DeviceType.Joystick && x.Score >= 15)
            .Take(2);
    }

    private static IEnumerable<(DeviceInstance Device, int Score)> RankAll(
        IList<DeviceInstance> devices) =>
        devices.Select(d => (d, ScoreDevice(d))).OrderByDescending(x => x.Item2);

    private static bool IsWatchTarget(DeviceInstance device) =>
        ScoreDevice(device) >= 15
        || device.Type is DeviceType.Driving or DeviceType.Joystick or DeviceType.FirstPerson;

    private static bool IsRaceWheelLabel(string label) =>
        !label.Contains("flightstick", StringComparison.OrdinalIgnoreCase)
        && !label.Contains("flight stick", StringComparison.OrdinalIgnoreCase)
        && (label.Contains("race wheel", StringComparison.OrdinalIgnoreCase)
            || (label.Contains("wheel", StringComparison.OrdinalIgnoreCase)
                && label.Contains("velocity", StringComparison.OrdinalIgnoreCase)));

    private static bool PreferRzAxis(string deviceName) =>
        !deviceName.Contains("pedal", StringComparison.OrdinalIgnoreCase)
        && (deviceName.Contains("velocity", StringComparison.OrdinalIgnoreCase)
            || deviceName.Contains("race", StringComparison.OrdinalIgnoreCase)
            || deviceName.Contains("turtle", StringComparison.OrdinalIgnoreCase)
            || deviceName.Contains("wheel", StringComparison.OrdinalIgnoreCase));

    private static int ScoreDevice(DeviceInstance device)
    {
        var label = Label(device);
        var score = 0;
        if (label.Contains("velocity", StringComparison.OrdinalIgnoreCase))
        {
            score += 120;
        }

        if (label.Contains("flightstick", StringComparison.OrdinalIgnoreCase)
            || label.Contains("flight stick", StringComparison.OrdinalIgnoreCase))
        {
            score -= 200;
        }

        if (label.Contains("race", StringComparison.OrdinalIgnoreCase))
        {
            score += 150;
        }

        if (label.Contains("turtle", StringComparison.OrdinalIgnoreCase))
        {
            score += 100;
        }

        if (label.Contains("pedal", StringComparison.OrdinalIgnoreCase))
        {
            score += 200;
        }

        if (label.Contains("wheel", StringComparison.OrdinalIgnoreCase))
        {
            score += 80;
        }

        if (device.Type == DeviceType.Driving)
        {
            score += 70;
        }
        else if (device.Type is DeviceType.Joystick or DeviceType.Gamepad)
        {
            score += 30;
        }

        return score;
    }

    private static string Label(DeviceInstance device)
    {
        var text = $"{device.InstanceName} {device.ProductName}".Trim();
        return string.IsNullOrWhiteSpace(text) ? "DirectInput device" : text;
    }

    private static bool IsPedalAxisName(string name)
    {
        var lower = name.ToLowerInvariant();
        return lower.Contains("accel")
            || lower.Contains("accelerator")
            || lower.Contains("gas")
            || lower.Contains("throttle")
            || lower.Contains("aceler")
            || lower.Contains("regulador")
            || lower.Contains("rotación z")
            || lower.Contains("rotation z")
            || lower.Contains("rot z")
            || lower is "rz";
    }

    private static string FormatAxes(int[] vals)
    {
        var parts = new string[vals.Length];
        for (var i = 0; i < vals.Length; i++)
        {
            parts[i] = $"{AxisNames[i]}={vals[i]}";
        }

        return string.Join(" ", parts);
    }

    private static int ReadAxis(JoystickState state, int offset) => offset switch
    {
        DiAxis.X => state.X,
        DiAxis.Y => state.Y,
        DiAxis.Z => state.Z,
        DiAxis.Rx => state.RotationX,
        DiAxis.Ry => state.RotationY,
        DiAxis.Rz => state.RotationZ,
        DiAxis.Slider0 => state.Sliders[0],
        DiAxis.Slider1 => state.Sliders[1],
        _ => 0,
    };

    private static string FormatPedal(int raw, bool invert)
    {
        var normalized = raw >= 0 ? raw / 32767.0 : (raw + 32768.0) / 65535.0;
        if (invert)
        {
            normalized = 1.0 - normalized;
        }

        return Math.Clamp(normalized, 0, 1).ToString("F3", CultureInfo.InvariantCulture);
    }

    private static void TryReacquire(IDirectInputDevice8 handle)
    {
        try
        {
            handle.Unacquire();
            handle.Acquire();
        }
        catch
        {
        }
    }

    private static DirectInputThrottleSample NotConnected() =>
        new(false, "", "", "", 0);

    private static void ResetDevices()
    {
        foreach (var bound in Bound)
        {
            bound.Handle.Dispose();
        }

        Bound.Clear();
    }

    private sealed class BoundDevice(IDirectInputDevice8 handle, string label, IReadOnlyList<AxisBinding> throttleAxes)
    {
        public IDirectInputDevice8 Handle { get; } = handle;
        public string Label { get; } = label;
        public IReadOnlyList<AxisBinding> ThrottleAxes { get; } = throttleAxes;
    }

    private readonly record struct AxisBinding(int Offset, bool Invert);

    private static class DiAxis
    {
        public const int X = 0x00;
        public const int Y = 0x04;
        public const int Z = 0x08;
        public const int Rx = 0x0C;
        public const int Ry = 0x10;
        public const int Rz = 0x14;
        public const int Slider0 = 0x18;
        public const int Slider1 = 0x1C;

        public static string Label(int offset) => offset switch
        {
            Slider0 => "Slider0",
            Slider1 => "Slider1",
            Rx => "Rx",
            Ry => "Ry",
            Z => "Z",
            Rz => "Rz",
            Y => "Y",
            X => "X",
            _ => $"0x{offset:X}",
        };
    }
}
