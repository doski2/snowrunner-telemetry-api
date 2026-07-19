using System.Globalization;
using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent.Havok;

internal sealed record WheelTerrainSnapshot(
    string TerrainKind,
    string SurfaceWheel,
    string MudGradeLabel,
    int MudGrade,
    int WheelCount,
    double WheelGrip,
    double SurfaceAvg,
    double ContactAvg,
    double SurfaceDeformAvg,
    double GripMin,
    double GripMax,
    double ContactMin,
    double ContactMax,
    string WheelKinds,
    string TerrainSource);

/// <summary>Port fiel de memoria_havok.read_wheel_terrain / classify_terrain_from_wheels.</summary>
internal static class WheelTerrainReader
{
    private const int OffWheelGripAlt1 = 0x2F4;
    private const int OffWheelGripAlt2 = 0x2F8;
    private const int OffWheelContactAlt = 0x2E8;
    private const float SurfacePositiveThreshold = 0.25f;
    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    public static WheelTerrainSnapshot? Read(
        nint processHandle,
        nint vehicle,
        OffsetsReference offsets,
        string vehicleId,
        float? velY = null)
    {
        if (!TryReadWheelSamples(processHandle, vehicle, offsets, out var samples) || samples.Count == 0)
        {
            return null;
        }

        var classified = ClassifyTerrainFromWheels(samples);
        var grips = samples.Select(static s => s.Grip).ToList();
        var contacts = samples.Select(static s => s.Contact).ToList();
        var deforms = samples.Select(static s => s.Deform).ToList();
        var grade = ClassifyMudGrade(
            classified.TerrainKind,
            Average(grips),
            contacts.Count > 0 ? Average(contacts) : 0f,
            Average(deforms),
            velY);

        var ambiguous = samples.TrueForAll(static s =>
            s.Deform < -0.5f && s.Contact >= 0.95f && s.Grip >= 0.9f);

        return new WheelTerrainSnapshot(
            classified.TerrainKind,
            classified.SurfaceWheel,
            grade.Label,
            grade.Grade,
            samples.Count,
            Round3(classified.GripAvg),
            Round3(classified.SurfaceAvg),
            Round3(contacts.Count > 0 ? Average(contacts) : 0f),
            Round3(Average(deforms)),
            Round3(Min(grips)),
            Round3(Max(grips)),
            Round3(contacts.Count > 0 ? Min(contacts) : 0f),
            Round3(contacts.Count > 0 ? Max(contacts) : 0f),
            classified.WheelKinds,
            ambiguous
                ? $"wheel_model:{vehicleId};ambiguous_bandit_like"
                : $"wheel_model:{vehicleId}");
    }

    public static void DebugPrint(
        nint processHandle,
        nint vehicle,
        OffsetsReference offsets,
        string vehicleId)
    {
        Console.WriteLine($"[wheel-debug] vehicle={vehicleId} veh=0x{vehicle:X}");
        if (!TryReadWheelPointers(processHandle, vehicle, offsets, out var wheelBegin, out var wheelEnd))
        {
            Console.WriteLine("[wheel-debug] sin array de ruedas (+200/+208)");
            return;
        }

        Console.WriteLine($"[wheel-debug] array 0x{wheelBegin:X}..0x{wheelEnd:X}");
        var index = 0;
        for (var cursor = wheelBegin; cursor < wheelEnd; cursor += sizeof(ulong))
        {
            if (ReadPointer(processHandle, cursor) is not { } wheel)
            {
                continue;
            }

            var sample = ReadWheelSample(processHandle, wheel, offsets);
            if (sample is null)
            {
                continue;
            }

            var rawFc = ReadF32(processHandle, wheel + offsets.WheelGripOffset);
            var rawF8 = ReadF32(processHandle, wheel + OffWheelGripAlt2);
            var rawF4 = ReadF32(processHandle, wheel + OffWheelGripAlt1);
            var rawEc = ReadF32(processHandle, wheel + offsets.WheelContactOffset);
            var rawE8 = ReadF32(processHandle, wheel + OffWheelContactAlt);
            var effFrom = sample.SurfaceB4 > SurfacePositiveThreshold ? "2B4" : "2EC";
            Console.WriteLine(
                $"[wheel-debug]  #{index} wheel=0x{wheel:X} " +
                $"grip={Fmt(sample.Grip)} (2FC={Fmt(rawFc)} 2F8={Fmt(rawF8)} 2F4={Fmt(rawF4)}) " +
                $"surface={Fmt(sample.SurfaceB4)} contact={Fmt(sample.Contact)} (2EC={Fmt(rawEc)} 2E8={Fmt(rawE8)}) " +
                $"eff={sample.EffectiveSurface:F3}<-{effFrom} kind={sample.Kind}");
            index++;
        }

        var snap = Read(processHandle, vehicle, offsets, vehicleId);
        if (snap is null)
        {
            Console.WriteLine("[wheel-debug] Read -> null");
            return;
        }

        Console.WriteLine(
            $"[wheel-debug] terrain_kind={snap.TerrainKind} surface_wheel={snap.SurfaceWheel} " +
            $"mud_grade={snap.MudGrade} ({snap.MudGradeLabel}) wheel_grip={snap.WheelGrip.ToString(Inv)} " +
            $"surface_avg={snap.SurfaceAvg.ToString(Inv)} contact_avg={snap.ContactAvg.ToString(Inv)} " +
            $"deform_avg={snap.SurfaceDeformAvg.ToString(Inv)} kinds={snap.WheelKinds} wheels={snap.WheelCount}");
        if (snap.TerrainSource.Contains("ambiguous", StringComparison.Ordinal))
        {
            Console.WriteLine(
                "[wheel-debug] AVISO: +2B4 muy negativo y +2EC/+2FC ~1.0 — Havok no separa barro/asfalto en este camion.");
            Console.WriteLine(
                "[wheel-debug]        Compara en el mismo sitio: python grabar_ce.py --probe y scan_wheel_substance.py --save <tag>");
        }
    }

    private sealed record WheelSample(
        float Grip,
        float SurfaceB4,
        float Contact,
        float Deform,
        float EffectiveSurface,
        string Kind);

    private sealed record TerrainClassified(
        string TerrainKind,
        string SurfaceWheel,
        float GripAvg,
        float SurfaceAvg,
        string WheelKinds);

    private static bool TryReadWheelSamples(
        nint processHandle,
        nint vehicle,
        OffsetsReference offsets,
        out List<WheelSample> samples)
    {
        samples = [];
        if (!TryReadWheelPointers(processHandle, vehicle, offsets, out var wheelBegin, out var wheelEnd))
        {
            return false;
        }

        for (var cursor = wheelBegin; cursor < wheelEnd; cursor += sizeof(ulong))
        {
            if (ReadPointer(processHandle, cursor) is not { } wheel)
            {
                continue;
            }

            if (ReadWheelSample(processHandle, wheel, offsets) is { } sample)
            {
                samples.Add(sample);
            }
        }

        return samples.Count > 0;
    }

    private static bool TryReadWheelPointers(
        nint processHandle,
        nint vehicle,
        OffsetsReference offsets,
        out nint wheelBegin,
        out nint wheelEnd)
    {
        wheelBegin = default;
        wheelEnd = default;
        if (ReadPointer(processHandle, vehicle + offsets.WheelsArrayStart) is not { } begin
            || ReadPointer(processHandle, vehicle + offsets.WheelsArrayEnd) is not { } end
            || end <= begin)
        {
            return false;
        }

        wheelBegin = begin;
        wheelEnd = end;
        return true;
    }

    private static WheelSample? ReadWheelSample(nint processHandle, nint wheel, OffsetsReference offsets)
    {
        var grip = ReadF32(processHandle, wheel + offsets.WheelGripOffset);
        var surfaceB4 = ReadF32(processHandle, wheel + offsets.WheelSurfaceOffset);
        var contactEc = ReadF32(processHandle, wheel + offsets.WheelContactOffset);
        if (grip is null || (surfaceB4 is null && contactEc is null))
        {
            return null;
        }

        var sb = surfaceB4 ?? 0f;
        var contact = contactEc ?? 0f;
        var effectiveSurface = EffectiveSurface(sb, contact);
        var kind = ClassifyWheelContact(grip.Value, effectiveSurface, sb);
        return new WheelSample(grip.Value, sb, contact, sb, effectiveSurface, kind);
    }

    private static float EffectiveSurface(float surfaceB4, float contactEc) =>
        surfaceB4 > SurfacePositiveThreshold ? surfaceB4 : contactEc;

    private static string ClassifyWheelContact(float grip, float surface, float deform)
    {
        if (grip < 0.06f && surface > 0.68f)
        {
            return "ice";
        }

        if (deform > 0.55f && grip < 0.45f && surface > 0.55f)
        {
            return "snow";
        }

        if ((grip > 0.45f && surface > 0.30f) || (surface > 0.68f && grip > 0.12f))
        {
            return "hard";
        }

        if (grip < 0.25f || (surface < 0.62f && grip < 0.40f))
        {
            return "mud";
        }

        return "soft";
    }

    private static TerrainClassified ClassifyTerrainFromWheels(IReadOnlyList<WheelSample> samples)
    {
        if (samples.Count == 0)
        {
            return new TerrainClassified("unknown", "", 0f, 0f, "");
        }

        var kinds = samples.Select(static s => s.Kind).ToList();
        var (terrainKind, surfaceWheel, _) = ResolveDominantKind(kinds);
        return new TerrainClassified(
            terrainKind,
            surfaceWheel,
            Average(samples.Select(static s => s.Grip).ToList()),
            Average(samples.Select(static s => s.EffectiveSurface).ToList()),
            string.Join('|', kinds));
    }

    private static (string TerrainKind, string SurfaceWheel, bool WheelDisagreement) ResolveDominantKind(
        IReadOnlyList<string> kinds)
    {
        if (kinds.Count == 0)
        {
            return ("unknown", "", false);
        }

        var counts = kinds
            .GroupBy(static k => k, StringComparer.Ordinal)
            .ToDictionary(static g => g.Key, static g => g.Count(), StringComparer.Ordinal);
        if (counts.Count == 1)
        {
            var only = kinds[0];
            return (only, only, false);
        }

        var top = counts.MaxBy(static kv => kv.Value);
        if (top.Value > kinds.Count / 2)
        {
            return (top.Key, top.Key, counts.Count > 1);
        }

        return ("mixed", "mixed", true);
    }

    private static (int Grade, string Label) ClassifyMudGrade(
        string terrainKind,
        float gripAvg,
        float contactAvg,
        float deformAvg,
        float? velY)
    {
        var kind = (terrainKind ?? "").Trim().ToLowerInvariant();
        return kind switch
        {
            "snow" => gripAvg < 0.15f ? (5, "snow_loose") : (5, "snow_packed"),
            "ice" => (6, "ice"),
            "hard" => (0, "dry_hard"),
            "soft" => (1, "soft_dirt"),
            "mud" or "mixed" => ClassifyMudOrMixed(gripAvg, contactAvg, deformAvg, velY ?? 0f),
            _ => (0, "dry_hard"),
        };
    }

    private static (int Grade, string Label) ClassifyMudOrMixed(
        float gripAvg,
        float contactAvg,
        float deformAvg,
        float velY)
    {
        if (velY < -0.35f && contactAvg >= 0.48f)
        {
            return (4, "water_ford");
        }

        if (gripAvg < 0.05f && contactAvg < 0.42f)
        {
            return (3, "mud_deep");
        }

        if (deformAvg < -0.10f && gripAvg < 0.12f)
        {
            return (3, "mud_deep");
        }

        if (gripAvg < 0.25f && contactAvg < 0.52f)
        {
            return (2, "mud_light");
        }

        if (gripAvg < 0.40f)
        {
            return (2, "mud_light");
        }

        return (1, "soft_dirt");
    }

    private static float? ReadF32(nint processHandle, nint address)
    {
        var value = ProcessMemoryReader.ReadFloat32(processHandle, address);
        if (value is null || float.IsNaN(value.Value) || Math.Abs(value.Value) > 1e6f)
        {
            return null;
        }

        return value;
    }

    private static nint? ReadPointer(nint processHandle, nint address)
    {
        var ptr = ProcessMemoryReader.ReadUInt64(processHandle, address);
        return ptr is > 0x10000 and < 0x7FFFFFFFFFFF ? (nint)ptr.Value : null;
    }

    private static float Average(IReadOnlyList<float> values)
    {
        var sum = 0f;
        foreach (var value in values)
        {
            sum += value;
        }

        return sum / values.Count;
    }

    private static float Min(IReadOnlyList<float> values)
    {
        var min = values[0];
        for (var i = 1; i < values.Count; i++)
        {
            min = Math.Min(min, values[i]);
        }

        return min;
    }

    private static float Max(IReadOnlyList<float> values)
    {
        var max = values[0];
        for (var i = 1; i < values.Count; i++)
        {
            max = Math.Max(max, values[i]);
        }

        return max;
    }

    private static double Round3(float value) => Math.Round(value, 3);

    private static string Fmt(float? value) =>
        value is null ? "—" : value.Value.ToString("F3", Inv);
}
