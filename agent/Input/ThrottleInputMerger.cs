using System.Globalization;

namespace SnowrunnerTelemetryAgent.Input;

public static class ThrottleInputMerger
{
    private const double StuckBandLow = 0.35;
    private const double StuckBandHigh = 0.75;
    private const double PressedThreshold = 0.05;
    private const double DominanceMargin = 0.05;

    public static (string Value, string Source) Merge(
        string memoryValue,
        string memorySource,
        PhysicalThrottleSample physical)
    {
        if (!physical.Connected)
        {
            return (memoryValue, memorySource);
        }

        if (physical.Backend is "directinput" or "wingame" or "winmm")
        {
            return (physical.Value, physical.Backend);
        }

        var memory = Parse(memoryValue);
        var trigger = Parse(physical.Value);

        if (trigger >= PressedThreshold
            || trigger > memory + DominanceMargin
            || (memory is > StuckBandLow and < StuckBandHigh && trigger <= PressedThreshold))
        {
            return (physical.Value, physical.Backend);
        }

        return (memoryValue, memorySource);
    }

    private static double Parse(string value) =>
        double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed)
            ? parsed
            : 0;
}
