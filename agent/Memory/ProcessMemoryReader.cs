using System.Buffers.Binary;
using System.Runtime.InteropServices;
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
        if (!Kernel32.ReadProcessMemory(processHandle, address, buffer, (nuint)size, out var read)
            || read != (nuint)size)
        {
            return null;
        }

        return buffer;
    }

    public static ulong? ReadUInt64(nint processHandle, nint address)
    {
        var bytes = ReadBytes(processHandle, address, 8);
        return bytes is null ? null : BinaryPrimitives.ReadUInt64LittleEndian(bytes);
    }

    public static uint? ReadUInt32(nint processHandle, nint address)
    {
        var bytes = ReadBytes(processHandle, address, 4);
        return bytes is null ? null : BinaryPrimitives.ReadUInt32LittleEndian(bytes);
    }

    public static float? ReadFloat32(nint processHandle, nint address)
    {
        var bytes = ReadBytes(processHandle, address, 4);
        return bytes is null ? null : BinaryPrimitives.ReadSingleLittleEndian(bytes);
    }

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
            if (moduleBase == nint.Zero)
            {
                continue;
            }

            var nameLen = Psapi.GetModuleBaseNameW(
                processHandle, moduleBase, nameBuffer, (uint)nameBuffer.Length);
            if (nameLen == 0)
            {
                continue;
            }

            var name = new string(nameBuffer, 0, (int)nameLen);
            if (string.Equals(name, moduleName, StringComparison.OrdinalIgnoreCase))
            {
                return moduleBase;
            }
        }

        return null;
    }

    public static string Win32ErrorMessage()
    {
        return $"Win32 error {Marshal.GetLastWin32Error()}";
    }
}
