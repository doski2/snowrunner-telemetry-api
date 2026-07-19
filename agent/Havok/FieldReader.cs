using System.Globalization;
using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent.Havok;

internal static class FieldReader
{
    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    public static string ReadFieldAt(nint processHandle, nint basePtr, string offsetSpec, string kind)
    {
        if (OffsetsReference.ParseHex(offsetSpec) is not { } offset)
        {
            return "";
        }

        var addr = basePtr + offset;
        if (string.Equals(kind, "u8", StringComparison.OrdinalIgnoreCase))
        {
            var raw = ProcessMemoryReader.ReadUInt8(processHandle, addr);
            return raw is null ? "" : (raw.Value / 255.0).ToString("F3", Inv);
        }

        var f32 = ProcessMemoryReader.ReadFloat32(processHandle, addr);
        if (f32 is null || float.IsNaN(f32.Value) || Math.Abs(f32.Value) > 1e6)
        {
            return "";
        }

        var v = f32.Value;
        return v is >= 0f and <= 1.05f ? v.ToString("F3", Inv) : v.ToString("F1", Inv);
    }
}
