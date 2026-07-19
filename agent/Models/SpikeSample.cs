namespace SnowrunnerTelemetryAgent.Models;

public sealed record SpikeSample
{
    public required string Chain { get; init; }
    public required string VehicleId { get; init; }
    public double SpeedKmh { get; init; }
    public string ThrottleInput { get; init; } = "";
    public string ThrottleMotor { get; init; } = "";
    public string ThrottleInputSource { get; init; } = "none";
    public string ThrottleInputMemory { get; init; } = "";
    public string ThrottleInputMemorySource { get; init; } = "none";
    public bool PhysicalInputConnected { get; init; }
    public string PhysicalInputBackend { get; init; } = "";
    public string PhysicalInputDevice { get; init; } = "";
    public string ThrottleInputPhysical { get; init; } = "";
    public string PhysicalInputAxis { get; init; } = "";
    public int PhysicalInputRaw { get; init; }
    public int XInputUserIndex { get; init; } = -1;
    public byte XInputRightTrigger { get; init; }
    public byte XInputLeftTrigger { get; init; }
    public string VehicleHex { get; init; } = "";
    public string RigidBodyHex { get; init; } = "";
    public float VelX { get; init; }
    public float VelY { get; init; }
    public float VelZ { get; init; }
    public double? FuelPct { get; init; }
    public double? FuelLiters { get; init; }
    public int? FuelCapacityLiters { get; init; }
    public string FuelSource { get; init; } = "";
    public string TerrainKind { get; init; } = "";
    public string MudGradeLabel { get; init; } = "";
    public int? MudGrade { get; init; }
    public int WheelCount { get; init; }
    public double? WheelGrip { get; init; }
    public double? SurfaceAvg { get; init; }
    public double? ContactAvg { get; init; }
    public double? SurfaceDeformAvg { get; init; }
    public double? GripMin { get; init; }
    public double? GripMax { get; init; }
    public double? ContactMin { get; init; }
    public double? ContactMax { get; init; }
    public string TerrainSource { get; init; } = "";

    public bool ProbeOk =>
        VehicleId.StartsWith("s_", StringComparison.Ordinal)
        && SpeedKmh is >= 0 and < 500;
}
