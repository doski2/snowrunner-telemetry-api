using System.Runtime.InteropServices;
using SnowrunnerTelemetryAgent.Native;

namespace SnowrunnerTelemetryAgent.Memory;

public sealed class GameProcess : IDisposable
{
    private readonly nint _handle;
    private bool _disposed;

    public GameProcess(uint processId)
    {
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

        _disposed = true;
        Kernel32.CloseHandle(_handle);
    }
}
