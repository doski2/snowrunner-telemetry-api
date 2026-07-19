using System.Globalization;
using SnowrunnerTelemetryAgent.Havok;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent;

internal static partial class Program
{
    private static int RunFuelScan(string[] args)
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
                return ExitProbeFailed;
            }

            var vehicle = GameSession.ParseVehicle(sample);
            if (FuelReader.ReadAddonPointer(session.Process.Handle, vehicle) is not { } addon)
            {
                Console.WriteLine("[fuel-scan] addon null");
                return ExitProbeFailed;
            }

            var targetLiters = ParseFuelScanTarget(args);
            var targetPct = targetLiters / 210f;
            Console.WriteLine(
                $"[fuel-scan] target ~{targetLiters} L / {targetPct:P1} (cap 210) veh=0x{vehicle:X} addon=0x{addon:X}");
            Console.WriteLine("[fuel-scan] u16 matches (liters HUD):");

            ScanU16Block(session.Process.Handle, addon, "addon", targetLiters, 12);
            ScanF32Block(session.Process.Handle, addon, "addon", targetLiters, targetPct, 12f);

            foreach (var ptrOff in new[] { 0x128, 0x130, 0x120, 0x138, 0x140, 0x148 })
            {
                if (ReadValidPointer(session.Process.Handle, addon + ptrOff) is not { } child)
                {
                    continue;
                }

                ScanU16Block(session.Process.Handle, child, $"addon+{ptrOff:X}->child", targetLiters, 12);
                ScanF32Block(session.Process.Handle, child, $"addon+{ptrOff:X}->child", targetLiters, targetPct, 12f);
            }

            ScanU16Block(session.Process.Handle, vehicle, "vehicle", targetLiters, 12);
            ScanF32Block(session.Process.Handle, vehicle, "vehicle", targetLiters, targetPct, 12f);

            if (ReadValidPointer(session.Process.Handle, session.ModuleBase + offsets.UiFuelSingletonOffset) is { } singleton)
            {
                ScanF32Block(session.Process.Handle, singleton, "UI_FUEL_SINGLETON", targetLiters, targetPct, 15f);
                if (ReadValidPointer(session.Process.Handle, singleton + 0x8) is { } step1)
                {
                    ScanF32Block(session.Process.Handle, step1, "singleton+8", targetLiters, targetPct, 15f);
                }
            }

            return ExitOk;
        }
    }

    private static int ParseFuelScanTarget(string[] args)
    {
        foreach (var arg in args)
        {
            if (!arg.StartsWith("--target-liters=", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (int.TryParse(arg["--target-liters=".Length..], out var liters) && liters is > 0 and <= 500)
            {
                return liters;
            }
        }

        return 194;
    }

    private static void ScanU16Block(
        nint handle,
        nint basePtr,
        string label,
        int targetLiters,
        int tolerance)
    {
        for (var off = 0x0; off <= 0x900; off += 2)
        {
            var value = ProcessMemoryReader.ReadUInt16(handle, basePtr + off);
            if (value is not { } liters)
            {
                continue;
            }

            if (Math.Abs(liters - targetLiters) <= tolerance)
            {
                Console.WriteLine(
                    $"  {label}+0x{off:X3} u16={liters.ToString(CultureInfo.InvariantCulture)}");
            }
        }
    }

    private static void ScanF32Block(
        nint handle,
        nint basePtr,
        string label,
        int targetLiters,
        float targetPct,
        float literTolerance)
    {
        for (var off = 0x0; off <= 0x900; off += 4)
        {
            var value = ProcessMemoryReader.ReadFloat32(handle, basePtr + off);
            if (value is not { } raw || float.IsNaN(raw))
            {
                continue;
            }

            if (Math.Abs(raw - targetLiters) <= literTolerance)
            {
                Console.WriteLine(
                    $"  {label}+0x{off:X3} f32={raw.ToString("F2", CultureInfo.InvariantCulture)} L?");
            }

            if (raw is > 0.05f and <= 1.05f && Math.Abs(raw - targetPct) <= 0.03f)
            {
                Console.WriteLine(
                    $"  {label}+0x{off:X3} f32={raw.ToString("F4", CultureInfo.InvariantCulture)} pct?");
            }
        }
    }
}
