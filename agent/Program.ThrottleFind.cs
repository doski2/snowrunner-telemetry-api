using System.Buffers.Binary;
using SnowrunnerTelemetryAgent.Input;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent;

internal static partial class Program
{
    private sealed class CorrAcc
    {
        public int N;
        public double Sx, Sxx, Sxy, Min = double.MaxValue, Max = double.MinValue;
        public readonly HashSet<float> Distinct = new();

        public void Add(float x, double y)
        {
            N++;
            Sx += x;
            Sxx += (double)x * x;
            Sxy += x * y;
            Min = Math.Min(Min, x);
            Max = Math.Max(Max, x);
            if (Distinct.Count < 8)
            {
                Distinct.Add(x);
            }
        }
    }

    /// <summary>
    /// Localiza el acelerador del juego en memoria: correlaciona cada f32 del vehículo (y de los
    /// objetos a los que apunta) con el eje crudo del pedal físico. Pisa y suelta el pedal a fondo.
    /// </summary>
    private static int RunThrottleFind(string[] args)
    {
        var seconds = ParseIntArg(args, "--duration=", 30, static v => v is > 3 and < 600);
        var deep = HasArg(args, "--deep");
        var intervalMs = ParseIntArg(args, "--interval=", deep ? 250 : 100, static v => v >= 20);
        var axisIndex = ParseAxisArg(args);

        if (GameSession.TryLoadOffsets(out var offsets) != ExitOk || offsets is null)
        {
            return ExitMemoryFailed;
        }

        var (code, session) = GameSession.TryOpen(offsets);
        if (session is null)
        {
            return code;
        }

        using (session)
        {
            var handle = session.Process.Handle;
            var moduleBase = session.ModuleBase;
            var accs = new Dictionary<string, CorrAcc>();
            double n = 0, sy = 0, syy = 0, rawMin = double.MaxValue, rawMax = double.MinValue;

            Console.WriteLine($"[throttle-find] {seconds} s, eje {"XYZRUV"[axisIndex]}{(deep ? " (profundo)" : "")}: mueve el control a fondo, varias veces.");
            var end = DateTime.UtcNow.AddSeconds(seconds);
            while (DateTime.UtcNow < end)
            {
                var pedal = WinMmJoystickReader.Read();
                var sample = session.ReadActiveSample();
                if (!pedal.Connected || sample is null)
                {
                    Thread.Sleep(intervalMs);
                    continue;
                }

                double y = axisIndex == 3 ? pedal.RawAxis : WinMmJoystickReader.ReadAxes(pedal.JoyId)?[axisIndex] ?? double.NaN;
                if (double.IsNaN(y))
                {
                    Thread.Sleep(intervalMs);
                    continue;
                }

                n++;
                sy += y;
                syy += y * y;
                rawMin = Math.Min(rawMin, y);
                rawMax = Math.Max(rawMax, y);

                var vehicle = GameSession.ParseVehicle(sample);
                var tc = ReadValidPointer(handle, moduleBase + offsets.TruckControlOffset) ?? 0;
                var dl = ReadValidPointer(handle, moduleBase + offsets.DriveLogicOffset) ?? 0;
                foreach (var (label, address, size) in EnumerateBlocks(handle, vehicle, tc, dl, deep))
                {
                    AddBlock(accs, label, handle, address, size, y);
                }

                Thread.Sleep(intervalMs);
            }

            Console.WriteLine($"[throttle-find] ticks={n} eje raw min={rawMin} max={rawMax}");
            if (n < 30 || rawMax - rawMin < 2000)
            {
                Console.WriteLine("[FALLO] pocas muestras o el pedal no se movió lo suficiente.");
                return ExitProbeFailed;
            }

            var varY = (syy / n) - Math.Pow(sy / n, 2);
            var ranked = accs
                .Where(kv => kv.Value.N >= n * 0.9 && kv.Value.Distinct.Count > 3)
                .Select(kv =>
                {
                    var a = kv.Value;
                    var varX = (a.Sxx / a.N) - Math.Pow(a.Sx / a.N, 2);
                    var cov = (a.Sxy / a.N) - ((a.Sx / a.N) * (sy / n));
                    var r = varX > 1e-12 && varY > 0 ? cov / Math.Sqrt(varX * varY) : 0;
                    return (Key: kv.Key, R: r, a.Min, a.Max);
                })
                .OrderByDescending(t => Math.Abs(t.R))
                .Take(20);

            Console.WriteLine("[throttle-find] mejores candidatos (|r| = correlación con el pedal):");
            foreach (var (key, r, min, max) in ranked)
            {
                Console.WriteLine($"  {key,-16} r={r,7:F3}  rango [{min:F3} .. {max:F3}]");
            }

            return ExitOk;
        }
    }

    private static int ParseAxisArg(string[] args)
    {
        foreach (var arg in args)
        {
            if (arg.StartsWith("--axis=", StringComparison.OrdinalIgnoreCase) && arg.Length > 7)
            {
                var idx = "XYZRUV".IndexOf(char.ToUpperInvariant(arg[7]));
                if (idx >= 0)
                {
                    return idx;
                }
            }
        }

        return 3; // R: el acelerador del volante
    }

    /// <summary>Bloques de memoria del vehículo a explorar; con <paramref name="deep"/> también los nietos.</summary>
    private static IEnumerable<(string Label, nint Address, int Size)> EnumerateBlocks(
        nint handle, nint vehicle, nint truckControl, nint driveLogic, bool deep)
    {
        yield return ("veh", vehicle, 0x1000);
        yield return ("tc", truckControl, 0x400);
        yield return ("dl", driveLogic, 0x400);
        var seen = new HashSet<nint> { vehicle, truckControl, driveLogic };
        for (var p = 0; p < 0x400; p += 8)
        {
            if (ReadValidPointer(handle, vehicle + p) is not { } child || !seen.Add(child))
            {
                continue;
            }

            yield return ($"veh+{p:X}->", child, 0x200);
            if (!deep || ProcessMemoryReader.ReadBytes(handle, child, 0x200) is not { } slots)
            {
                continue;
            }

            for (var q = 0; q < 0x200; q += 8)
            {
                var raw = BinaryPrimitives.ReadUInt64LittleEndian(slots.AsSpan(q, 8));
                if (raw is > 0x10000 and < 0x7FFFFFFFFFFF && seen.Add((nint)raw))
                {
                    yield return ($"veh+{p:X}->+{q:X}->", (nint)raw, 0x80);
                }
            }
        }
    }

    private static void AddBlock(
        Dictionary<string, CorrAcc> accs, string prefix, nint handle, nint address, int size, double y)
    {
        if (address == 0 || ProcessMemoryReader.ReadBytes(handle, address, size) is not { } block)
        {
            return;
        }

        for (var off = 0; off + 4 <= size; off += 4)
        {
            var f = BinaryPrimitives.ReadSingleLittleEndian(block.AsSpan(off, 4));
            if (!float.IsFinite(f) || Math.Abs(f) > 1e6f)
            {
                continue;
            }

            var key = $"{prefix}+{off:X}";
            if (!accs.TryGetValue(key, out var acc))
            {
                accs[key] = acc = new CorrAcc();
            }

            acc.Add(f, y);
        }
    }
}
