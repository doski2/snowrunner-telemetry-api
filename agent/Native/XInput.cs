using System.Runtime.InteropServices;

namespace SnowrunnerTelemetryAgent.Native;

internal static class XInput
{
    public const int ErrorSuccess = 0;
    private const int ErrorDeviceNotConnected = 1167;

    [DllImport("xinput1_4.dll", EntryPoint = "XInputGetState")]
    private static extern int GetState14(int userIndex, out XInputState state);

    [DllImport("xinput9_1_0.dll", EntryPoint = "XInputGetState")]
    private static extern int GetState9(int userIndex, out XInputState state);

    public static int GetState(int userIndex, out XInputState state)
    {
        var result = GetState14(userIndex, out state);
        return result is ErrorSuccess or ErrorDeviceNotConnected
            ? result
            : GetState9(userIndex, out state);
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct XInputState
    {
        public uint PacketNumber;
        public XInputGamepad Gamepad;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct XInputGamepad
    {
        public ushort Buttons;
        public byte LeftTrigger;
        public byte RightTrigger;
        public short ThumbLX;
        public short ThumbLY;
        public short ThumbRX;
        public short ThumbRY;
    }
}
