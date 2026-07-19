namespace SnowrunnerTelemetryAgent.Havok;

internal static class FuelSessionTracker
{
    private const double RefuelSyncLiters = 8.0;

    private static double? _liters;
    private static DateTime _lastUtc;

    public static void Reset()
    {
        _liters = null;
        _lastUtc = default;
    }

    public static double Track(
        double? rawLiters,
        int capacityLiters,
        double speedKmh,
        double throttleInput,
        bool engineOn)
    {
        var now = DateTime.UtcNow;
        var dt = _lastUtc == default ? 0.0 : (now - _lastUtc).TotalSeconds;
        _lastUtc = now;

        if (rawLiters is { } raw && raw > 0 && raw <= capacityLiters)
        {
            if (_liters is null)
            {
                _liters = raw;
                return raw;
            }

            // Memoria bajó: confiar (consumo real o campo vivo).
            if (raw < _liters.Value - 0.4)
            {
                _liters = raw;
                return raw;
            }

            // Solo subir en repostaje grande; no resync a campos congelados (+2 L saltaba a 183).
            if (raw > _liters.Value + RefuelSyncLiters)
            {
                _liters = raw;
                return raw;
            }
        }

        if (_liters is null)
        {
            return rawLiters ?? 0;
        }

        if (!engineOn || dt <= 0)
        {
            return _liters.Value;
        }

        var pedal = Math.Clamp(throttleInput, 0.0, 1.0);
        var motion = Math.Clamp(speedKmh / 45.0, 0.0, 1.5);
        var load = Math.Clamp(pedal * 0.85 + motion * 0.65, 0.05, 1.6);
        var burnPerSecond = 0.018 + load * 0.075;
        _liters = Math.Max(0.0, _liters.Value - burnPerSecond * dt);
        return _liters.Value;
    }
}
