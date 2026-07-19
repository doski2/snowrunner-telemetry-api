using System.Globalization;
using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent.Havok;

public static class ThrottleResolver
{
    private static readonly int[] CommonU8Offsets =
    [
        0x0C8, 0x5E8, 0x17C, 0x0D8, 0x0E0, 0x108, 0x184, 0x100, 0x168,
    ];

    private const double StuckBandMin = 0.35;
    private const double StuckBandMax = 0.75;

    private static readonly Dictionary<string, DriveFieldSpec> SessionCache = new(StringComparer.Ordinal);

    public static void ClearCache() => SessionCache.Clear();

    public static (string Value, string Source) ResolveThrottleInput(
        nint processHandle,
        nint moduleBase,
        nint vehicle,
        string vehicleId,
        OffsetsReference offsets,
        double speedKmh = 0)
    {
        if (!string.IsNullOrEmpty(vehicleId) && SessionCache.TryGetValue(vehicleId, out var cached))
        {
            var cachedValue = ReadDriveField(processHandle, moduleBase, vehicle, cached, offsets);
            if (IsPlausible(cachedValue, speedKmh))
            {
                return (cachedValue, "cache");
            }

            SessionCache.Remove(vehicleId);
        }

        if (!string.IsNullOrEmpty(vehicleId)
            && offsets.PerVehicleThrottle.TryGetValue(vehicleId, out var perVehicle)
            && TryRead(processHandle, moduleBase, vehicle, perVehicle, offsets, speedKmh) is { } pv)
        {
            SessionCache[vehicleId] = perVehicle;
            return (pv, "per_vehicle");
        }

        if (offsets.DefaultThrottleInput is { } global
            && TryRead(processHandle, moduleBase, vehicle, global, offsets, speedKmh) is { } gv)
        {
            Cache(vehicleId, global);
            return (gv, "global");
        }

        if (ProbeSpec(processHandle, moduleBase, vehicle, offsets) is { } probed
            && TryRead(processHandle, moduleBase, vehicle, probed, offsets, speedKmh) is { } av)
        {
            Cache(vehicleId, probed);
            return (av, "auto_probe");
        }

        return ("", "none");
    }

    private static void Cache(string vehicleId, DriveFieldSpec spec)
    {
        if (!string.IsNullOrEmpty(vehicleId))
        {
            SessionCache[vehicleId] = spec;
        }
    }

    private static string? TryRead(
        nint processHandle,
        nint moduleBase,
        nint vehicle,
        DriveFieldSpec spec,
        OffsetsReference offsets,
        double speedKmh,
        nint? knownBase = null)
    {
        if (!IsReadable(processHandle, moduleBase, vehicle, spec, offsets, knownBase))
        {
            return null;
        }

        var value = ReadDriveField(processHandle, moduleBase, vehicle, spec, offsets, knownBase);
        return IsPlausible(value, speedKmh) ? value : null;
    }

    private static DriveFieldSpec? ProbeSpec(
        nint processHandle,
        nint moduleBase,
        nint vehicle,
        OffsetsReference offsets)
    {
        DriveFieldSpec? best = null;
        var bestNorm = double.MaxValue;

        foreach (var target in ScanTargets(processHandle, moduleBase, vehicle, offsets))
        {
            if (!target.Label.StartsWith("tc+", StringComparison.OrdinalIgnoreCase)
                || target.Label.Contains("vehicle", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            foreach (var off in CommonU8Offsets)
            {
                if (off >= target.ScanEnd)
                {
                    continue;
                }

                var raw = ProcessMemoryReader.ReadUInt8(processHandle, target.Pointer + off);
                if (raw is null)
                {
                    continue;
                }

                var norm = raw.Value / 255.0;
                if (IsStuckBand(norm) || norm > 0.15 || norm >= bestNorm)
                {
                    continue;
                }

                var spec = new DriveFieldSpec
                {
                    Base = target.Label,
                    Offset = $"+0x{off:X3}",
                    Kind = "u8",
                };

                if (!IsReadable(processHandle, moduleBase, vehicle, spec, offsets, target.Pointer))
                {
                    continue;
                }

                best = spec;
                bestNorm = norm;
            }
        }

        return best;
    }

    private static bool IsPlausible(string value, double speedKmh)
    {
        if (string.IsNullOrEmpty(value)
            || !double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed)
            || IsStuckBand(parsed))
        {
            return false;
        }

        // Parado con gas suelto: rechazar lecturas altas del candidato global equivocado.
        return speedKmh >= 1.0 || parsed <= 0.15;
    }

    private static bool IsStuckBand(double norm) => norm is > StuckBandMin and < StuckBandMax;

    private static bool IsReadable(
        nint processHandle,
        nint moduleBase,
        nint vehicle,
        DriveFieldSpec spec,
        OffsetsReference offsets,
        nint? knownBase = null)
    {
        var basePtr = knownBase ?? ResolveBase(processHandle, moduleBase, vehicle, spec.Base, offsets);
        if (basePtr is null || OffsetsReference.ParseHex(spec.Offset) is not { } offset)
        {
            return false;
        }

        var addr = basePtr.Value + offset;
        return string.Equals(spec.Kind, "u8", StringComparison.OrdinalIgnoreCase)
            ? ProcessMemoryReader.ReadUInt8(processHandle, addr) is not null
            : ProcessMemoryReader.ReadFloat32(processHandle, addr) is not null;
    }

    private static string ReadDriveField(
        nint processHandle,
        nint moduleBase,
        nint vehicle,
        DriveFieldSpec spec,
        OffsetsReference offsets,
        nint? knownBase = null)
    {
        var basePtr = knownBase ?? ResolveBase(processHandle, moduleBase, vehicle, spec.Base, offsets);
        return basePtr is null
            ? ""
            : FieldReader.ReadFieldAt(processHandle, basePtr.Value, spec.Offset, spec.Kind);
    }

    private static nint? ResolveBase(
        nint processHandle,
        nint moduleBase,
        nint vehicle,
        string baseName,
        OffsetsReference offsets)
    {
        if (string.Equals(baseName, "vehicle", StringComparison.OrdinalIgnoreCase))
        {
            return vehicle;
        }

        if (string.Equals(baseName, "truck_control", StringComparison.OrdinalIgnoreCase))
        {
            return ReadSingleton(processHandle, moduleBase, offsets.TruckControlOffset);
        }

        if (string.Equals(baseName, "drive_logic", StringComparison.OrdinalIgnoreCase))
        {
            return ReadSingleton(processHandle, moduleBase, offsets.DriveLogicOffset);
        }

        if (!OffsetPatterns.TryParseChildBase(baseName, out var prefix, out var childOffset))
        {
            return null;
        }

        var parentOffset = string.Equals(prefix, "dl", StringComparison.OrdinalIgnoreCase)
            ? offsets.DriveLogicOffset
            : offsets.TruckControlOffset;
        var parent = ReadSingleton(processHandle, moduleBase, parentOffset);
        if (parent is null)
        {
            return null;
        }

        var child = ProcessMemoryReader.ReadUInt64(processHandle, parent.Value + childOffset);
        return child is > 0x10000 ? (nint)child.Value : null;
    }

    private static nint? ReadSingleton(nint processHandle, nint moduleBase, int singletonOffset)
    {
        var ptr = ProcessMemoryReader.ReadUInt64(processHandle, moduleBase + singletonOffset);
        return ptr is > 0x10000 ? (nint)ptr.Value : null;
    }

    private static IEnumerable<ScanTarget> ScanTargets(
        nint processHandle,
        nint moduleBase,
        nint vehicle,
        OffsetsReference offsets)
    {
        var seen = new HashSet<nint>();

        var tc = ProcessMemoryReader.ReadUInt64(processHandle, moduleBase + offsets.TruckControlOffset);
        if (tc is > 0x10000)
        {
            foreach (var t in YieldTarget(seen, "truck_control", (nint)tc.Value, 0x800))
            {
                yield return t;
            }

            for (var off = 0; off < 0x200; off += 8)
            {
                var child = ProcessMemoryReader.ReadUInt64(processHandle, (nint)tc.Value + off);
                if (child is not > 0x10000)
                {
                    continue;
                }

                var label = off == 0x8 ? "tc+008→vehicle" : $"tc+{off:X3}";
                foreach (var t in YieldTarget(seen, label, (nint)child.Value, 0x600))
                {
                    yield return t;
                }
            }
        }

        var dl = ProcessMemoryReader.ReadUInt64(processHandle, moduleBase + offsets.DriveLogicOffset);
        if (dl is > 0x10000)
        {
            foreach (var t in YieldTarget(seen, "drive_logic", (nint)dl.Value, 0x400))
            {
                yield return t;
            }
        }

        if (vehicle > 0x10000)
        {
            foreach (var t in YieldTarget(seen, "vehicle", vehicle, 0xC00))
            {
                yield return t;
            }
        }
    }

    private static IEnumerable<ScanTarget> YieldTarget(HashSet<nint> seen, string label, nint pointer, int scanEnd)
    {
        if (seen.Add(pointer))
        {
            yield return new ScanTarget(label, pointer, scanEnd);
        }
    }

    private sealed record ScanTarget(string Label, nint Pointer, int ScanEnd);
}
