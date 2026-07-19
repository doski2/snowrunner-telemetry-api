using System.Globalization;
using System.Text;
using SnowrunnerTelemetryAgent.Native;

namespace SnowrunnerTelemetryAgent.Input;

public readonly record struct XInputThrottleSample(
    bool Connected,
    int UserIndex,
    string Value,
    byte RightTrigger,
    byte LeftTrigger);

public static class XInputReader
{
    private const int MaxSlots = 4;

    private static XInputThrottleSample Disconnected => new(false, -1, "", 0, 0);

    public static XInputThrottleSample Read(int preferredIndex = -1)
    {
        if (preferredIndex is >= 0 and <= 3 && TryReadSlot(preferredIndex, out var preferred))
        {
            return preferred;
        }

        for (var slot = 0; slot < MaxSlots; slot++)
        {
            if (slot != preferredIndex && TryReadSlot(slot, out var sample))
            {
                return sample;
            }
        }

        return Disconnected;
    }

    public static string ListDevicesReport()
    {
        var sb = new StringBuilder();
        sb.AppendLine("[XInput] slots 0-3:");

        for (var slot = 0; slot < MaxSlots; slot++)
        {
            if (TryReadSlot(slot, out var sample))
            {
                sb.AppendLine($"  slot {slot}: RT={sample.RightTrigger} LT={sample.LeftTrigger}");
            }
            else
            {
                sb.AppendLine($"  slot {slot}: (vacío)");
            }
        }

        return sb.ToString().TrimEnd();
    }

    public static bool TryReadSlot(int userIndex, out XInputThrottleSample sample)
    {
        sample = Disconnected with { UserIndex = userIndex };
        if (userIndex is < 0 or > 3
            || XInput.GetState(userIndex, out var state) != XInput.ErrorSuccess)
        {
            return false;
        }

        var rt = state.Gamepad.RightTrigger;
        var lt = state.Gamepad.LeftTrigger;
        sample = new XInputThrottleSample(
            true,
            userIndex,
            F3(Math.Max(rt, lt) / 255.0),
            rt,
            lt);
        return true;
    }

    private static string F3(double value) => value.ToString("F3", CultureInfo.InvariantCulture);
}
