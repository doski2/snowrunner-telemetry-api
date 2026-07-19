using System.Globalization;
using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent.Havok;

/// <summary>CE pointerscan: static module offset + pointer hops + final field offset.</summary>
internal static class FuelPointerChainReader
{
    public sealed record ChainReadResult(
        float Raw,
        double Liters,
        nint FieldAddress,
        string Label);

    public static ChainReadResult? TryRead(
        nint processHandle,
        nint moduleBase,
        FuelPointerScanSpec spec,
        int capacityLiters)
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

        if (!TryInterpretFuelLiters(raw, capacityLiters, out var liters))
        {
            return null;
        }

        return new ChainReadResult(raw, liters, field, spec.Label);
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
