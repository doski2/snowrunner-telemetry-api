using System.Globalization;
using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent.Havok;

/// <summary>CE pointerscan: static module offset + pointer hops + final field offset.</summary>
internal static class FuelPointerChainReader
{
    private const float MinPlausibleCapacity = 30f;
    private const float MaxPlausibleCapacity = 1500f;

    public sealed record ChainReadResult(
        float Raw,
        double Liters,
        int CapacityLiters,
        bool CapacityFromMemory,
        nint FieldAddress,
        string Label);

    /// <summary>
    /// Lee litros del HUD y, junto al campo (<c>CapacityDelta</c>), la capacidad real del depósito.
    /// <paramref name="fallbackCapacityLiters"/> solo se usa si esa lectura no es plausible.
    /// </summary>
    public static ChainReadResult? TryRead(
        nint processHandle,
        nint moduleBase,
        FuelPointerScanSpec spec,
        int fallbackCapacityLiters)
    {
        if (spec.Offsets.Length == 0)
        {
            return null;
        }

        if (ReadChainField(processHandle, moduleBase, spec.ModuleOffset, spec.Offsets) is not { } field)
        {
            return null;
        }

        if (ProcessMemoryReader.ReadFloat32(processHandle, field) is not { } raw
            || float.IsNaN(raw))
        {
            return null;
        }

        var capacity = fallbackCapacityLiters;
        var fromMemory = false;
        if (spec.CapacityDelta != 0
            && ProcessMemoryReader.ReadFloat32(processHandle, field + spec.CapacityDelta) is { } cap
            && cap is >= MinPlausibleCapacity and <= MaxPlausibleCapacity)
        {
            capacity = (int)Math.Round(cap);
            fromMemory = true;
        }

        if (!TryInterpretFuelLiters(raw, capacity, out var liters))
        {
            return null;
        }

        return new ChainReadResult(raw, liters, capacity, fromMemory, field, spec.Label);
    }

    public static string DebugLine(
        nint processHandle,
        nint moduleBase,
        FuelPointerScanSpec spec)
    {
        if (ReadChainField(processHandle, moduleBase, spec.ModuleOffset, spec.Offsets) is not { } field)
        {
            return $"[fuel-debug]   {spec.Label}: chain broken";
        }

        var raw = ProcessMemoryReader.ReadFloat32(processHandle, field);
        return $"[fuel-debug]   {spec.Label}: raw={Format(raw)} field=0x{field:X} ({spec.ChainText})";
    }

    private static nint? ReadChainField(
        nint processHandle,
        nint moduleBase,
        int moduleOffset,
        int[] offsets)
    {
        if (ReadPointer(processHandle, moduleBase + moduleOffset) is not { } current)
        {
            return null;
        }

        for (var i = 0; i < offsets.Length - 1; i++)
        {
            if (ReadPointer(processHandle, current + offsets[i]) is not { } next)
            {
                return null;
            }

            current = next;
        }

        return current + offsets[^1];
    }

    private static bool TryInterpretFuelLiters(float raw, int capacityLiters, out double liters)
    {
        if (raw is > 0f and <= 1.2f)
        {
            liters = raw * capacityLiters;
            return liters > 0 && liters <= capacityLiters + 5;
        }

        if (raw > 1f && raw <= capacityLiters + 15f)
        {
            liters = raw;
            return true;
        }

        liters = 0;
        return false;
    }

    private static string Format(float? value) =>
        value is { } v
            ? v.ToString("F4", CultureInfo.InvariantCulture)
            : "null";

    private static nint? ReadPointer(nint processHandle, nint address)
    {
        var ptr = ProcessMemoryReader.ReadUInt64(processHandle, address);
        return ptr is > 0x10000 and < 0x7FFFFFFFFFFF ? (nint)ptr.Value : null;
    }
}
