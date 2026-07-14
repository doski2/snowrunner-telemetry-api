using System.Diagnostics;

namespace SnowrunnerTelemetryAgent.Platform;

public static class SnowRunnerLocator
{
    public const string ExecutableName = "SnowRunner.exe";
    public const string ProcessName = "SnowRunner";

    public static int? FindProcessId()
    {
        var processes = Process.GetProcessesByName(ProcessName);
        try
        {
            return processes.Length > 0 ? processes[0].Id : null;
        }
        finally
        {
            foreach (var process in processes)
            {
                process.Dispose();
            }
        }
    }
}
