using System.Globalization;
using SnowrunnerTelemetryAgent.Havok;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent;

internal static partial class Program
{
    private static int RunFuelDiff(int waitMs)
    {
        if (GameSession.TryLoadOffsets(out var offsets) != ExitOk || offsets is null)
        {
            return ExitMemoryFailed;
        }

        var (code, session) = GameSession.TryOpen(offsets);
        if (code != ExitOk || session is null)
        {
            return code;
        }

        using (session)
        {
            var sample = session.ReadActiveSample();
            if (sample is null)
            {
                return ExitProbeFailed;
            }

            var vehicle = GameSession.ParseVehicle(sample);
            if (FuelReader.ReadAddonPointer(session.Process.Handle, vehicle) is not { } addon)
            {
                Console.WriteLine("[fuel-diff] addon null");
                return ExitProbeFailed;
            }

            var child128 = ReadValidPointer(session.Process.Handle, addon + 0x128);
            var child130 = ReadValidPointer(session.Process.Handle, addon + 0x130);

            var beforeAddon = SnapshotAddon(session.Process.Handle, addon);
            var beforeVehicle = SnapshotBlock(session.Process.Handle, vehicle, "veh");
            var before128 = child128 is { } c128 ? SnapshotBlock(session.Process.Handle, c128, "c128") : [];
            var before130 = child130 is { } c130 ? SnapshotBlock(session.Process.Handle, c130, "c130") : [];

            PrintFuelWatch("before", session.Process.Handle, addon, vehicle, child128, child130);

            Thread.Sleep(waitMs);

            var afterAddon = SnapshotAddon(session.Process.Handle, addon);
            var afterVehicle = SnapshotBlock(session.Process.Handle, vehicle, "veh");
            var after128 = child128 is { } c128b ? SnapshotBlock(session.Process.Handle, c128b, "c128") : [];
            var after130 = child130 is { } c130b ? SnapshotBlock(session.Process.Handle, c130b, "c130") : [];

            PrintFuelWatch("after ", session.Process.Handle, addon, vehicle, child128, child130);

            var changes = PrintChanges("addon", beforeAddon, afterAddon)
                + PrintChanges("c128", before128, after128)
                + PrintChanges("c130", before130, after130)
                + PrintChanges("veh", beforeVehicle, afterVehicle);

            Console.WriteLine($"[fuel-diff] changes={changes} wait={waitMs}ms speed={sample.SpeedKmh}");
            return ExitOk;
        }
    }

    private static int PrintChanges(
        string label,
        Dictionary<string, float> before,
        Dictionary<string, float> after)
    {
        var changes = 0;
        foreach (var key in before.Keys.Union(after.Keys).OrderBy(static k => k))
        {
            var a = before.GetValueOrDefault(key);
            var b = after.GetValueOrDefault(key);
            if (Math.Abs(a - b) > 0.001f)
            {
                changes++;
                Console.WriteLine(
                    $"[fuel-diff] {label}.{key}: {a.ToString("F3", CultureInfo.InvariantCulture)} -> {b.ToString("F3", CultureInfo.InvariantCulture)}");
            }
        }

        return changes;
    }

    private static Dictionary<string, float> SnapshotBlock(nint handle, nint basePtr, string prefix)
    {
        var map = new Dictionary<string, float>();
        for (var off = 0x0; off <= 0xA00; off += 4)
        {
            var value = ProcessMemoryReader.ReadFloat32(handle, basePtr + off);
            if (value is { } v && !float.IsNaN(v) && v is >= 0f and <= 500f)
            {
                map[$"{prefix}.f32+{off:X}"] = v;
            }
        }

        for (var off = 0x0; off <= 0xA00; off += 2)
        {
            var value = ProcessMemoryReader.ReadUInt16(handle, basePtr + off);
            if (value is > 0 and <= 500)
            {
                map[$"{prefix}.u16+{off:X}"] = value.Value;
            }
        }

        return map;
    }

    private static Dictionary<string, float> SnapshotAddon(nint handle, nint addon)
    {
        var map = new Dictionary<string, float>();
        for (var off = 0x0; off <= 0x900; off += 4)
        {
            var value = ProcessMemoryReader.ReadFloat32(handle, addon + off);
            if (value is { } v && !float.IsNaN(v) && v is >= 0f and <= 500f)
            {
                map[$"f32+{off:X}"] = v;
            }
        }

        for (var off = 0x0; off <= 0x900; off += 2)
        {
            var value = ProcessMemoryReader.ReadUInt16(handle, addon + off);
            if (value is > 0 and <= 500)
            {
                map[$"u16+{off:X}"] = value.Value;
            }
        }

        return map;
    }

    private static void PrintFuelWatch(
        string label,
        nint handle,
        nint addon,
        nint vehicle,
        nint? child128,
        nint? child130)
    {
        var parts = new List<string>
        {
            Fmt("addon+868", ProcessMemoryReader.ReadFloat32(handle, addon + 0x868)),
            Fmt("addon+258", ProcessMemoryReader.ReadFloat32(handle, addon + 0x258)),
            Fmt("addon+008", ProcessMemoryReader.ReadFloat32(handle, addon + 0x8)),
            Fmt("veh+728", ProcessMemoryReader.ReadFloat32(handle, vehicle + 0x728)),
            Fmt("veh+758", ProcessMemoryReader.ReadFloat32(handle, vehicle + 0x758)),
            Fmt("veh+294", ProcessMemoryReader.ReadFloat32(handle, vehicle + 0x294)),
        };

        if (child130 is { } c130)
        {
            parts.Add(Fmt("130+05C", ProcessMemoryReader.ReadFloat32(handle, c130 + 0x5C)));
            parts.Add(Fmt("130+4F4", ProcessMemoryReader.ReadFloat32(handle, c130 + 0x4F4)));
            parts.Add(Fmt("130+06C", ProcessMemoryReader.ReadFloat32(handle, c130 + 0x6C)));
            parts.Add(Fmt("130+1D0", ProcessMemoryReader.ReadFloat32(handle, c130 + 0x1D0)));
        }

        if (child128 is { } c128)
        {
            var u16_100 = ProcessMemoryReader.ReadUInt16(handle, c128 + 0x100);
            parts.Add(u16_100 is > 0 and <= 500
                ? $"128+u16+100={u16_100.Value.ToString(CultureInfo.InvariantCulture)}L?"
                : "128+u16+100=null");
            parts.Add(Fmt("128+f32+100", ProcessMemoryReader.ReadFloat32(handle, c128 + 0x100)));
            parts.Add(Fmt("128+070", ProcessMemoryReader.ReadFloat32(handle, c128 + 0x70)));
            parts.Add(Fmt("128+0EC", ProcessMemoryReader.ReadFloat32(handle, c128 + 0xEC)));
            parts.Add(Fmt("128+040", ProcessMemoryReader.ReadFloat32(handle, c128 + 0x40)));
            parts.Add(Fmt("128+1F8", ProcessMemoryReader.ReadFloat32(handle, c128 + 0x1F8)));
        }

        Console.WriteLine($"[fuel-diff] watch {label}: {string.Join("  ", parts)}");
    }

    private static string Fmt(string name, float? value) =>
        value is { } v
            ? $"{name}={v.ToString("F4", CultureInfo.InvariantCulture)}"
            : $"{name}=null";
}
