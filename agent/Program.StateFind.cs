using System.Buffers.Binary;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent;

internal static partial class Program
{
    private const int WheelBlockSize = 0x600;
    private const int MaxWheels = 16;

    /// <summary>
    /// Localiza el giro de cada rueda: correlaciona cada f32 de cada objeto rueda con la velocidad
    /// longitudinal. Hay que conducir variando la velocidad (acelerar y frenar), no a ritmo constante.
    /// </summary>
    private static int RunWheelFind(string[] args)
    {
        var seconds = ParseIntArg(args, "--duration=", 40, static v => v is > 3 and < 600);
        var intervalMs = ParseIntArg(args, "--interval=", 100, static v => v >= 20);

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
            var accs = new Dictionary<string, CorrAcc>();
            double n = 0, sy = 0, syy = 0, yMin = double.MaxValue, yMax = double.MinValue;

            Console.WriteLine($"[wheel-find] {seconds} s: conduce acelerando y frenando (varía la velocidad).");
            var end = DateTime.UtcNow.AddSeconds(seconds);
            while (DateTime.UtcNow < end)
            {
                var sample = session.ReadActiveSample();
                if (sample is null)
                {
                    Thread.Sleep(intervalMs);
                    continue;
                }

                var y = LongitudinalSpeedMs(sample);
                n++;
                sy += y;
                syy += y * y;
                yMin = Math.Min(yMin, y);
                yMax = Math.Max(yMax, y);

                var vehicle = GameSession.ParseVehicle(sample);
                var wheels = ReadWheelPointers(handle, vehicle, offsets.WheelsArrayStart, offsets.WheelsArrayEnd);
                for (var i = 0; i < wheels.Count; i++)
                {
                    AddBlock(accs, $"w{i}", handle, wheels[i], WheelBlockSize, y);
                }

                Thread.Sleep(intervalMs);
            }

            Console.WriteLine($"[wheel-find] ticks={n} velocidad longitudinal min={yMin:F2} max={yMax:F2} m/s");
            var varY = (syy / n) - Math.Pow(sy / n, 2);
            if (n < 30 || yMax - yMin < 1.0 || varY <= 0)
            {
                Console.WriteLine("[FALLO] pocas muestras o la velocidad casi no varió.");
                return ExitProbeFailed;
            }

            // r por (rueda, offset); se agrupa por offset para exigir que TODAS las ruedas lo muestren
            var perOffset = new Dictionary<string, List<(string Wheel, double R, double Min, double Max)>>();
            foreach (var (key, acc) in accs)
            {
                if (acc.N < n * 0.9 || acc.Distinct.Count <= 3)
                {
                    continue;
                }

                var varX = (acc.Sxx / acc.N) - Math.Pow(acc.Sx / acc.N, 2);
                if (varX <= 1e-12)
                {
                    continue;
                }

                var cov = (acc.Sxy / acc.N) - ((acc.Sx / acc.N) * (sy / n));
                var r = cov / Math.Sqrt(varX * varY);
                var split = key.IndexOf('+');
                var wheel = key[..split];
                var off = key[split..];
                if (!perOffset.TryGetValue(off, out var list))
                {
                    perOffset[off] = list = [];
                }

                list.Add((wheel, r, acc.Min, acc.Max));
            }

            var ranked = perOffset
                .Where(kv => kv.Value.Count >= 2)
                .Select(kv => (Off: kv.Key, Items: kv.Value, Score: kv.Value.Min(i => Math.Abs(i.R))))
                .OrderByDescending(t => t.Score)
                .Take(15)
                .ToList();

            Console.WriteLine("[wheel-find] offsets de rueda que siguen la velocidad en TODAS las ruedas (puntuación = |r| mínimo):");
            foreach (var (off, items, score) in ranked)
            {
                var detail = string.Join(" ", items.OrderBy(i => i.Wheel).Select(i => $"{i.Wheel}:{i.R:+0.00;-0.00}"));
                var min = items.Min(i => i.Min);
                var max = items.Max(i => i.Max);
                Console.WriteLine($"  rueda{off,-7} score={score:F3}  rango [{min:F2} .. {max:F2}]  {detail}");
            }

            return ranked.Count > 0 ? ExitOk : ExitProbeFailed;
        }
    }

    /// <summary>
    /// Compara dos estados estables (A y B) de la memoria del vehículo para localizar un interruptor
    /// (diferencial, AWD, reductora, marcha…). Pulsa el control justo cuando se te indique.
    /// </summary>
    private static int RunStateDiff(string[] args)
    {
        var holdMs = ParseIntArg(args, "--hold=", 3000, static v => v >= 500);
        var waitMs = ParseIntArg(args, "--wait=", 8000, static v => v >= 1000);
        var deep = HasArg(args, "--deep");

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
            Console.WriteLine($"[state-diff] capturando estado A ({holdMs / 1000.0:F0} s): no toques nada…");
            var a = CaptureStates(session, offsets, holdMs, deep);
            Console.WriteLine($"[state-diff] >>> CAMBIA AHORA el control (tienes {waitMs / 1000.0:F0} s) y deja el camión quieto.");
            Thread.Sleep(waitMs);
            Console.WriteLine($"[state-diff] capturando estado B ({holdMs / 1000.0:F0} s)…");
            var b = CaptureStates(session, offsets, holdMs, deep);

            var changed = a
                .Where(kv => kv.Value.Count == 1 && b.TryGetValue(kv.Key, out var vb) && vb.Count == 1
                    && kv.Value.First() != vb.First())
                .Select(kv => (Key: kv.Key, A: kv.Value.First(), B: b[kv.Key].First()))
                .OrderBy(t => t.Key, StringComparer.Ordinal)
                .ToList();

            Console.WriteLine($"[state-diff] {changed.Count} campos estables que cambian entre A y B:");
            foreach (var (key, va, vb) in changed.Take(80))
            {
                Console.WriteLine($"  {key,-18} A={Describe(va)}  B={Describe(vb)}");
            }

            return changed.Count > 0 ? ExitOk : ExitProbeFailed;
        }
    }

    private static Dictionary<string, HashSet<uint>> CaptureStates(GameSession session, Config.OffsetsReference offsets, int holdMs, bool deep)
    {
        var handle = session.Process.Handle;
        var values = new Dictionary<string, HashSet<uint>>();
        var end = DateTime.UtcNow.AddMilliseconds(holdMs);
        while (DateTime.UtcNow < end)
        {
            if (session.ReadActiveSample() is { } sample)
            {
                var vehicle = GameSession.ParseVehicle(sample);
                var tc = ReadValidPointer(handle, session.ModuleBase + offsets.TruckControlOffset) ?? 0;
                var dl = ReadValidPointer(handle, session.ModuleBase + offsets.DriveLogicOffset) ?? 0;
                foreach (var (label, address, size) in EnumerateBlocks(handle, vehicle, tc, dl, deep))
                {
                    CaptureBlock(values, label, handle, address, size);
                }
            }

            Thread.Sleep(deep ? 200 : 100);
        }

        return values;
    }

    private static void CaptureBlock(Dictionary<string, HashSet<uint>> values, string prefix, nint handle, nint address, int size)
    {
        if (address == 0 || ProcessMemoryReader.ReadBytes(handle, address, size) is not { } block)
        {
            return;
        }

        for (var off = 0; off + 4 <= size; off += 4)
        {
            var key = $"{prefix}+{off:X}";
            if (!values.TryGetValue(key, out var set))
            {
                values[key] = set = [];
            }

            if (set.Count <= 1)
            {
                set.Add(BinaryPrimitives.ReadUInt32LittleEndian(block.AsSpan(off, 4)));
            }
            else if (set.Count == 2)
            {
                set.Add(uint.MaxValue - 1); // más de un valor: marca de inestable (>1 distintos)
                set.Add(uint.MaxValue - 2);
            }
        }
    }

    private static string Describe(uint raw)
    {
        var f = BitConverter.UInt32BitsToSingle(raw);
        var asFloat = float.IsFinite(f) && Math.Abs(f) is > 1e-6f and < 1e6f ? $" f32={f:G5}" : "";
        return $"{raw,10} (0x{raw:X8}){asFloat}";
    }

    private static double LongitudinalSpeedMs(Models.SpikeSample sample)
    {
        // Eje delantero = columna 0 de la rotación (calibrado en sep-2026); sin rotación, velocidad horizontal
        if (sample.Rotation is { Length: 9 } rot)
        {
            return (sample.VelX * rot[0]) + (sample.VelY * rot[1]) + (sample.VelZ * rot[2]);
        }

        return sample.SpeedKmh / 3.6;
    }

    private static List<nint> ReadWheelPointers(nint handle, nint vehicle, int startOffset, int endOffset)
    {
        var wheels = new List<nint>();
        if (ProcessMemoryReader.ReadUInt64(handle, vehicle + startOffset) is not { } start
            || ProcessMemoryReader.ReadUInt64(handle, vehicle + endOffset) is not { } end
            || end <= start || start < 0x10000)
        {
            return wheels;
        }

        var count = (int)Math.Min((end - start) / 8, MaxWheels);
        for (var i = 0; i < count; i++)
        {
            if (ReadValidPointer(handle, (nint)start + (i * 8)) is { } wheel)
            {
                wheels.Add(wheel);
            }
        }

        return wheels;
    }
}
