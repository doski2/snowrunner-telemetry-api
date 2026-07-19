using System.Globalization;
using System.Text.Json;
using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Havok;
using SnowrunnerTelemetryAgent.Input;
using SnowrunnerTelemetryAgent.Models;
using SnowrunnerTelemetryAgent.Platform;

namespace SnowrunnerTelemetryAgent;

internal static partial class Program
{
    private static readonly JsonSerializerOptions JsonPretty = new() { WriteIndented = true };
    private static long _sampleSeq;

    public static int Main(string[] args)
    {
        var options = RunOptions.Parse(args);

        if (HasArg(args, "--list-devices"))
        {
            PrintListDevices();
            return ExitOk;
        }

        if (HasArg(args, "--watch-input"))
        {
            WatchAllInputs(options.IntervalMs);
            return ExitOk;
        }

        if (HasArg(args, "--fuel-debug"))
        {
            return RunFuelDebug();
        }

        if (HasArg(args, "--fuel-diff"))
        {
            var waitMs = ParseIntArg(args, "--wait=", 5000, static v => v > 0);
            return RunFuelDiff(waitMs);
        }

        if (HasArg(args, "--fuel-scan"))
        {
            return RunFuelScan(args);
        }

        if (HasArg(args, "--wheel-debug"))
        {
            return RunWheelDebug();
        }

        Console.WriteLine("snowrunner-telemetry-agent v0.1.0 — Fase 2.1 read_active_sample spike");
        AnnounceInputDevice(options);
        Console.WriteLine();

        if (GameSession.TryLoadOffsets(out var offsets) != ExitOk || offsets is null)
        {
            return ExitMemoryFailed;
        }

        Console.WriteLine($"[OK] offsets build: {offsets.TruckControlOffset:X} / {offsets.DriveLogicOffset:X}");

        while (true)
        {
            var code = RunOnce(offsets, options);
            if (!options.Loop || code != ExitOk)
            {
                return code;
            }

            Thread.Sleep(options.IntervalMs);
            Console.WriteLine();
        }
    }

    private static bool HasArg(string[] args, string flag) =>
        args.Contains(flag, StringComparer.OrdinalIgnoreCase);

    private static void PrintListDevices()
    {
        Console.WriteLine(WinMmJoystickReader.ListDevicesReport());
        Console.WriteLine();
        Console.WriteLine(WinGameControllerReader.ListDevicesReport());
        Console.WriteLine();
        Console.WriteLine(DirectInputReader.ListDevicesReport());
        Console.WriteLine();
        Console.WriteLine(XInputReader.ListDevicesReport());
    }

    private static void WatchAllInputs(int intervalMs)
    {
        WinMmJoystickReader.WatchInputLoop(intervalMs);
        Console.WriteLine();
        WinGameControllerReader.WatchInputLoop(intervalMs);
        Console.WriteLine();
        DirectInputReader.WatchInputLoop(intervalMs);
    }

    private static void AnnounceInputDevice(RunOptions options)
    {
        if (options.MemoryOnly)
        {
            Console.WriteLine("[INFO] Solo memoria (--memory-only)");
            return;
        }

        if (PhysicalInputReader.TryDetect(out var backend, out var deviceName))
        {
            var label = backend switch
            {
                "winmm" => "Volante winmm (Eje RZ)",
                "wingame" => "Volante WinGame HID",
                "directinput" => "Volante/mando DirectInput",
                "xinput" => "Mando XInput",
                _ => "Entrada fisica",
            };
            Console.WriteLine($"[OK] {label} detectado — {deviceName}");
            return;
        }

        Console.WriteLine("[INFO] Sin volante/mando; pedal desde memoria Havok");
        if (SnowRunnerLocator.FindProcessId() is not null)
        {
            Console.WriteLine("[AVISO] SnowRunner en ejecucion — DirectInput suele estar bloqueado.");
            Console.WriteLine("        Prueba: .\\run_agent.bat --list-devices (seccion [WinMM])");
        }
    }

    private static int RunFuelDebug()
    {
        if (GameSession.TryLoadOffsets(out var offsets) != ExitOk || offsets is null)
        {
            return ExitMemoryFailed;
        }

        var (code, session) = GameSession.TryOpen(offsets);
        if (code != ExitOk || session is null)
        {
            return code;
        }

        using (session)
        {
            var sample = session.ReadActiveSample();
            if (sample is null)
            {
                Console.WriteLine("[FALLO] sin vehiculo activo");
                return ExitProbeFailed;
            }

            var vehicle = GameSession.ParseVehicle(sample);
            var (throttleInput, engineOn) = ParseThrottleSignals(sample);
            FuelReader.DebugPrint(
                session.Process.Handle,
                session.ModuleBase,
                offsets,
                vehicle,
                sample.SpeedKmh,
                throttleInput,
                engineOn);
            var pct = FuelReader.ReadFuelPct(
                session.Process.Handle,
                session.ModuleBase,
                offsets,
                vehicle,
                sample.SpeedKmh,
                throttleInput,
                engineOn);
            Console.WriteLine(
                pct is null
                    ? "[fuel-debug] ReadFuelPct -> null"
                    : $"[fuel-debug] ReadFuelPct -> {pct.Value.ToString(CultureInfo.InvariantCulture)}%");
            return ExitOk;
        }
    }

    private static int RunWheelDebug()
    {
        if (GameSession.TryLoadOffsets(out var offsets) != ExitOk || offsets is null)
        {
            return ExitMemoryFailed;
        }

        var (code, session) = GameSession.TryOpen(offsets);
        if (code != ExitOk || session is null)
        {
            return code;
        }

        using (session)
        {
            var sample = session.ReadActiveSample();
            if (sample is null)
            {
                Console.WriteLine("[FALLO] sin vehiculo activo");
                return ExitProbeFailed;
            }

            var vehicle = GameSession.ParseVehicle(sample);
            WheelTerrainReader.DebugPrint(
                session.Process.Handle,
                vehicle,
                offsets,
                sample.VehicleId);
            return ExitOk;
        }
    }

    private static int RunOnce(OffsetsReference offsets, RunOptions options)
    {
        var (code, session) = GameSession.TryOpen(offsets);
        if (code != ExitOk || session is null)
        {
            return code;
        }

        using (session)
        {
            var sample = session.ReadActiveSample();
            if (sample is null)
            {
                Console.WriteLine("[FALLO] read_active_sample — sin vehiculo activo o cadena Havok rota");
                Console.WriteLine("        Revisa offsets tras un patch (ROADMAP mantenimiento post-patch).");
                return ExitProbeFailed;
            }

            sample = MergeInputs(sample, options);
            PrintSample(sample, options);
            return sample.ProbeOk ? ExitOk : ExitProbeFailed;
        }
    }

    private static (double ThrottleInput, bool EngineOn) ParseThrottleSignals(SpikeSample sample)
    {
        var throttleInput = double.TryParse(
            sample.ThrottleInput,
            NumberStyles.Float,
            CultureInfo.InvariantCulture,
            out var pedal)
            ? pedal
            : 0.0;
        var engineOn = double.TryParse(
            sample.ThrottleMotor,
            NumberStyles.Float,
            CultureInfo.InvariantCulture,
            out var motor)
            && motor > 0.5;
        return (throttleInput, engineOn);
    }

    private static SpikeSample MergeInputs(SpikeSample sample, RunOptions options)
    {
        var physical = options.MemoryOnly
            ? PhysicalThrottleSample.Empty
            : PhysicalInputReader.Read(options.XInputUserIndex);

        var (throttle, source) = options.MemoryOnly
            ? (sample.ThrottleInput, sample.ThrottleInputSource)
            : options.ForcePhysical && physical.Connected
                ? (physical.Value, physical.Backend)
                : ThrottleInputMerger.Merge(sample.ThrottleInput, sample.ThrottleInputSource, physical);

        return sample with
        {
            ThrottleInputMemory = sample.ThrottleInput,
            ThrottleInputMemorySource = sample.ThrottleInputSource,
            PhysicalInputConnected = physical.Connected,
            PhysicalInputBackend = physical.Backend,
            PhysicalInputDevice = physical.DeviceName,
            ThrottleInputPhysical = physical.Value,
            PhysicalInputAxis = physical.ThrottleAxis,
            PhysicalInputRaw = physical.RawAxis,
            XInputUserIndex = physical.XInputUserIndex,
            XInputRightTrigger = physical.XInputRightTrigger,
            XInputLeftTrigger = physical.XInputLeftTrigger,
            ThrottleInput = throttle,
            ThrottleInputSource = source,
        };
    }

    private static void PrintSample(SpikeSample sample, RunOptions options)
    {
        var xinput = sample.PhysicalInputBackend == "xinput" && sample.PhysicalInputConnected;
        var seq = options.Loop ? Interlocked.Increment(ref _sampleSeq) : 0L;
        var payload = new
        {
            sample_seq = seq,
            probe_ok = sample.ProbeOk,
            chain = sample.Chain,
            vehicle_id = sample.VehicleId,
            speed_kmh = sample.SpeedKmh,
            fuel_pct = sample.FuelPct,
            fuel_liters = sample.FuelLiters,
            fuel_cap_liters = sample.FuelCapacityLiters,
            fuel_source = sample.FuelSource,
            terrain_kind = sample.TerrainKind,
            mud_grade = sample.MudGrade,
            mud_grade_label = sample.MudGradeLabel,
            wheel_count = sample.WheelCount,
            wheel_grip = sample.WheelGrip,
            surface_avg = sample.SurfaceAvg,
            contact_avg = sample.ContactAvg,
            surface_deform_avg = sample.SurfaceDeformAvg,
            grip_min = sample.GripMin,
            grip_max = sample.GripMax,
            contact_min = sample.ContactMin,
            contact_max = sample.ContactMax,
            terrain_source = sample.TerrainSource,
            throttle_input = sample.ThrottleInput,
            throttle_motor = sample.ThrottleMotor,
            throttle_input_src = sample.ThrottleInputSource,
            throttle_input_memory = sample.ThrottleInputMemory,
            throttle_input_memory_src = sample.ThrottleInputMemorySource,
            physical_input_connected = sample.PhysicalInputConnected,
            physical_input_backend = sample.PhysicalInputBackend,
            physical_input_device = sample.PhysicalInputDevice,
            throttle_input_physical = sample.ThrottleInputPhysical,
            physical_input_axis = sample.PhysicalInputAxis,
            physical_input_raw = sample.PhysicalInputRaw,
            xinput_connected = xinput,
            xinput_user_index = sample.XInputUserIndex,
            throttle_input_xinput = xinput ? sample.ThrottleInputPhysical : "",
            xinput_rt = sample.XInputRightTrigger,
            xinput_lt = sample.XInputLeftTrigger,
            veh = sample.VehicleHex,
            rb = sample.RigidBodyHex,
            vel = new { x = sample.VelX, y = sample.VelY, z = sample.VelZ },
        };

        var jsonOpts = options.Loop ? JsonSerializerOptions.Default : JsonPretty;
        Console.WriteLine(JsonSerializer.Serialize(payload, jsonOpts));
        if (!options.Loop)
        {
            Console.WriteLine(sample.ProbeOk
                ? "[OK] probe_ok — Fase 2.1 spike"
                : "[AVISO] muestra incompleta (vehicle_id o speed fuera de rango)");
        }
        else
        {
            Console.Out.Flush();
        }
    }

    private sealed class RunOptions
    {
        public bool Loop { get; init; }
        public int IntervalMs { get; init; } = 500;
        public bool ForcePhysical { get; init; }
        public bool MemoryOnly { get; init; }
        public int XInputUserIndex { get; init; } = -1;

        public static RunOptions Parse(string[] args)
        {
            if (args.Contains("--clear-throttle-cache", StringComparer.OrdinalIgnoreCase))
            {
                ThrottleResolver.ClearCache();
            }

            return new RunOptions
            {
                Loop = args.Contains("--loop", StringComparer.OrdinalIgnoreCase),
                IntervalMs = ParseIntArg(args, "--interval=", 500, static v => v > 0),
                ForcePhysical = args.Contains("--xinput", StringComparer.OrdinalIgnoreCase)
                    || args.Contains("--physical-only", StringComparer.OrdinalIgnoreCase),
                MemoryOnly = args.Contains("--memory-only", StringComparer.OrdinalIgnoreCase),
                XInputUserIndex = ParseIntArg(args, "--xinput-index=", -1, static v => v is >= 0 and <= 3),
            };
        }
    }
}
