namespace SnowrunnerTelemetryAgent.Config;

public sealed class FuelPointerScanSpec
{
    public required string Label { get; init; }
    public int ModuleOffset { get; init; }
    public int[] Offsets { get; init; } = [];
    public string ChainText { get; init; } = "";
}
