using System.Globalization;
using System.Text;
using Windows.Gaming.Input;

namespace SnowrunnerTelemetryAgent.Input;

public readonly record struct WinGameThrottleSample(
    bool Connected,
    int Score,
    string DeviceName,
    string Value,
    string AxisLabel,
    double Throttle);

public static class WinGameControllerReader
{
    private const int MinScore = 15;

    public static WinGameThrottleSample Read()
    {
        var best = default(WinGameThrottleSample);
        var bestScore = int.MinValue;

        foreach (var controller in RawGameController.RawGameControllers)
        {
            Consider(ref best, ref bestScore, Probe(controller).Sample);
        }

        return bestScore > int.MinValue
            ? best
            : new WinGameThrottleSample(false, 0, "", "", "", 0);
    }

    public static string ListDevicesReport()
    {
        var controllers = RawGameController.RawGameControllers.ToList();
        if (controllers.Count == 0)
        {
            return "[WinGame] Ningun volante/mando HID (RawGameController).";
        }

        var sb = new StringBuilder();
        sb.AppendLine($"[WinGame] RawGameControllers={controllers.Count}");

        var racingWheelCount = 0;
        foreach (var controller in controllers.OrderByDescending(c => ScoreDevice(c.DisplayName ?? "")))
        {
            var (sample, kind) = Probe(controller);
            if (kind == "RacingWheel")
            {
                racingWheelCount++;
            }

            AppendDevice(sb, sample, kind);
        }

        if (racingWheelCount == 0)
        {
            sb.AppendLine();
            sb.AppendLine("[WinGame] RacingWheel=0 — el VelocityOne Race Wheel no esta conectado como volante.");
            sb.AppendLine("          Flightstick es otro periferico; no sustituye al volante.");
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

        Console.WriteLine("[watch-win] Pisa/suelta el gas. Ctrl+C para salir.");
        var last = new Dictionary<string, double>();

        while (!cancel.Token.IsCancellationRequested)
        {
            var sample = Read();
            if (!sample.Connected)
            {
                Console.WriteLine("[watch-win] Sin lectura HID.");
                Thread.Sleep(intervalMs);
                continue;
            }

            var key = $"{sample.DeviceName}:{sample.AxisLabel}";
            if (!last.TryGetValue(key, out var prev))
            {
                last[key] = sample.Throttle;
                Console.WriteLine($"[{sample.DeviceName}] base throttle={sample.Throttle:F3} ({sample.AxisLabel})");
            }
            else if (Math.Abs(sample.Throttle - prev) > 0.02)
            {
                Console.WriteLine(
                    $"{DateTime.Now:HH:mm:ss} [{sample.DeviceName}] throttle={sample.Throttle:F3} (delta {(sample.Throttle - prev):+0.000;-0.000})");
                last[key] = sample.Throttle;
            }

            Thread.Sleep(intervalMs);
        }
    }

    private static (WinGameThrottleSample Sample, string Kind) Probe(RawGameController controller)
    {
        if (RacingWheel.FromGameController(controller) is { } wheel)
        {
            return (ReadRacingWheel(wheel), "RacingWheel");
        }

        if (FlightStick.FromGameController(controller) is { } stick)
        {
            return (ReadFlightStick(stick), "FlightStick");
        }

        return (ReadRaw(controller), "Raw");
    }

    private static WinGameThrottleSample ReadRacingWheel(RacingWheel wheel)
    {
        var name = ControllerName(wheel) ?? "RacingWheel";
        var throttle = wheel.GetCurrentReading().Throttle;
        return Sample(name, 200, "RacingWheel.Throttle", throttle);
    }

    private static WinGameThrottleSample ReadFlightStick(FlightStick stick)
    {
        var name = ControllerName(stick) ?? "FlightStick";
        var throttle = Math.Clamp(stick.GetCurrentReading().Throttle, 0, 1);
        return Sample(name, 0, "FlightStick.Throttle", throttle);
    }

    private static WinGameThrottleSample ReadRaw(RawGameController controller)
    {
        var name = controller.DisplayName ?? "RawGameController";
        var buttons = new bool[controller.ButtonCount];
        var switches = new GameControllerSwitchPosition[controller.SwitchCount];
        var axes = new double[controller.AxisCount];
        controller.GetCurrentReading(buttons, switches, axes);

        var throttle = axes.Length == 0 ? 0 : axes.Max();
        var axisLabel = axes.Length == 0 ? "none" : $"max(axis[0..{axes.Length - 1}])";
        return Sample(name, 0, axisLabel, throttle);
    }

    private static WinGameThrottleSample Sample(string name, int scoreBonus, string axisLabel, double throttle) =>
        new(
            true,
            ScoreDevice(name) + scoreBonus,
            name,
            F3(throttle),
            axisLabel,
            throttle);

    private static string? ControllerName(IGameController controller) =>
        RawGameController.FromGameController(controller)?.DisplayName;

    private static void Consider(ref WinGameThrottleSample best, ref int bestScore, WinGameThrottleSample sample)
    {
        if (!sample.Connected || sample.Score < MinScore || sample.Score <= bestScore)
        {
            return;
        }

        bestScore = sample.Score;
        best = sample;
    }

    private static void AppendDevice(StringBuilder sb, WinGameThrottleSample sample, string kind)
    {
        sb.AppendLine($"  score={sample.Score,4} [{kind}] {sample.DeviceName}");
        sb.AppendLine($"    throttle={sample.Throttle:F3} axis={sample.AxisLabel}");
    }

    private static string F3(double value) => value.ToString("F3", CultureInfo.InvariantCulture);

    private static int ScoreDevice(string label)
    {
        var score = 0;
        if (label.Contains("velocity", StringComparison.OrdinalIgnoreCase))
        {
            score += 120;
        }

        if (label.Contains("flightstick", StringComparison.OrdinalIgnoreCase))
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

        if (label.Contains("wheel", StringComparison.OrdinalIgnoreCase))
        {
            score += 80;
        }

        return score;
    }
}
