using System.Globalization;
using System.Text;
using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Memory;
using SnowrunnerTelemetryAgent.Models;

namespace SnowrunnerTelemetryAgent.Havok;

public sealed class ActiveSampleReader
{
    private static nint _lastVehicle;
    private readonly nint _handle;
    private readonly nint _moduleBase;
    private readonly OffsetsReference _offsets;

    public ActiveSampleReader(nint processHandle, nint moduleBase, OffsetsReference offsets)
    {
        _handle = processHandle;
        _moduleBase = moduleBase;
        _offsets = offsets;
    }

    public SpikeSample? ReadActiveSample()
    {
        foreach (var (singletonOffset, vehicleOffset, tag) in new (int, int, string)[]
        {
            (_offsets.TruckControlOffset, _offsets.VehiclePtrFromTruckControl, "TRUCK_CONTROL"),
            (_offsets.DriveLogicOffset, _offsets.VehiclePtrFromDriveLogic, "DRIVE_LOGIC"),
        })
        {
            if (ReadPointer(_moduleBase + singletonOffset) is not { } singleton)
            {
                continue;
            }

            if (ReadPointer(singleton + vehicleOffset) is not { } vehicle)
            {
                continue;
            }

            if (vehicle != _lastVehicle)
            {
                _lastVehicle = vehicle;
                FuelSessionTracker.Reset();
                FuelModeTracker.Reset();
            }

            if (ReadSampleFromVehicle(vehicle, tag) is { } sample)
            {
                var throttleInput = ParseThrottle(sample.ThrottleInput);
                var engineOn = ParseThrottle(sample.ThrottleMotor) > 0.5;
                var snapshot = FuelReader.ReadSnapshot(_handle, _moduleBase, _offsets, vehicle);
                var fuel = FuelReader.ReadFuelDisplay(
                    _handle,
                    _moduleBase,
                    _offsets,
                    vehicle,
                    sample.SpeedKmh,
                    throttleInput,
                    engineOn);
                var terrain = WheelTerrainReader.Read(
                    _handle, vehicle, _offsets, sample.VehicleId, sample.VelY);
                return sample with
                {
                    FuelPct = fuel.Pct,
                    FuelLiters = fuel.Liters ?? snapshot.Liters,
                    FuelCapacityLiters = fuel.CapacityLiters ?? snapshot.CapacityLiters,
                    FuelSource = fuel.Source,
                    TerrainKind = terrain?.TerrainKind ?? "",
                    MudGradeLabel = terrain?.MudGradeLabel ?? "",
                    MudGrade = terrain?.MudGrade,
                    WheelCount = terrain?.WheelCount ?? 0,
                    WheelGrip = terrain?.WheelGrip,
                    SurfaceAvg = terrain?.SurfaceAvg,
                    ContactAvg = terrain?.ContactAvg,
                    SurfaceDeformAvg = terrain?.SurfaceDeformAvg,
                    GripMin = terrain?.GripMin,
                    GripMax = terrain?.GripMax,
                    ContactMin = terrain?.ContactMin,
                    ContactMax = terrain?.ContactMax,
                    TerrainSource = terrain is null ? "" : $"{terrain.TerrainSource} kinds={terrain.WheelKinds}",
                };
            }
        }

        return null;
    }

    private SpikeSample? ReadSampleFromVehicle(nint vehicle, string chain)
    {
        if (ReadPointer(vehicle + _offsets.VehicleRigidBodyOffset) is not { } rb)
        {
            return null;
        }

        var vx = ProcessMemoryReader.ReadFloat32(_handle, rb + _offsets.LinearVelocityX);
        var vz = ProcessMemoryReader.ReadFloat32(_handle, rb + _offsets.LinearVelocityZ);
        if (vx is null || vz is null)
        {
            return null;
        }

        var vy = ProcessMemoryReader.ReadFloat32(_handle, rb + _offsets.LinearVelocityY) ?? 0f;
        var speedKmh = Math.Sqrt(vx.Value * vx.Value + vz.Value * vz.Value) * 3.6;
        var vehicleId = ReadVehicleId(vehicle);
        var (throttleInput, throttleSource) = ThrottleResolver.ResolveThrottleInput(
            _handle, _moduleBase, vehicle, vehicleId, _offsets, speedKmh);

        var motor = _offsets.ThrottleMotor;
        var throttleMotor = FieldReader.ReadFieldAt(_handle, vehicle, motor.Offset, motor.Kind);

        return new SpikeSample
        {
            Chain = chain,
            VehicleId = vehicleId,
            SpeedKmh = Math.Round(speedKmh, 2),
            ThrottleInput = throttleInput,
            ThrottleMotor = throttleMotor,
            ThrottleInputSource = throttleSource,
            VehicleHex = $"0x{vehicle:X}",
            RigidBodyHex = $"0x{rb:X}",
            VelX = vx.Value,
            VelY = vy,
            VelZ = vz.Value,
        };
    }

    private string ReadVehicleId(nint vehicle)
    {
        static bool Ok(string s) =>
            !string.IsNullOrEmpty(s) && s.StartsWith("s_", StringComparison.Ordinal) && s.Length < 64;

        var idPtr = ProcessMemoryReader.ReadUInt64(_handle, vehicle + _offsets.VehicleIdOffset);
        if (idPtr is > 0x10000 and < 0x7FFFFFFFFFFF)
        {
            var viaPtr = ReadCString((nint)idPtr.Value);
            if (Ok(viaPtr))
            {
                return viaPtr;
            }
        }

        var inlineId = ReadCString(vehicle + _offsets.VehicleIdOffset);
        if (Ok(inlineId))
        {
            return inlineId;
        }

        foreach (var extra in new[] { 0xD50, 0xCE8, 0xCF8 })
        {
            var fallback = ReadCString(vehicle + extra);
            if (Ok(fallback))
            {
                return fallback;
            }
        }

        return "";
    }

    private static double ParseThrottle(string raw) =>
        double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out var value)
            ? Math.Clamp(value, 0.0, 1.0)
            : 0.0;

    private nint? ReadPointer(nint address)
    {
        var ptr = ProcessMemoryReader.ReadUInt64(_handle, address);
        return ptr is > 0x10000 ? (nint)ptr.Value : null;
    }

    private string ReadCString(nint address, int maxLen = 64)
    {
        var bytes = ProcessMemoryReader.ReadBytes(_handle, address, maxLen);
        if (bytes is null)
        {
            return "";
        }

        var end = Array.IndexOf(bytes, (byte)0);
        if (end >= 0)
        {
            bytes = bytes[..end];
        }

        return Encoding.UTF8.GetString(bytes);
    }
}
