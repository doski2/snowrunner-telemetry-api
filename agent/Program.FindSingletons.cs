using System.Buffers.Binary;
using System.Text;
using SnowrunnerTelemetryAgent.Config;
using SnowrunnerTelemetryAgent.Memory;

namespace SnowrunnerTelemetryAgent;

internal static partial class Program
{
    private const int FindMaxHits = 40;
    private const int VehicleBlockSize = 0x1000;
    private const int PointerHolderBlockSize = 0x48;

    /// <summary>
    /// Tras un patch del juego, localiza singletons estáticos sin offsets previos:
    /// recorre punteros de las secciones escribibles del exe y busca objetos (a +0..+0x40
    /// del puntero) cuyo bloque contiene el <c>vehicle_id</c> del camión activo.
    /// </summary>
    private static int RunFindSingletons(string[] args)
    {
        var id = "s_krs_58_bandit";
        foreach (var arg in args)
        {
            if (arg.StartsWith("--id=", StringComparison.OrdinalIgnoreCase))
            {
                id = arg["--id=".Length..];
            }
        }

        if (GameSession.TryLoadOffsets(out var offsets) != ExitOk || offsets is null)
        {
            return ExitMemoryFailed;
        }

        var (code, session) = GameSession.TryOpen(offsets);
        if (session is null)
        {
            return code;
        }

        using (session)
        {
            var handle = session.Process.Handle;
            var moduleBase = session.ModuleBase;
            var needle = Encoding.ASCII.GetBytes(id);
            Console.WriteLine($"[find-singletons] id={id} module=0x{moduleBase:X}");

            var sections = ReadWritableSections(handle, moduleBase);
            Console.WriteLine($"[find-singletons] secciones escribibles: {sections.Count}");

            var seenVehicles = new HashSet<nint>();
            var hits = 0;
            long scanned = 0;
            foreach (var (name, rva, size) in sections)
            {
                for (var chunk = 0; chunk < size; chunk += 0x10000)
                {
                    var len = Math.Min(0x10000, size - chunk);
                    var data = ProcessMemoryReader.ReadBytes(handle, moduleBase + rva + chunk, len);
                    if (data is null)
                    {
                        continue;
                    }

                    for (var i = 0; i + 8 <= len; i += 8)
                    {
                        var raw = BinaryPrimitives.ReadUInt64LittleEndian(data.AsSpan(i, 8));
                        if (raw is <= 0x10000 or >= 0x7FFFFFFFFFFF)
                        {
                            continue;
                        }

                        scanned++;
                        var holder = ProcessMemoryReader.ReadBytes(handle, (nint)raw, PointerHolderBlockSize);
                        if (holder is null)
                        {
                            continue;
                        }

                        for (var o = 0; o < PointerHolderBlockSize; o += 8)
                        {
                            var v = BinaryPrimitives.ReadUInt64LittleEndian(holder.AsSpan(o, 8));
                            if (v is <= 0x10000 or >= 0x7FFFFFFFFFFF || !seenVehicles.Add((nint)v))
                            {
                                continue;
                            }

                            if (FindIdInObject(handle, (nint)v, needle) is not { } found)
                            {
                                continue;
                            }

                            var singletonRva = rva + chunk + i;
                            Console.WriteLine(
                                $"[HIT] singleton exe+{singletonRva:X} ({name}) -> +0x{o:X} -> vehicle 0x{v:X}"
                                + $"  id@+0x{found.Offset:X} ({found.Kind})");
                            if (++hits >= FindMaxHits)
                            {
                                Console.WriteLine("[find-singletons] límite de resultados alcanzado");
                                return ExitOk;
                            }
                        }
                    }
                }
            }

            Console.WriteLine($"[find-singletons] punteros revisados: {scanned}, hits: {hits}");
            return hits > 0 ? ExitOk : ExitProbeFailed;
        }
    }

    private static (int Offset, string Kind)? FindIdInObject(nint handle, nint obj, byte[] needle)
    {
        var block = ProcessMemoryReader.ReadBytes(handle, obj, VehicleBlockSize);
        if (block is null)
        {
            return null;
        }

        var inline = block.AsSpan().IndexOf(needle);
        if (inline >= 0)
        {
            return (inline, "inline");
        }

        for (var k = 0xC00; k + 8 <= VehicleBlockSize; k += 8)
        {
            var p = BinaryPrimitives.ReadUInt64LittleEndian(block.AsSpan(k, 8));
            if (p is <= 0x10000 or >= 0x7FFFFFFFFFFF)
            {
                continue;
            }

            var text = ProcessMemoryReader.ReadBytes(handle, (nint)p, needle.Length);
            if (text is not null && text.AsSpan().SequenceEqual(needle))
            {
                return (k, "ptr");
            }
        }

        return null;
    }

    private static List<(string Name, int Rva, int Size)> ReadWritableSections(nint handle, nint moduleBase)
    {
        var result = new List<(string, int, int)>();
        var header = ProcessMemoryReader.ReadBytes(handle, moduleBase, 0x1000);
        if (header is null)
        {
            return result;
        }

        var peOffset = BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(0x3C, 4));
        var sectionCount = BinaryPrimitives.ReadUInt16LittleEndian(header.AsSpan(peOffset + 6, 2));
        var optionalSize = BinaryPrimitives.ReadUInt16LittleEndian(header.AsSpan(peOffset + 20, 2));
        var table = peOffset + 24 + optionalSize;

        for (var s = 0; s < sectionCount; s++)
        {
            var at = table + (s * 40);
            if (at + 40 > header.Length)
            {
                break;
            }

            var name = Encoding.ASCII.GetString(header, at, 8).TrimEnd('\0');
            var virtualSize = BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(at + 8, 4));
            var rva = BinaryPrimitives.ReadInt32LittleEndian(header.AsSpan(at + 12, 4));
            var flags = BinaryPrimitives.ReadUInt32LittleEndian(header.AsSpan(at + 36, 4));
            const uint memWrite = 0x80000000;
            const uint memExecute = 0x20000000;
            if ((flags & memWrite) != 0 && (flags & memExecute) == 0)
            {
                result.Add((name, rva, virtualSize));
            }
        }

        return result;
    }
}
