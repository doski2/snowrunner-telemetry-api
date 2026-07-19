using System.Globalization;
using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent.Havok;

internal sealed record FuelSnapshot(double? Liters, int? CapacityLiters, string Source);

internal sealed record FuelDisplay(double? Pct, double? Liters, int? CapacityLiters, string Source);

internal static class FuelReader
{
    private const int AddonManagerOffset = 0x48;
    private const float StaleOutlierGap = 0.05f;
    private const double StaleLitersGap = 15.0;
    private const double LowOutlierRatio = 0.45;

    private static readonly string[] PreferredRepostajeSources =
    [
        "ui130_06c",
        "ui130_070",
        "ui128_040",
        "addon_f32",
        "addon_u16",
    ];

    private static readonly string[] PreferredLiveSources =
    [
        "ui130_05c",
        "ui130_4f4",
        "ui128_0ec",
        "ui130_520",
        "ui128_1f8",
        "veh_pct",
        "addon_f32",
    ];

    private static readonly int[] AddonPointerOffsets = [0x48, 0x58, 0x70];

    public static FuelSnapshot ReadSnapshot(
        nint processHandle,
        nint moduleBase,
        OffsetsReference offsets,
        nint vehicle)
    {
        var capacity = offsets.FuelDefaultCapacityLiters;
        foreach (var scan in offsets.FuelPointerScans)
        {
            if (FuelPointerChainReader.TryRead(processHandle, moduleBase, scan, capacity) is { } chainRead)
            {
                return new FuelSnapshot(chainRead.Liters, capacity, chainRead.Label);
            }
        }

        foreach (var addonOff in AddonPointerOffsets)
        {
            if (ReadPointer(processHandle, vehicle + addonOff) is not { } addon)
            {
                continue;
            }

            if (TryLiveFuelSnapshot(processHandle, vehicle, addon, offsets) is { } liveSnapshot)
            {
                return liveSnapshot;
            }

            if (TrySnapshot(processHandle, addon, offsets) is { } snapshot)
            {
                return snapshot;
            }
        }

        if (ReadFuelFromSingleton(processHandle, moduleBase + offsets.UiFuelSingletonOffset, offsets, vehicle)
            is { } singletonSnapshot)
        {
            return singletonSnapshot;
        }

        return new FuelSnapshot(null, null, "none");
    }

    public static double? ReadFuelPct(
        nint processHandle,
        nint moduleBase,
        OffsetsReference offsets,
        nint vehicle,
        double speedKmh,
        double throttleInput,
        bool engineOn) =>
        ReadFuelDisplay(processHandle, moduleBase, offsets, vehicle, speedKmh, throttleInput, engineOn).Pct;

    public static FuelDisplay ReadFuelDisplay(
        nint processHandle,
        nint moduleBase,
        OffsetsReference offsets,
        nint vehicle,
        double speedKmh,
        double throttleInput,
        bool engineOn)
    {
        var snapshot = ReadSnapshot(processHandle, moduleBase, offsets, vehicle);
        if (snapshot.Liters is null || snapshot.CapacityLiters is null or <= 0)
        {
            return new FuelDisplay(null, null, snapshot.CapacityLiters, snapshot.Source);
        }

        var capacity = snapshot.CapacityLiters.Value;
        var liters = FuelSessionTracker.Track(
            snapshot.Liters,
            capacity,
            speedKmh,
            throttleInput,
            engineOn);
        var source = snapshot.Source;
        if (Math.Abs(liters - snapshot.Liters.Value) > 0.05)
        {
            source = $"{snapshot.Source}+tracked";
        }

        var pct = NormalizePct(100.0 * liters / capacity);
        return new FuelDisplay(pct, liters, capacity, source);
    }

    public static void DebugPrint(
        nint processHandle,
        nint moduleBase,
        OffsetsReference offsets,
        nint vehicle,
        double speedKmh,
        double throttleInput,
        bool engineOn)
    {
        Console.WriteLine($"[fuel-debug] vehicle=0x{vehicle:X}");

        foreach (var scan in offsets.FuelPointerScans)
        {
            Console.WriteLine(FuelPointerChainReader.DebugLine(processHandle, moduleBase, scan));
        }

        foreach (var addonOff in AddonPointerOffsets)
        {
            if (ReadPointer(processHandle, vehicle + addonOff) is not { } addon)
            {
                continue;
            }

            Console.WriteLine($"[fuel-debug] addon veh+{addonOff:X} = 0x{addon:X}");
            var liveF32 = ProcessMemoryReader.ReadFloat32(processHandle, addon + offsets.FuelLitersLiveF32Offset);
            var liveU16 = ProcessMemoryReader.ReadUInt16(processHandle, addon + offsets.FuelLitersLiveU16Offset);
            var vehPct = ProcessMemoryReader.ReadFloat32(processHandle, vehicle + offsets.FuelPctVehicleOffset);
            var vehLit = ProcessMemoryReader.ReadFloat32(processHandle, vehicle + offsets.FuelLitersVehicleOffset);
            var addonPct868 = ProcessMemoryReader.ReadFloat32(processHandle, addon + offsets.FuelPctAddonDirectOffset);
            Console.WriteLine(
                $"[fuel-debug]   live f32+{offsets.FuelLitersLiveF32Offset:X}={Format(liveF32)} L?"
                + $" u16+{offsets.FuelLitersLiveU16Offset:X}={liveU16?.ToString(CultureInfo.InvariantCulture) ?? "null"}"
                + $" veh+{offsets.FuelPctVehicleOffset:X}={Format(vehPct)} pct?"
                + $" veh+{offsets.FuelLitersVehicleOffset:X}={Format(vehLit)} L?"
                + $" addon+{offsets.FuelPctAddonDirectOffset:X}={Format(addonPct868)} pct?");

            foreach (var probe in BuildConsumeProbes(offsets).Concat(BuildRepostajeProbes(offsets)))
            {
                if (ReadPointer(processHandle, addon + probe.TankPtrOffset) is not { } child)
                {
                    Console.WriteLine(
                        $"[fuel-debug]   {probe.Tag}: child null (addon+{probe.TankPtrOffset:X})");
                    continue;
                }

                var frac = ProcessMemoryReader.ReadFloat32(processHandle, child + probe.PctOffset);
                Console.WriteLine(
                    $"[fuel-debug]   {probe.Tag}: child+{probe.PctOffset:X} f32={Format(frac)}"
                    + (IsValidFuelFraction(frac) ? " OK" : ""));
            }
        }

        var snapshot = ReadSnapshot(processHandle, moduleBase, offsets, vehicle);
        var pct = ReadFuelPct(processHandle, moduleBase, offsets, vehicle, speedKmh, throttleInput, engineOn);
        Console.WriteLine(
            $"[fuel-debug] snapshot={snapshot.Source} liters={Format(snapshot.Liters)}"
            + $" cap={snapshot.CapacityLiters?.ToString(CultureInfo.InvariantCulture) ?? "null"}");
        Console.WriteLine($"[fuel-debug] mode tracker last consume/repostaje (see picks above)");
        Console.WriteLine(
            pct is null
                ? "[fuel-debug] ReadFuelPct -> null"
                : $"[fuel-debug] ReadFuelPct -> {pct.Value.ToString(CultureInfo.InvariantCulture)}%");
    }

    internal static nint? ReadAddonPointer(nint processHandle, nint vehicle) =>
        ReadPointer(processHandle, vehicle + AddonManagerOffset);

    private readonly record struct FuelUiProbe(int TankPtrOffset, int PctOffset, string Tag);

    private static IEnumerable<FuelUiProbe> BuildConsumeProbes(OffsetsReference offsets)
    {
        yield return new(offsets.FuelConsumeTankPtrOffset, offsets.FuelConsumePctF32Offset, "ui130_4f4");
        yield return new(offsets.FuelConsumeTankPtrOffset, offsets.FuelConsumePctF32AltOffset, "ui130_520");
        yield return new(offsets.FuelConsumeTankPtrAltOffset, offsets.FuelConsumePctF32Alt2Offset, "ui128_1f8");
        yield return new(offsets.FuelConsumeTankPtrAltOffset, offsets.FuelConsumePctF32Alt5Offset, "ui128_0ec");
        yield return new(offsets.FuelConsumeTankPtrOffset, offsets.FuelConsumePctF32Alt4Offset, "ui130_05c");
    }

    private static IEnumerable<FuelUiProbe> BuildRepostajeProbes(OffsetsReference offsets)
    {
        yield return new(offsets.FuelUiTankPtrOffset, offsets.FuelPctF32Offset, "ui128_040");
        yield return new(offsets.FuelUiTankPtrAltOffset, offsets.FuelPctF32AltOffset, "ui130_06c");
        yield return new(offsets.FuelUiTankPtrAltOffset, offsets.FuelPctF32Alt2Offset, "ui130_070");
    }

    private static FuelSnapshot? TryDirectHudFuel(
        nint processHandle,
        nint vehicle,
        nint addon,
        OffsetsReference offsets,
        int capacity)
    {
        double? addonLiters = null;
        if (ProcessMemoryReader.ReadFloat32(processHandle, addon + offsets.FuelPctAddonDirectOffset) is { } addonPct
            && IsValidFuelFraction(addonPct))
        {
            addonLiters = addonPct * capacity;
        }

        double? vehicleLiters = null;
        if (ProcessMemoryReader.ReadFloat32(processHandle, vehicle + offsets.FuelLitersVehicleOffset) is { } vehLit
            && !float.IsNaN(vehLit)
            && vehLit is > 1f and var liveLiters
            && liveLiters <= capacity)
        {
            vehicleLiters = liveLiters;
        }

        if (addonLiters is null && vehicleLiters is null)
        {
            return null;
        }

        if (addonLiters is { } addonValue && vehicleLiters is { } vehicleValue)
        {
            if (Math.Abs(addonValue - vehicleValue) <= 8.0)
            {
                return new FuelSnapshot(
                    (addonValue + vehicleValue) / 2.0,
                    capacity,
                    "addon868+veh728");
            }

            return new FuelSnapshot(addonValue, capacity, "addon_pct868");
        }

        if (addonLiters is { } onlyAddon)
        {
            return new FuelSnapshot(onlyAddon, capacity, "addon_pct868");
        }

        return new FuelSnapshot(vehicleLiters!.Value, capacity, "veh_lit728");
    }

    private static FuelSnapshot? TryLiveFuelSnapshot(
        nint processHandle,
        nint vehicle,
        nint addon,
        OffsetsReference offsets)
    {
        var capacity = ResolveCapacity(processHandle, addon, offsets);

        if (TryDirectHudFuel(processHandle, vehicle, addon, offsets, capacity) is { } directSnapshot)
        {
            return directSnapshot;
        }

        var consumeCandidates = new List<(double Liters, string Source)>();
        var repostajeCandidates = new List<(double Liters, string Source)>();

        if (ProcessMemoryReader.ReadFloat32(processHandle, addon + offsets.FuelLitersLiveF32Offset) is { } addonLiters
            && !float.IsNaN(addonLiters)
            && addonLiters is > 1f and var liveLiters
            && liveLiters <= capacity)
        {
            repostajeCandidates.Add((liveLiters, "addon_f32"));
        }

        if (ProcessMemoryReader.ReadFloat32(processHandle, vehicle + offsets.FuelPctVehicleOffset) is { } vehiclePct
            && IsValidFuelFraction(vehiclePct))
        {
            consumeCandidates.Add((vehiclePct * capacity, "veh_pct"));
        }

        AddFractionCandidates(processHandle, addon, capacity, BuildConsumeProbes(offsets), consumeCandidates);
        AddFractionCandidates(processHandle, addon, capacity, BuildRepostajeProbes(offsets), repostajeCandidates);

        if (ProcessMemoryReader.ReadUInt16(processHandle, addon + offsets.FuelLitersLiveU16Offset)
            is > 0 and var hudLiters
            && hudLiters <= capacity)
        {
            repostajeCandidates.Add((hudLiters, "addon_u16"));
            consumeCandidates.Add((hudLiters, "addon_u16"));
        }

        (double Liters, string Source)? consumePick = consumeCandidates.Count > 0
            ? PickClusterLiters(consumeCandidates, PreferredLiveSources)
            : null;
        (double Liters, string Source)? repostajePick = repostajeCandidates.Count > 0
            ? PickClusterLiters(repostajeCandidates, PreferredRepostajeSources)
            : null;

        double? hudU16 = ProcessMemoryReader.ReadUInt16(processHandle, addon + offsets.FuelLitersLiveU16Offset)
            is > 0 and var u16
            && u16 <= capacity
            ? u16
            : null;

        if (consumePick is not null || repostajePick is not null)
        {
            var picked = FuelModeTracker.Resolve(consumePick, repostajePick, hudU16);
            return new FuelSnapshot(picked.Liters, capacity, picked.Source);
        }

        return TryFractionSnapshot(
            processHandle,
            addon,
            capacity,
            BuildRepostajeProbes(offsets),
            preferLow: false);
    }

    private static void AddFractionCandidates(
        nint processHandle,
        nint addon,
        int capacity,
        IEnumerable<FuelUiProbe> probes,
        List<(double Liters, string Source)> candidates)
    {
        foreach (var probe in probes)
        {
            if (ReadPointer(processHandle, addon + probe.TankPtrOffset) is not { } child)
            {
                continue;
            }

            if (ProcessMemoryReader.ReadFloat32(processHandle, child + probe.PctOffset) is not { } fraction)
            {
                continue;
            }

            if (!IsValidFuelFraction(fraction))
            {
                continue;
            }

            candidates.Add((fraction * capacity, probe.Tag));
        }
    }

    private static (double Liters, string Source) PickClusterLiters(
        IReadOnlyList<(double Liters, string Source)> candidates,
        IReadOnlyList<string> preferredSources) =>
        PickLiveLiters(candidates, preferredSources);

    private static (double Liters, string Source) PickLiveLiters(
        IReadOnlyList<(double Liters, string Source)> candidates,
        IReadOnlyList<string>? preferredSources = null)
    {
        preferredSources ??= PreferredLiveSources;
        var pool = candidates.Where(static candidate => candidate.Source != "addon_u16").ToList();
        if (pool.Count == 0)
        {
            pool = candidates.ToList();
        }

        if (pool.Count == 1)
        {
            return pool[0];
        }

        pool = DropLowOutliers(pool);
        if (pool.Count == 1)
        {
            return pool[0];
        }

        foreach (var tag in preferredSources)
        {
            var hit = pool.FirstOrDefault(candidate => candidate.Source == tag);
            if (hit.Source == tag && IsNearMedian(pool, hit.Liters))
            {
                return hit;
            }
        }

        var cluster = ClusterNearMedian(pool);
        var average = cluster.Average(static candidate => candidate.Liters);
        return cluster.MinBy(candidate => Math.Abs(candidate.Liters - average));
    }

    private static List<(double Liters, string Source)> DropLowOutliers(
        IReadOnlyList<(double Liters, string Source)> pool)
    {
        var maxLiters = pool.Max(static candidate => candidate.Liters);
        if (maxLiters <= 80)
        {
            return pool.ToList();
        }

        var floor = maxLiters * LowOutlierRatio;
        var filtered = pool.Where(candidate => candidate.Liters >= floor).ToList();
        return filtered.Count > 0 ? filtered : pool.ToList();
    }

    private static List<(double Liters, string Source)> ClusterNearMedian(
        IReadOnlyList<(double Liters, string Source)> pool)
    {
        var median = MedianLiters(pool);
        var cluster = pool.Where(candidate => Math.Abs(candidate.Liters - median) <= StaleLitersGap).ToList();
        return cluster.Count > 0 ? cluster : pool.ToList();
    }

    private static bool IsNearMedian(IReadOnlyList<(double Liters, string Source)> pool, double liters)
    {
        var median = MedianLiters(pool);
        return Math.Abs(liters - median) <= StaleLitersGap;
    }

    private static double MedianLiters(IReadOnlyList<(double Liters, string Source)> pool)
    {
        var sorted = pool.Select(static candidate => candidate.Liters).Order().ToList();
        var mid = sorted.Count / 2;
        return sorted.Count % 2 == 1
            ? sorted[mid]
            : (sorted[mid - 1] + sorted[mid]) / 2.0;
    }

    private static FuelSnapshot? TryFractionSnapshot(
        nint processHandle,
        nint addon,
        int capacity,
        IEnumerable<FuelUiProbe> probes,
        bool preferLow)
    {
        var hits = new List<(float Fraction, string Tag)>();

        foreach (var probe in probes)
        {
            if (ReadPointer(processHandle, addon + probe.TankPtrOffset) is not { } child)
            {
                continue;
            }

            if (ProcessMemoryReader.ReadFloat32(processHandle, child + probe.PctOffset) is not { } fraction)
            {
                continue;
            }

            if (!IsValidFuelFraction(fraction))
            {
                continue;
            }

            hits.Add((fraction, probe.Tag));
        }

        if (hits.Count == 0)
        {
            return null;
        }

        var picked = preferLow
            ? PickConsumeFraction(hits.Select(static hit => hit.Fraction).ToList())
            : PickFuelFraction(hits.Select(static hit => hit.Fraction).ToList());
        var tag = hits.MinBy(hit => Math.Abs(hit.Fraction - picked)).Tag;
        return new FuelSnapshot(picked * capacity, capacity, tag);
    }

    private static int ResolveCapacity(nint processHandle, nint addon, OffsetsReference offsets)
    {
        var cap = ProcessMemoryReader.ReadUInt16(processHandle, addon + offsets.FuelCapacityOffset);
        return cap is >= 80 and <= 500 ? cap.Value : offsets.FuelDefaultCapacityLiters;
    }

    private static bool IsValidFuelFraction(float? fraction) =>
        fraction is { } value
        && !float.IsNaN(value)
        && value is >= 0f and <= 1.05f;

    private static float PickConsumeFraction(IReadOnlyList<float> fractions)
    {
        if (fractions.Count == 1)
        {
            return fractions[0];
        }

        var min = fractions.Min();
        var cluster = fractions.Where(value => value <= min + StaleOutlierGap).ToList();
        return PickFuelFraction(cluster);
    }

    private static float PickFuelFraction(IReadOnlyList<float> fractions)
    {
        if (fractions.Count == 1)
        {
            return fractions[0];
        }

        var sorted = fractions.OrderBy(static value => value).ToList();
        var mid = sorted.Count / 2;
        return sorted.Count % 2 == 1
            ? sorted[mid]
            : (sorted[mid - 1] + sorted[mid]) / 2f;
    }

    private static FuelSnapshot? TrySnapshot(
        nint processHandle,
        nint addon,
        OffsetsReference offsets)
    {
        var capacity = ProcessMemoryReader.ReadUInt16(processHandle, addon + offsets.FuelCapacityOffset);
        if (capacity is not { } cap || cap < 80 || cap > 500)
        {
            return null;
        }

        var hud = ProcessMemoryReader.ReadUInt16(processHandle, addon + offsets.FuelLitersHudOffset);
        if (hud is > 0 and var hudLiters && hudLiters <= cap)
        {
            return new FuelSnapshot(hudLiters, cap, "hud_u16");
        }

        var live = ProcessMemoryReader.ReadFloat32(processHandle, addon + offsets.FuelLitersOffset);
        if (live is { } liters && !float.IsNaN(liters) && liters > 0f && liters <= cap)
        {
            return new FuelSnapshot(liters, cap, "live_f32");
        }

        return null;
    }

    private static FuelSnapshot? ReadFuelFromSingleton(
        nint processHandle,
        nint singletonAddr,
        OffsetsReference offsets,
        nint vehicle)
    {
        if (ReadPointer(processHandle, singletonAddr) is not { } singleton)
        {
            return null;
        }

        if (ReadPointer(processHandle, singleton + 0x8) is not { } step1)
        {
            return null;
        }

        if (ReadPointer(processHandle, step1 + AddonManagerOffset) is not { } fuelObj)
        {
            return null;
        }

        return TryLiveFuelSnapshot(processHandle, vehicle, fuelObj, offsets)
            ?? TrySnapshot(processHandle, fuelObj, offsets);
    }

    private static string Format(double? value) =>
        value is null ? "null" : value.Value.ToString("F2", CultureInfo.InvariantCulture);

    private static string Format(float? value) =>
        value is null ? "null" : value.Value.ToString("F4", CultureInfo.InvariantCulture);

    private static double? NormalizePct(double pct) =>
        pct is < 0 or > 100.5 ? null : Math.Round(pct, 1);

    private static nint? ReadPointer(nint processHandle, nint address)
    {
        var ptr = ProcessMemoryReader.ReadUInt64(processHandle, address);
        return ptr is > 0x10000 and < 0x7FFFFFFFFFFF ? (nint)ptr.Value : null;
    }
}
