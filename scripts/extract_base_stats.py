#!/usr/bin/env python3
"""
Extract species ID → base stats mapping from the Radical Red ROM.

Uses two tables (from dump_team.py):
  Gen 1-3 (species 1-386):  ROM 0x00254784, stride 28
  Gen 4-9 (species 387+):   ROM 0x017B98EC, stride 28

First 6 bytes of each entry: HP, ATK, DEF, SPE, SPA, SPDEF.

Usage:
    uv run python scripts/extract_base_stats.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
ROM  = ROOT / "radicalred.gba"
OUT  = ROOT / "data" / "base_stats.json"

_GEN3_TABLE  = 0x00254784
_EXT_TABLE   = 0x017B98EC
_STRIDE      = 28
_GEN3_MAX    = 386


def _read_base_stats(rom: bytes, species_id: int) -> dict | None:
    if species_id <= _GEN3_MAX:
        base = _GEN3_TABLE + species_id * _STRIDE
    else:
        base = _EXT_TABLE + species_id * _STRIDE

    if base + 6 > len(rom):
        return None

    hp, atk, def_, spe, spa, spdef = rom[base:base + 6]
    if hp == 0 and atk == 0:
        return None

    return {"hp": hp, "atk": atk, "def": def_, "spe": spe, "spa": spa, "spdef": spdef}


def main():
    rom = ROM.read_bytes()
    species = json.loads((ROOT / "data" / "species.json").read_text())

    entries = [None]  # index 0 = null
    for species_id in range(1, len(species)):
        if not species[species_id]:
            entries.append(None)
            continue
        entries.append(_read_base_stats(rom, species_id))

    OUT.write_text(json.dumps(entries, indent=2) + "\n")
    print(f"Wrote {len(entries)} entries to {OUT}")

    for sid, name, expected in [
        (1,   "Bulbasaur",  {"hp": 45, "atk": 49, "def": 49, "spe": 45,  "spa": 65,  "spdef": 65}),
        (6,   "Charizard",  {"hp": 78, "atk": 84, "def": 78, "spe": 100, "spa": 109, "spdef": 85}),
        (130, "Gyarados",   {"hp": 95, "atk": 125,"def": 79, "spe": 81,  "spa": 60,  "spdef": 100}),
        (944, "Incineroar", {"hp": 95, "atk": 115,"def": 90, "spe": 60,  "spa": 80,  "spdef": 90}),
    ]:
        actual = entries[sid] if sid < len(entries) else None
        status = "✓" if actual == expected else f"✗ (got {actual})"
        print(f"  [{sid}] {name}: {status}")


if __name__ == "__main__":
    main()
