#!/usr/bin/env python3
"""
Extract species data from the Radical Red ROM and write to each task's species.json.

Output is a JSON array where index = species ID. Index 0 is null (the null species);
each populated entry contains its name, types, and base stats.

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
OUTS = [ROOT / "data" / "radical_red" / "v4.1" / "species.json"]

_SPECIES_NAME_TABLE = 0x14042CC
_SPECIES_NAME_STRIDE = 11

_SPECIES_STATS_TABLE = 0x017B98EC
_SPECIES_STATS_STRIDE = 28
_TYPE1_OFFSET = 6
_TYPE2_OFFSET = 7
GROWTH_RATE_OFFSET = 19
_ABILITY1_OFFSET = 22
_ABILITY2_OFFSET = 23
_HIDDEN_ABILITY_OFFSET = 26
GEN3_SPECIES_STATS_TABLE = 0x00254784
GEN3_MAX = 386
NUM_SPECIES = 1376
EXCLUDED_SPECIES_IDS = {412}

NAME_OVERRIDES = {
    770: "Fletchinder",
    777: "Flabébé",
    923: "Meowscarada",
    957: "Crabominable",
    989: "Type: Null",
    1077: "Blacephalon",
    1100: "Dudunsparce",
    1114: "Corvisquire",
    1115: "Corviknight",
    1139: "Barraskewda",
    1143: "Centiskorch",
    1147: "Polteageist",
    1166: "Stonjourner",
    1232: "Iron Valiant",
    1243: "Brute Bonnet",
    1244: "Sandy Shocks",
    1246: "Flutter Mane",
    1255: "Slither Wing",
    1256: "Centiskorch",
    1257: "Roaring Moon",
    1263: "Iron Jugulis",
    1268: "Basculegion",
    1290: "Centiskorch",
    1291: "Centiskorch",
    1336: "Kilowattrel",
    1338: "Squawkabilly",
    1352: "Brambleghast",
    1354: "Walking Wake",
    1355: "Squawkabilly",
    1361: "Poltchageist",
    1364: "Fezandipiti",
    1373: "Iron Boulder",
    1374: "Gouging Fire",
}
FORM_OVERRIDES = {
    713: "heat",
    714: "wash",
    715: "frost",
    716: "fan",
    717: "mow",
    866: "sevii",
    867: "sevii",
    1085: "surfing",
    1086: "flying",
    1087: "cosplay",
    1088: "libre",
    1089: "popstar",
    1090: "rockstar",
    1091: "belle",
    1092: "phd",
    1186: "sevii",
    1200: "sevii",
    1274: "sevii",
    1275: "sevii",
    1276: "sevii",
    1277: "sevii",
    1278: "sevii",
    1279: "sevii",
    1282: "sevii",
    1283: "sevii",
    1284: "sevii",
    1285: "sevii",
    1286: "sevii",
    1287: "sevii",
    1288: "sevii",
    1289: "sevii",
    1290: "sevii",
    1291: "sevii_mega",
    1292: "sevii",
    1293: "sevii_school",
    1294: "sevii",
}
SOURCE_OVERRIDES = {
    **{species_id: "radical_red" for species_id in FORM_OVERRIDES},
    1375: "radical_red",
}

for form_id, form_name in enumerate("BCDEFGHIJKLMNOPQRSTUVWXYZ", start=413):
    NAME_OVERRIDES[form_id] = "Unown"
    FORM_OVERRIDES[form_id] = form_name.lower()

_TYPES = {
    0: "Normal", 1: "Fighting", 2: "Flying", 3: "Poison", 4: "Ground",
    5: "Rock",   6: "Bug",      7: "Ghost",  8: "Steel",  9: "???",
    10: "Fire",  11: "Water",   12: "Grass", 13: "Electric", 14: "Psychic",
    15: "Ice",   16: "Dragon",  17: "Dark",  18: "Fairy", 23: "Fairy",
}

GROWTH_RATES = {
    0: "medium_fast",
    1: "erratic",
    2: "fluctuating",
    3: "medium_slow",
    4: "fast",
    5: "slow",
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
        elif b == 0xB5:
            out.append("♂")
        elif b == 0xB6:
            out.append("♀")
        elif b == 0xB8:
            out.append(',')
        elif b == 0xF0:
            out.append(':')
        elif b == 0x1B:
            out.append('é')
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
    for species_id in range(1, NUM_SPECIES):
        name = NAME_OVERRIDES.get(species_id, decode_name(rom, species_id))
        if species_id in EXCLUDED_SPECIES_IDS:
            entries.append(None)
            continue
        if name:
            ability_base = _SPECIES_STATS_TABLE + species_id * _SPECIES_STATS_STRIDE
            if species_id <= GEN3_MAX:
                stats_base = GEN3_SPECIES_STATS_TABLE + species_id * _SPECIES_STATS_STRIDE
            else:
                stats_base = _SPECIES_STATS_TABLE + species_id * _SPECIES_STATS_STRIDE
            hp, atk, defense, speed, spa, spdef = rom[stats_base:stats_base + 6]
            base_stats = None
            if hp or atk:
                base_stats = {
                    "hp": hp,
                    "atk": atk,
                    "def": defense,
                    "spe": speed,
                    "spa": spa,
                    "spdef": spdef,
                }
            entries.append({
                "name": name,
                "form": FORM_OVERRIDES.get(species_id),
                "source": SOURCE_OVERRIDES.get(species_id, "official"),
                "types": read_types(rom, species_id),
                "base_stats": base_stats,
                "growth_rate": GROWTH_RATES[rom[ability_base + GROWTH_RATE_OFFSET]],
                "abilities": {
                    "normal": [
                        ability_id
                        for ability_id in (
                            rom[ability_base + _ABILITY1_OFFSET],
                            rom[ability_base + _ABILITY2_OFFSET],
                        )
                        if ability_id
                    ],
                    "hidden": rom[ability_base + _HIDDEN_ABILITY_OFFSET] or None,
                },
            })
        else:
            entries.append(None)

    while entries and not entries[-1]:
        entries.pop()
    serialized_entries = json.dumps(entries, indent=2, ensure_ascii=False) + "\n"
    for out_path in OUTS:
        out_path.write_text(serialized_entries)
    print(f"Wrote {len(entries)} species entries to {OUTS[0]}")

    for sid, expected_name, expected_types, expected_hp in [
        (1, "Bulbasaur", ["Grass", "Poison"], 45),
        (6, "Charizard", ["Fire", "Flying"], 78),
        (35, "Clefairy", ["Fairy"], 70),
        (130, "Gyarados", ["Water", "Flying"], 95),
        (355, "Mawile", ["Steel", "Fairy"], 50),
        (503, "Hippowdon", ["Ground"], 108),
        (944, "Incineroar", ["Fire", "Dark"], 95),
        (1342, "Garganacl", ["Rock"], 100),
    ]:
        e = entries[sid] if sid < len(entries) else None
        ok = (
            e
            and e["name"] == expected_name
            and e["types"] == expected_types
            and e["base_stats"]["hp"] == expected_hp
        )
        status = "✓" if ok else f"✗ (got {e!r})"
        print(f"  [{sid}] {expected_name} {status}")


if __name__ == "__main__":
    main()
