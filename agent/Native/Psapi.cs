using System.Runtime.InteropServices;

namespace SnowrunnerTelemetryAgent.Native;

internal static class Psapi
{
    public const uint ListModulesAll = 0x03;

    [DllImport("psapi.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern uint GetModuleBaseNameW(
        nint hProcess,
        nint hModule,
        char[] lpBaseName,
        uint nSize);

    [DllImport("psapi.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool EnumProcessModulesEx(
        nint hProcess,
        nint[] lphModule,
        uint cb,
        out uint lpcbNeeded,
        uint dwFilterFlag);
}
