using System.Buffers.Binary;
using SnowrunnerTelemetryAgent.Native;

namespace SnowrunnerTelemetryAgent.Memory;

public static class ProcessMemoryReader
{
    public static byte[]? ReadBytes(nint processHandle, nint address, int size)
    {
        if (size <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(size));
        }

        var buffer = new byte[size];
        return Kernel32.ReadProcessMemory(processHandle, address, buffer, (nuint)size, out var read)
            && read == (nuint)size
            ? buffer
            : null;
    }

    public static ulong? ReadUInt64(nint processHandle, nint address) =>
        ReadPrimitive(processHandle, address, 8, static bytes => BinaryPrimitives.ReadUInt64LittleEndian(bytes));

    public static float? ReadFloat32(nint processHandle, nint address) =>
        ReadPrimitive(processHandle, address, 4, static bytes => BinaryPrimitives.ReadSingleLittleEndian(bytes));

    public static byte? ReadUInt8(nint processHandle, nint address) =>
        ReadBytes(processHandle, address, 1) is { } bytes ? bytes[0] : null;

    public static ushort? ReadUInt16(nint processHandle, nint address) =>
        ReadPrimitive(processHandle, address, 2, static bytes => BinaryPrimitives.ReadUInt16LittleEndian(bytes));

    public static nint? GetModuleBase(nint processHandle, string moduleName)
    {
        var modules = new nint[1024];
        if (!Psapi.EnumProcessModulesEx(
                processHandle,
                modules,
                (uint)(modules.Length * nint.Size),
                out var needed,
                Psapi.ListModulesAll))
        {
            return null;
        }

        var moduleCount = Math.Min((int)(needed / (uint)nint.Size), modules.Length);
        var nameBuffer = new char[260];

        for (var i = 0; i < moduleCount; i++)
        {
            var moduleBase = modules[i];
            var nameLen = Psapi.GetModuleBaseNameW(
                processHandle, moduleBase, nameBuffer, (uint)nameBuffer.Length);
            if (nameLen > 0
                && MemoryExtensions.Equals(
                    nameBuffer.AsSpan(0, (int)nameLen),
                    moduleName,
                    StringComparison.OrdinalIgnoreCase))
            {
                return moduleBase;
            }
        }

        return null;
    }

    private static T? ReadPrimitive<T>(nint processHandle, nint address, int size, Func<byte[], T> parse)
        where T : struct
    {
        var bytes = ReadBytes(processHandle, address, size);
        return bytes is null ? null : parse(bytes);
    }
}
