namespace SnowrunnerTelemetryAgent.Input;

public readonly record struct PhysicalThrottleSample(
    bool Connected,
    string Backend,
    string DeviceName,
    string Value,
    string ThrottleAxis,
    int RawAxis,
    byte XInputRightTrigger,
    byte XInputLeftTrigger,
    int XInputUserIndex)
{
    public static PhysicalThrottleSample Empty { get; } = new(
        false, "", "", "", "", 0, 0, 0, -1);
}

public static class PhysicalInputReader
{
    public static PhysicalThrottleSample Read(int preferredXInputIndex = -1) =>
        Probe(preferredXInputIndex) ?? PhysicalThrottleSample.Empty;

    public static bool TryDetect(out string backend, out string deviceName)
    {
        if (Probe() is { } sample)
        {
            backend = sample.Backend;
            deviceName = sample.DeviceName;
            return true;
        }

        backend = "";
        deviceName = "";
        return false;
    }

    private static PhysicalThrottleSample? Probe(int preferredXInputIndex = -1)
    {
        var winMm = WinMmJoystickReader.Read();
        if (winMm.Connected)
        {
            return ToPhysical(winMm);
        }

        var winGame = WinGameControllerReader.Read();
        if (winGame.Connected && winGame.Score >= 50)
        {
            return ToPhysical(winGame);
        }

        var directInput = DirectInputReader.Read();
        if (directInput.Connected)
        {
            return ToPhysical(directInput);
        }

        if (winGame.Connected && winGame.Score >= 15)
        {
            return ToPhysical(winGame);
        }

        var xinput = XInputReader.Read(preferredXInputIndex);
        return xinput.Connected ? ToPhysical(xinput) : null;
    }

    private static PhysicalThrottleSample ToPhysical(WinMmThrottleSample sample) =>
        new(
            true,
            "winmm",
            $"{sample.DeviceName} (joy{sample.JoyId})",
            sample.Value,
            sample.Axis,
            (int)sample.RawAxis,
            0,
            0,
            -1);

    private static PhysicalThrottleSample ToPhysical(WinGameThrottleSample sample) =>
        new(
            true,
            "wingame",
            sample.DeviceName,
            sample.Value,
            sample.AxisLabel,
            (int)Math.Round(sample.Throttle * 32767),
            0,
            0,
            -1);

    private static PhysicalThrottleSample ToPhysical(DirectInputThrottleSample sample) =>
        new(
            true,
            "directinput",
            sample.DeviceName,
            sample.Value,
            sample.ThrottleAxis,
            sample.RawAxis,
            0,
            0,
            -1);

    private static PhysicalThrottleSample ToPhysical(XInputThrottleSample sample) =>
        new(
            true,
            "xinput",
            $"slot {sample.UserIndex}",
            sample.Value,
            "RT/LT",
            Math.Max(sample.RightTrigger, sample.LeftTrigger),
            sample.RightTrigger,
            sample.LeftTrigger,
            sample.UserIndex);
}
