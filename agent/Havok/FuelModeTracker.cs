namespace SnowrunnerTelemetryAgent.Havok;

/// <summary>
/// Consume probes bajan en marcha y se congelan al repostar.
/// Repostaje probes suben al repostar y se congelan al consumir.
/// </summary>
internal static class FuelModeTracker
{
    private const double RefuelJumpLiters = 6.0;
    private const double StaleHighGapLiters = 12.0;
    private const double TiebreakerLiters = 8.0;
    private const double FlatEpsilon = 0.4;

    private static double? _lastConsumeLiters;
    private static double? _lastRepostajeLiters;

    public static void Reset()
    {
        _lastConsumeLiters = null;
        _lastRepostajeLiters = null;
    }

    public static (double Liters, string Source) Resolve(
        (double Liters, string Source)? consume,
        (double Liters, string Source)? repostaje,
        double? hudU16Liters = null)
    {
        if (consume is null && repostaje is null)
        {
            return (0, "none");
        }

        if (consume is null)
        {
            var only = repostaje!.Value;
            Remember(only.Liters, only.Liters);
            return only;
        }

        if (repostaje is null)
        {
            var only = consume.Value;
            Remember(only.Liters, null);
            return only;
        }

        var c = consume.Value;
        var r = repostaje.Value;

        if (hudU16Liters is { } hud)
        {
            if (Math.Abs(hud - r.Liters) <= TiebreakerLiters && hud > c.Liters + RefuelJumpLiters)
            {
                Remember(c.Liters, r.Liters);
                return (hud, $"{r.Source}+u16");
            }

            if (Math.Abs(hud - c.Liters) <= TiebreakerLiters)
            {
                Remember(c.Liters, r.Liters);
                return (hud, $"{c.Source}+u16");
            }
        }

        var pick = Choose(c, r);
        Remember(c.Liters, r.Liters);
        return pick;
    }

    private static (double Liters, string Source) Choose(
        (double Liters, string Source) consume,
        (double Liters, string Source) repostaje)
    {
        var gap = repostaje.Liters - consume.Liters;

        if (_lastConsumeLiters is null || _lastRepostajeLiters is null)
        {
            return gap > StaleHighGapLiters ? consume : PreferCloser(consume, repostaje);
        }

        var repostajeFresh = repostaje.Liters > _lastRepostajeLiters.Value + FlatEpsilon;
        var consumeFreshDown = consume.Liters < _lastConsumeLiters.Value - FlatEpsilon;
        var consumeFlat = Math.Abs(consume.Liters - _lastConsumeLiters.Value) <= FlatEpsilon;
        var repostajeFlat = Math.Abs(repostaje.Liters - _lastRepostajeLiters.Value) <= FlatEpsilon;

        if (repostajeFresh && (consumeFlat || gap >= RefuelJumpLiters))
        {
            return repostaje;
        }

        if (consumeFlat && repostajeFresh && gap >= RefuelJumpLiters)
        {
            return repostaje;
        }

        if (repostajeFlat && consumeFreshDown)
        {
            return consume;
        }

        if (gap > StaleHighGapLiters)
        {
            return consume;
        }

        return PreferCloser(consume, repostaje);
    }

    private static (double Liters, string Source) PreferCloser(
        (double Liters, string Source) consume,
        (double Liters, string Source) repostaje)
    {
        var gap = Math.Abs(repostaje.Liters - consume.Liters);
        return gap <= StaleHighGapLiters ? consume : repostaje;
    }

    private static void Remember(double consumeLiters, double? repostajeLiters)
    {
        _lastConsumeLiters = consumeLiters;
        if (repostajeLiters is { } repostaje)
        {
            _lastRepostajeLiters = repostaje;
        }
    }
}
