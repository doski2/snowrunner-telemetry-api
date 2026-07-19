using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Havok;
using SnowrunnerTelemetryAgent.Memory;
using SnowrunnerTelemetryAgent.Models;
using SnowrunnerTelemetryAgent.Platform;

namespace SnowrunnerTelemetryAgent;

internal static partial class Program
{
    private const int ExitOk = 0;
    private const int ExitGameNotRunning = 1;
    private const int ExitMemoryFailed = 2;
    private const int ExitProbeFailed = 3;

    private sealed class GameSession : IDisposable
    {
        public GameProcess Process { get; }
        public nint ModuleBase { get; }
        public OffsetsReference Offsets { get; }

        private GameSession(GameProcess process, nint moduleBase, OffsetsReference offsets)
        {
            Process = process;
            ModuleBase = moduleBase;
            Offsets = offsets;
        }

        public static int TryLoadOffsets(out OffsetsReference? offsets)
        {
            offsets = null;
            try
            {
                offsets = OffsetsReference.Load();
                return ExitOk;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[FALLO] offsets_referencia.json: {ex.Message}");
                return ExitMemoryFailed;
            }
        }

        public static (int ExitCode, GameSession? Session) TryOpen(OffsetsReference offsets)
        {
            var pid = SnowRunnerLocator.FindProcessId();
            if (pid is null)
            {
                Console.WriteLine($"[AVISO] {SnowRunnerLocator.ExecutableName} no esta en ejecucion.");
                return (ExitGameNotRunning, null);
            }

            var game = new GameProcess((uint)pid.Value);
            var moduleBase = ProcessMemoryReader.GetModuleBase(game.Handle, SnowRunnerLocator.ExecutableName);
            if (moduleBase is null)
            {
                game.Dispose();
                Console.WriteLine($"[FALLO] modulo {SnowRunnerLocator.ExecutableName} no encontrado");
                return (ExitMemoryFailed, null);
            }

            return (ExitOk, new GameSession(game, moduleBase.Value, offsets));
        }

        public SpikeSample? ReadActiveSample() =>
            new ActiveSampleReader(Process.Handle, ModuleBase, Offsets).ReadActiveSample();

        public static nint ParseVehicle(SpikeSample sample) =>
            (nint)Convert.ToUInt64(sample.VehicleHex[2..], 16);

        public void Dispose() => Process.Dispose();
    }

    private static nint? ReadValidPointer(nint handle, nint address)
    {
        var ptr = ProcessMemoryReader.ReadUInt64(handle, address);
        return ptr is > 0x10000 and < 0x7FFFFFFFFFFF ? (nint)ptr.Value : null;
    }

    private static int ParseIntArg(string[] args, string prefix, int fallback, Func<int, bool> valid)
    {
        foreach (var arg in args)
        {
            if (!arg.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (int.TryParse(arg[prefix.Length..], out var value) && valid(value))
            {
                return value;
            }
        }

        return fallback;
    }
}
