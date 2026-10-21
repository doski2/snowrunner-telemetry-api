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
                var throttleInput = sample.ThrottleGame ?? ParseThrottle(sample.ThrottleInput);
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
                    FuelLitersRaw = snapshot.Liters,
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

        var (position, rotation) = ReadPose(rb);
        return new SpikeSample
        {
            Position = position,
            Rotation = rotation,
            AngularVelocity = ReadFloats(rb + _offsets.AngularVelocityOffset, 3),
            WheelOmega = ReadWheelField(vehicle, _offsets.WheelOmegaOffset),
            WheelSpeed = ReadWheelField(vehicle, _offsets.WheelGroundSpeedOffset),
            ThrottleGame = ReadDriverInput(vehicle, _offsets.ThrottleGameOffset, _offsets.ThrottleGameScale, 0.0, 1.0),
            BrakeGame = ReadDriverInput(vehicle, _offsets.ThrottleGameOffset, -_offsets.ThrottleGameScale, 0.0, 1.0),
            SteerGame = ReadDriverInput(vehicle, _offsets.SteerGameOffset, _offsets.ThrottleGameScale, -1.0, 1.0),
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

    /// <summary>Matriz de rotación (3 columnas de 16 B) justo antes de la posición, en el cuerpo rígido.</summary>
    private (float[]? Position, float[]? Rotation) ReadPose(nint rb)
    {
        var rotation = new float[9];
        for (var col = 0; col < 3; col++)
        {
            if (ReadFloats(rb + _offsets.RotationOffset + (col * 16), 3) is not { } axis)
            {
                return (ReadFloats(rb + _offsets.PositionOffset, 3), null);
            }

            Array.Copy(axis, 0, rotation, col * 3, 3);
        }

        return (ReadFloats(rb + _offsets.PositionOffset, 3), rotation);
    }

    /// <summary>Un f32 por rueda (mismo offset en cada objeto rueda del array del vehículo).</summary>
    private float[]? ReadWheelField(nint vehicle, int fieldOffset)
    {
        if (ProcessMemoryReader.ReadUInt64(_handle, vehicle + _offsets.WheelsArrayStart) is not { } start
            || ProcessMemoryReader.ReadUInt64(_handle, vehicle + _offsets.WheelsArrayEnd) is not { } end
            || start < 0x10000 || end <= start)
        {
            return null;
        }

        var count = (int)Math.Min((end - start) / 8, 16);
        var values = new float[count];
        for (var i = 0; i < count; i++)
        {
            if (ReadPointer((nint)start + (i * 8)) is not { } wheel
                || ReadFloats(wheel + fieldOffset, 1) is not { } v)
            {
                return null;
            }

            values[i] = v[0];
        }

        return values;
    }

    private float[]? ReadFloats(nint address, int count)
    {
        var bytes = ProcessMemoryReader.ReadBytes(_handle, address, count * 4);
        if (bytes is null)
        {
            return null;
        }

        var values = new float[count];
        for (var i = 0; i < count; i++)
        {
            var v = BitConverter.ToSingle(bytes, i * 4);
            if (!float.IsFinite(v))
            {
                return null;
            }

            values[i] = MathF.Round(v, 4);
        }

        return values;
    }

    /// <summary>
    /// Entrada del conductor en [[vehicle+Ptr]+offset] (f32 normalizado). Gas y freno comparten el campo
    /// (negativo = gas, positivo = freno/marcha atrás); el volante está junto a él. `sign` y los límites
    /// seleccionan cada magnitud.
    /// </summary>
    private double? ReadDriverInput(nint vehicle, int fieldOffset, double sign, double lo, double hi)
    {
        if (ReadPointer(vehicle + _offsets.ThrottleGamePtrOffset) is not { } holder
            || ProcessMemoryReader.ReadFloat32(_handle, holder + fieldOffset) is not { } raw
            || !float.IsFinite(raw))
        {
            return null;
        }

        return Math.Round(Math.Clamp(raw * sign, lo, hi), 3);
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
