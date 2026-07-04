#!/usr/bin/env python3
"""
Extract species data (name + typing) from the Radical Red ROM and write to data/species.json.

Output is a JSON array where index = species ID. Index 0 is null (the null species);
each populated entry is {"name": str, "types": [str, ...]} with one type for monotypes
and two for dual types.

Name table base 0x14042CC, stride 11. Typing comes from the extended base-stats table
0x017B98EC (stride 28), type bytes at offsets 6 and 7 — this table holds Radical Red's
actual (modern) typings for ALL species; the gen-3 table 0x00254784 has stale vanilla data
(e.g. Mawile reads Steel there but is Steel/Fairy in RR).

Usage:
    uv run python scripts/extract_species.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
ROM  = ROOT / "radicalred.gba"
OUT  = ROOT / "data" / "species.json"

_SPECIES_NAME_TABLE = 0x14042CC
_SPECIES_NAME_STRIDE = 11

_SPECIES_STATS_TABLE = 0x017B98EC
_SPECIES_STATS_STRIDE = 28
_TYPE1_OFFSET = 6
_TYPE2_OFFSET = 7

_TYPES = {
    0: "Normal", 1: "Fighting", 2: "Flying", 3: "Poison", 4: "Ground",
    5: "Rock",   6: "Bug",      7: "Ghost",  8: "Steel",  9: "???",
    10: "Fire",  11: "Water",   12: "Grass", 13: "Electric", 14: "Psychic",
    15: "Ice",   16: "Dragon",  17: "Dark",  18: "Fairy", 23: "Fairy",
}


def decode_name(rom: bytes, species_id: int) -> str:
    offset = _SPECIES_NAME_TABLE + species_id * _SPECIES_NAME_STRIDE
    out = []
    for b in rom[offset : offset + _SPECIES_NAME_STRIDE]:
        if b == 0xFF:
            break
        if 0xBB <= b <= 0xD4:
            out.append(chr(ord('A') + b - 0xBB))
        elif 0xD5 <= b <= 0xEE:
            out.append(chr(ord('a') + b - 0xD5))
        elif b in (0x00, 0xA0):
            out.append(' ')
        elif b == 0xAD:
            out.append('.')
        elif b == 0xAE:
            out.append('-')
        elif 0xA1 <= b <= 0xAA:
            out.append(str(b - 0xA1))
        elif b == 0xB4:
            out.append("'")
        elif b == 0xB8:
            out.append(',')
        else:
            break
    return ''.join(out).strip()


def read_types(rom: bytes, species_id: int) -> list[str]:
    base = _SPECIES_STATS_TABLE + species_id * _SPECIES_STATS_STRIDE
    t1 = _TYPES.get(rom[base + _TYPE1_OFFSET], str(rom[base + _TYPE1_OFFSET]))
    t2 = _TYPES.get(rom[base + _TYPE2_OFFSET], str(rom[base + _TYPE2_OFFSET]))
    return [t1] if t1 == t2 else [t1, t2]


def main():
    rom = ROM.read_bytes()
    entries: list = [None]  # index 0 = null species
    empty_streak = 0

    for species_id in range(1, 2048):
        name = decode_name(rom, species_id)
        entries.append({"name": name, "types": read_types(rom, species_id)} if name else None)
        empty_streak = 0 if name else empty_streak + 1
        if empty_streak >= 32:
            while entries and not entries[-1]:
                entries.pop()
            break

    OUT.write_text(json.dumps(entries, indent=2) + "\n")
    print(f"Wrote {len(entries)} species entries to {OUT}")

    for sid, expected_name, expected_types in [
        (1, "Bulbasaur", ["Grass", "Poison"]),
        (6, "Charizard", ["Fire", "Flying"]),
        (35, "Clefairy", ["Fairy"]),
        (130, "Gyarados", ["Water", "Flying"]),
        (355, "Mawile", ["Steel", "Fairy"]),
        (503, "Hippowdon", ["Ground"]),
        (944, "Incineroar", ["Fire", "Dark"]),
        (1342, "Garganacl", ["Rock"]),
    ]:
        e = entries[sid] if sid < len(entries) else None
        ok = e and e["name"] == expected_name and e["types"] == expected_types
        status = "✓" if ok else f"✗ (got {e!r})"
        print(f"  [{sid}] {expected_name} {status}")


if __name__ == "__main__":
    main()
