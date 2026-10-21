namespace SnowrunnerTelemetryAgent.Config;

public sealed class FuelPointerScanSpec
{
    public required string Label { get; init; }
    public int ModuleOffset { get; init; }
    public int[] Offsets { get; init; } = [];
    public string ChainText { get; init; } = "";

    /// <summary>Distancia en bytes desde el campo de litros al f32 de capacidad (0 = no leer).</summary>
    public int CapacityDelta { get; init; }
}
