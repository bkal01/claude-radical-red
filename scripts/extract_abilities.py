#!/usr/bin/env python3
"""
Extract ability ID → name mapping from the Radical Red ROM and write to data/abilities.json.

Locates the ability name table by searching for two known sequences:
  Ability 22 = "Intimidate"
  Ability 45 = "Sand Stream"
These are confirmed from battle.py comments.

Usage:
    uv run python scripts/extract_abilities.py
"""
import json
import struct
from pathlib import Path

ROOT = Path(__file__).parent.parent
ROM  = ROOT / "radicalred.gba"
OUT  = ROOT / "data" / "abilities.json"

_NAME_TABLE_OFFSET = 0x010E32D1
_NAME_TABLE_STRIDE = 17
_DESCRIPTION_POINTER_TABLE_OFFSET = 0x01009B84
_ABILITY_COUNT = 256

def decode_text(rom: bytes, offset: int, max_len: int) -> str:
    out = []
    for i in range(max_len):
        b = rom[offset + i]
        if b == 0xFF:
            break
        if 0xBB <= b <= 0xD4:
            out.append(chr(ord('A') + b - 0xBB))
        elif 0xD5 <= b <= 0xEE:
            out.append(chr(ord('a') + b - 0xD5))
        elif b in (0x00, 0xA0):
            out.append(' ')
        elif b == 0xFE:
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
        elif b == 0xAB:
            out.append('!')
        elif b == 0xAC:
            out.append('?')
        elif b == 0x1B:
            out.append('é')
        elif 0xA1 <= b <= 0xAA:
            out.append(str(b - 0xA1))
        elif b == 0x2D:
            out.append('-')
        elif b == 0x2E:
            out.append('+')
        elif b == 0x5B:
            out.append('%')
        elif b == 0x5C:
            out.append('(')
        elif b == 0x5D:
            out.append(')')
        elif b == 0xBA:
            out.append('/')
        elif b in (0xB1, 0xB2):
            continue
        else:
            raise ValueError(f"Unsupported text byte 0x{b:02X} at 0x{offset + i:X}")
    return ' '.join(''.join(out).split())


def main():
    rom = ROM.read_bytes()
    abilities = [None]
    for ability_id in range(1, _ABILITY_COUNT):
        name_offset = _NAME_TABLE_OFFSET + (ability_id - 1) * _NAME_TABLE_STRIDE
        description_pointer_offset = _DESCRIPTION_POINTER_TABLE_OFFSET + ability_id * 4
        description_address = struct.unpack_from(
            '<I', rom, description_pointer_offset
        )[0]
        description_offset = description_address - 0x08000000
        if not 0 <= description_offset < len(rom):
            raise ValueError(
                f"Invalid description pointer for ability {ability_id}: "
                f"0x{description_address:08X}"
            )
        abilities.append(
            {
                "name": decode_text(rom, name_offset, _NAME_TABLE_STRIDE),
                "description": decode_text(rom, description_offset, 256),
            }
        )

    OUT.write_text(json.dumps(abilities, indent=2) + "\n")
    print(f"Wrote {len(abilities)} ability entries to {OUT}")


if __name__ == "__main__":
    main()
