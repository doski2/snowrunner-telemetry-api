using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace SnowrunnerTelemetryAgent.Config;

public sealed class DriveFieldSpec
{
    public string Base { get; init; } = "";
    public string Offset { get; init; } = "";
    public string Kind { get; init; } = "f32";
}

public sealed class OffsetsReference
{
    private static readonly DriveFieldSpec DefaultThrottleMotor = new()
    {
        Base = "vehicle",
        Offset = "+0x760",
        Kind = "f32",
    };

    public int TruckControlOffset { get; init; }
    public int DriveLogicOffset { get; init; }
    public int VehiclePtrFromTruckControl { get; init; } = 0x8;
    public int VehiclePtrFromDriveLogic { get; init; } = 0x20;
    public int VehicleRigidBodyOffset { get; init; }
    public int VehicleIdOffset { get; init; }
    public int LinearVelocityX { get; init; }
    public int LinearVelocityY { get; init; }
    public int LinearVelocityZ { get; init; }
    public int UiFuelSingletonOffset { get; init; }
    public int FuelLitersOffset { get; init; } = 0x82C;
    public int FuelLitersHudOffset { get; init; } = 0x420;
    public int FuelLitersStaleOffset { get; init; } = 0x718;
    public int FuelCapacityOffset { get; init; } = 0x732;
    public int FuelUiTankPtrOffset { get; init; } = 0x128;
    public int FuelPctF32Offset { get; init; } = 0x040;
    public int FuelUiTankPtrAltOffset { get; init; } = 0x130;
    public int FuelPctF32AltOffset { get; init; } = 0x06C;
    public int FuelPctF32Alt2Offset { get; init; } = 0x070;
    public int FuelLitersLiveU16Offset { get; init; } = 0x052;
    public int FuelLitersLiveF32Offset { get; init; } = 0x008;
    public int FuelPctVehicleOffset { get; init; } = 0x294;
    public int FuelLitersVehicleOffset { get; init; } = 0x728;
    public int FuelPctAddonDirectOffset { get; init; } = 0x868;
    public int FuelConsumeTankPtrOffset { get; init; } = 0x130;
    public int FuelConsumePctF32Offset { get; init; } = 0x4F4;
    public int FuelConsumePctF32AltOffset { get; init; } = 0x520;
    public int FuelConsumeTankPtrAltOffset { get; init; } = 0x128;
    public int FuelConsumePctF32Alt2Offset { get; init; } = 0x1F8;
    public int FuelConsumePctF32Alt3Offset { get; init; } = 0x100;
    public int FuelConsumePctF32Alt4Offset { get; init; } = 0x05C;
    public int FuelConsumePctF32Alt5Offset { get; init; } = 0x0EC;
    public int FuelDefaultCapacityLiters { get; init; } = 210;
    public int FuelCurrentOffset { get; init; } = 0x568;
    public int FuelMaxOffset { get; init; } = 0x570;
    public IReadOnlyList<FuelPointerScanSpec> FuelPointerScans { get; init; } = [];
    public DriveFieldSpec? DefaultThrottleInput { get; init; }
    public IReadOnlyDictionary<string, DriveFieldSpec> PerVehicleThrottle { get; init; }
        = new Dictionary<string, DriveFieldSpec>();
    public DriveFieldSpec ThrottleMotor { get; init; } = DefaultThrottleMotor;
    public int WheelsArrayStart { get; init; } = 0x200;
    public int WheelsArrayEnd { get; init; } = 0x208;
    public int WheelGripOffset { get; init; } = 0x2FC;
    public int WheelSurfaceOffset { get; init; } = 0x2B4;
    public int WheelContactOffset { get; init; } = 0x2EC;

    public static OffsetsReference Load(string? path = null)
    {
        path ??= Environment.GetEnvironmentVariable("SNOWRUNNER_OFFSETS_PATH")
            ?? Path.Combine(AppContext.BaseDirectory, "data", "offsets_referencia.json");

        if (!File.Exists(path))
        {
            throw new FileNotFoundException($"offsets_referencia.json not found: {path}");
        }

        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        var root = doc.RootElement;
        var singletons = root.GetProperty("singletons");
        var vehicle = root.GetProperty("vehicle_object");
        var vel = root.GetProperty("hkpRigidBody").GetProperty("linear_velocity_xyz");
        var drive = root.GetProperty("drive_runtime");
        root.TryGetProperty("terrain_runtime", out var terrainEl);

        DriveFieldSpec? defaultThrottle = null;
        var throttleMotor = DefaultThrottleMotor;
        if (drive.TryGetProperty("candidates", out var candidates))
        {
            if (candidates.TryGetProperty("throttle_input", out var globalThr))
            {
                defaultThrottle = ParseDriveSpec(globalThr);
            }

            if (candidates.TryGetProperty("throttle_motor_f32", out var motor))
            {
                throttleMotor = ParseDriveSpec(motor);
            }
        }

        var perVehicle = new Dictionary<string, DriveFieldSpec>(StringComparer.Ordinal);
        if (drive.TryGetProperty("per_vehicle", out var pv))
        {
            foreach (var entry in pv.EnumerateObject())
            {
                if (entry.Value.TryGetProperty("throttle_input", out var thr))
                {
                    perVehicle[entry.Name] = ParseDriveSpec(thr);
                }
            }
        }

        return new OffsetsReference
        {
            TruckControlOffset = RequireHex(singletons.GetProperty("TRUCK_CONTROL").GetString()),
            DriveLogicOffset = RequireHex(singletons.GetProperty("DRIVE_LOGIC").GetString()),
            VehicleRigidBodyOffset = RequireHex(vehicle.GetProperty("main_rigid_body").GetString()),
            VehicleIdOffset = RequireHex(vehicle.GetProperty("internal_id_string").GetString()),
            WheelsArrayStart = ParseHex(vehicle.GetProperty("wheels_array_start").GetString()) ?? 0x200,
            WheelsArrayEnd = ParseHex(vehicle.GetProperty("wheels_array_end").GetString()) ?? 0x208,
            WheelGripOffset = ParseHex(vehicle.GetProperty("TRUCK_WHEEL_MODEL_grip").GetString())
                ?? TerrainHex(terrainEl, "grip_per_wheel")
                ?? 0x2FC,
            WheelSurfaceOffset = ParseHex(vehicle.GetProperty("TRUCK_WHEEL_MODEL_surface").GetString())
                ?? TerrainHex(terrainEl, "surface_deform")
                ?? 0x2B4,
            WheelContactOffset = TerrainHex(terrainEl, "contact_substance") ?? 0x2EC,
            LinearVelocityX = RequireHex(vel[0].GetString()),
            LinearVelocityY = RequireHex(vel[1].GetString()),
            LinearVelocityZ = RequireHex(vel[2].GetString()),
            UiFuelSingletonOffset = RequireHex(singletons.GetProperty("UI_FUEL_SINGLETON").GetString()),
            FuelLitersOffset = ParseHex(vehicle.GetProperty("fuel_liters_f32").GetString()) ?? 0x82C,
            FuelLitersHudOffset = ParseHex(vehicle.GetProperty("fuel_liters_u16").GetString()) ?? 0x420,
            FuelLitersStaleOffset = ParseHex(vehicle.GetProperty("fuel_liters_stale_f32").GetString()) ?? 0x718,
            FuelCapacityOffset = ParseHex(vehicle.GetProperty("fuel_capacity_u16").GetString()) ?? 0x732,
            FuelUiTankPtrOffset = ParseHex(vehicle.GetProperty("fuel_ui_tank_ptr").GetString()) ?? 0x128,
            FuelPctF32Offset = ParseHex(vehicle.GetProperty("fuel_pct_f32").GetString()) ?? 0x040,
            FuelUiTankPtrAltOffset = ParseHex(vehicle.GetProperty("fuel_ui_tank_ptr_alt").GetString()) ?? 0x130,
            FuelPctF32AltOffset = ParseHex(vehicle.GetProperty("fuel_pct_f32_alt").GetString()) ?? 0x06C,
            FuelPctF32Alt2Offset = ParseHex(vehicle.GetProperty("fuel_pct_f32_alt2").GetString()) ?? 0x070,
            FuelLitersLiveU16Offset = ParseHex(vehicle.GetProperty("fuel_liters_u16_live").GetString()) ?? 0x052,
            FuelLitersLiveF32Offset = ParseHex(vehicle.GetProperty("fuel_liters_f32_live").GetString()) ?? 0x008,
            FuelPctVehicleOffset = ParseHex(vehicle.GetProperty("fuel_pct_vehicle_f32").GetString()) ?? 0x294,
            FuelLitersVehicleOffset = ParseHex(vehicle.GetProperty("fuel_liters_vehicle_f32").GetString()) ?? 0x728,
            FuelPctAddonDirectOffset = ParseHex(vehicle.GetProperty("fuel_pct_addon_direct_f32").GetString()) ?? 0x868,
            FuelConsumeTankPtrOffset = ParseHex(vehicle.GetProperty("fuel_consume_tank_ptr").GetString()) ?? 0x130,
            FuelConsumePctF32Offset = ParseHex(vehicle.GetProperty("fuel_consume_pct_f32").GetString()) ?? 0x4F4,
            FuelConsumePctF32AltOffset = ParseHex(vehicle.GetProperty("fuel_consume_pct_f32_alt").GetString()) ?? 0x520,
            FuelConsumeTankPtrAltOffset = ParseHex(vehicle.GetProperty("fuel_consume_tank_ptr_alt").GetString()) ?? 0x128,
            FuelConsumePctF32Alt2Offset = ParseHex(vehicle.GetProperty("fuel_consume_pct_f32_alt2").GetString()) ?? 0x1F8,
            FuelConsumePctF32Alt3Offset = ParseHex(vehicle.GetProperty("fuel_consume_pct_f32_alt3").GetString()) ?? 0x100,
            FuelConsumePctF32Alt4Offset = ParseHex(vehicle.GetProperty("fuel_consume_pct_f32_alt4").GetString()) ?? 0x05C,
            FuelConsumePctF32Alt5Offset = ParseHex(vehicle.GetProperty("fuel_consume_pct_f32_alt5").GetString()) ?? 0x0EC,
            FuelDefaultCapacityLiters = vehicle.TryGetProperty("fuel_default_capacity_liters", out var capLiters)
                && capLiters.TryGetInt32(out var cap)
                ? cap
                : 210,
            FuelPointerScans = ParseFuelPointerScans(root),
            DefaultThrottleInput = defaultThrottle,
            PerVehicleThrottle = perVehicle,
            ThrottleMotor = throttleMotor,
        };
    }

    private static int? TerrainHex(JsonElement terrain, string property) =>
        terrain.ValueKind == JsonValueKind.Object
        && terrain.TryGetProperty(property, out var value)
            ? ParseHex(value.GetString())
            : null;

    private static DriveFieldSpec ParseDriveSpec(JsonElement el) => new()
    {
        Base = el.GetProperty("base").GetString() ?? "",
        Offset = el.GetProperty("offset").GetString() ?? "",
        Kind = el.TryGetProperty("kind", out var kind) ? kind.GetString() ?? "f32" : "f32",
    };

    private static IReadOnlyList<FuelPointerScanSpec> ParseFuelPointerScans(JsonElement root)
    {
        var list = new List<FuelPointerScanSpec>();
        if (!root.TryGetProperty("fuel_pointerscan", out var scans))
        {
            return list;
        }

        foreach (var entry in scans.EnumerateObject())
        {
            var el = entry.Value;
            if (!el.TryGetProperty("module_offset", out var modOff)
                || !el.TryGetProperty("offsets", out var offArr))
            {
                continue;
            }

            var moduleOffset = ParseHex(modOff.GetString());
            if (moduleOffset is null)
            {
                continue;
            }

            var offsets = new List<int>();
            foreach (var off in offArr.EnumerateArray())
            {
                var parsed = ParseHex(off.GetString());
                if (parsed is null)
                {
                    offsets.Clear();
                    break;
                }

                offsets.Add(parsed.Value);
            }

            if (offsets.Count == 0)
            {
                continue;
            }

            var chain = string.Join(
                "→",
                offsets.Select(static o => $"+{o:X}"));
            list.Add(new FuelPointerScanSpec
            {
                Label = entry.Name,
                ModuleOffset = moduleOffset.Value,
                Offsets = offsets.ToArray(),
                ChainText = $"exe+{moduleOffset.Value:X}→{chain}",
            });
        }

        return list;
    }

    private static int RequireHex(string? raw) =>
        ParseHex(raw) ?? throw new InvalidDataException($"Invalid hex offset: {raw}");

    public static int? ParseHex(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return null;
        }

        var s = raw.Trim().TrimStart('+');
        if (s.StartsWith("0x", StringComparison.OrdinalIgnoreCase))
        {
            s = s[2..];
        }

        return int.Parse(s, NumberStyles.HexNumber, CultureInfo.InvariantCulture);
    }
}

public static partial class OffsetPatterns
{
    [GeneratedRegex(@"^(tc|dl)\+([0-9A-Fa-f]{3})$", RegexOptions.IgnoreCase)]
    private static partial Regex ChildBaseRegex();

    public static bool TryParseChildBase(string baseName, out string prefix, out int childOffset)
    {
        var match = ChildBaseRegex().Match(baseName);
        if (!match.Success)
        {
            prefix = "";
            childOffset = 0;
            return false;
        }

        prefix = match.Groups[1].Value.ToLowerInvariant();
        childOffset = int.Parse(match.Groups[2].Value, NumberStyles.HexNumber, CultureInfo.InvariantCulture);
        return true;
    }
}
