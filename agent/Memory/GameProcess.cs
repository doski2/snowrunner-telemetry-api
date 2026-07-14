using System.Runtime.InteropServices;
using SnowrunnerTelemetryAgent.Native;

namespace SnowrunnerTelemetryAgent.Memory;

/// <summary>Handle Win32 a un proceso del juego (OpenProcess + lecturas).</summary>
public sealed class GameProcess : IDisposable
{
    private readonly nint _handle;
    private bool _disposed;

    public GameProcess(uint processId)
    {
        ProcessId = processId;
        _handle = Kernel32.OpenProcess(
            Kernel32.ProcessQueryInformation | Kernel32.ProcessVmRead,
            false,
            processId);

        if (_handle == nint.Zero)
        {
            throw new InvalidOperationException(
                $"OpenProcess failed for PID {processId} (error {Marshal.GetLastWin32Error()}).");
        }
    }

    public uint ProcessId { get; }

    public nint Handle
    {
        get
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            return _handle;
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        if (_handle != nint.Zero)
        {
            Kernel32.CloseHandle(_handle);
        }

        _disposed = true;
    }
}
