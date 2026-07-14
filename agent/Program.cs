using SnowrunnerTelemetryAgent.Memory;
using SnowrunnerTelemetryAgent.Platform;

namespace SnowrunnerTelemetryAgent;

internal static class Program
{
    private const int ExitOk = 0;
    private const int ExitGameNotRunning = 1;
    private const int ExitMemoryFailed = 2;

    public static int Main(string[] args)
    {
        Console.WriteLine("snowrunner-telemetry-agent v0.1.0 — Fase 2.0 scaffold");
        Console.WriteLine();

        var pid = SnowRunnerLocator.FindProcessId();
        if (pid is null)
        {
            Console.WriteLine($"[AVISO] {SnowRunnerLocator.ExecutableName} no esta en ejecucion.");
            Console.WriteLine("        Abre el juego y vuelve a ejecutar para probar OpenProcess + lectura PE.");
            return ExitGameNotRunning;
        }

        Console.WriteLine($"[OK] PID {pid.Value}");

        using var game = new GameProcess((uint)pid.Value);
        var moduleBase = ProcessMemoryReader.GetModuleBase(game.Handle, SnowRunnerLocator.ExecutableName);
        if (moduleBase is null)
        {
            Console.WriteLine($"[FALLO] No se encontro modulo {SnowRunnerLocator.ExecutableName}");
            Console.WriteLine($"        {ProcessMemoryReader.Win32ErrorMessage()}");
            return ExitMemoryFailed;
        }

        Console.WriteLine($"[OK] Module base 0x{moduleBase.Value:X}");

        var header = ProcessMemoryReader.ReadBytes(game.Handle, moduleBase.Value, 2);
        if (header is null || header[0] != (byte)'M' || header[1] != (byte)'Z')
        {
            Console.WriteLine("[FALLO] ReadProcessMemory no devolvio cabecera MZ del ejecutable");
            Console.WriteLine($"        {ProcessMemoryReader.Win32ErrorMessage()}");
            return ExitMemoryFailed;
        }

        Console.WriteLine("[OK] ReadProcessMemory — cabecera MZ valida");
        Console.WriteLine();
        Console.WriteLine("Fase 2.0 lista. Siguiente: 2.1 read_active_sample (speed, vehicle_id).");
        return ExitOk;
    }
}
