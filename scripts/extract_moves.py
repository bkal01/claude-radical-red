#!/usr/bin/env python3
"""
Extract move data from the Radical Red ROM and write to data/moves.json.

Output is a JSON array where index = move ID. Each entry is either null (no move)
or an object with: name, power (null if non-damaging), type, accuracy (null if
always hits), pp, category ("Physical"/"Special"/"Status").

Run once to generate the file; re-run if the ROM changes.

Usage:
    uv run python scripts/extract_moves.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
ROM  = ROOT / "radicalred.gba"
OUT  = ROOT / "data" / "moves.json"

_MOVE_NAME_TABLE  = 0x010EEEDC  # ROM file offset, not GBA address
_MOVE_NAME_STRIDE = 17

_MOVE_TABLE_GBA = 0x091521D0
_MOVE_TABLE_OFF = _MOVE_TABLE_GBA - 0x08000000
_MOVE_SIZE      = 12

_DESC_TABLE_OFF = 0x0103DF64  # ROM file offset for description pointer table
_DESC_ID_OFFSET = 3            # table entry = move_id + _DESC_ID_OFFSET

_TYPES = {
    0: "Normal",   1: "Fighting", 2: "Flying",   3: "Poison",
    4: "Ground",   5: "Rock",     6: "Bug",       7: "Ghost",
    8: "Steel",    10: "Fire",    11: "Water",    12: "Grass",
    13: "Electric", 14: "Psychic", 15: "Ice",     16: "Dragon",
    17: "Dark",    23: "Fairy",
}
_CATS = ["Physical", "Special", "Status"]


def decode_name(rom: bytes, move_id: int) -> str:
    offset = _MOVE_NAME_TABLE + move_id * _MOVE_NAME_STRIDE
    out = []
    for b in rom[offset : offset + _MOVE_NAME_STRIDE]:
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
        elif b == 0x1B:
            out.append('e')
        elif b == 0xAB:
            out.append('!')
        elif b == 0xAC:
            out.append('?')
        else:
            break
    return ''.join(out).strip()


def decode_desc(rom: bytes, move_id: int) -> str:
    import struct
    entry_off = _DESC_TABLE_OFF + (move_id + _DESC_ID_OFFSET) * 4
    if entry_off + 4 > len(rom):
        return ""
    ptr = struct.unpack_from('<I', rom, entry_off)[0]
    if not (0x08000000 <= ptr <= 0x0C000000):
        return ""
    off = ptr - 0x08000000
    out = []
    for i in range(512):
        if off + i >= len(rom):
            break
        b = rom[off + i]
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
        elif b == 0x1B:
            out.append('e')
        elif b == 0xAB:
            out.append('!')
        elif b == 0xAC:
            out.append('?')
        else:
            break
    desc = ' '.join(''.join(out).split())
    return desc if desc != 'No move information.' else ""


def read_stats(rom: bytes, move_id: int) -> dict:
    off = _MOVE_TABLE_OFF + move_id * _MOVE_SIZE
    power_raw = rom[off + 1]
    type_id   = rom[off + 2]
    acc_raw   = rom[off + 3]
    pp        = rom[off + 4]
    cat_raw   = rom[off + 10]
    desc      = decode_desc(rom, move_id)
    entry = {
        "power":    power_raw if power_raw > 0 else None,
        "type":     _TYPES.get(type_id, f"type_{type_id}"),
        "accuracy": acc_raw if acc_raw > 0 else None,
        "pp":       pp,
        "category": _CATS[cat_raw] if cat_raw < len(_CATS) else f"cat_{cat_raw}",
    }
    if desc:
        entry["description"] = desc
    return entry


def main():
    rom = ROM.read_bytes()
    entries = [None]  # index 0 = no move
    empty_streak = 0

    for move_id in range(1, 1024):
        name = decode_name(rom, move_id)
        if not name:
            entries.append(None)
            empty_streak += 1
            if empty_streak >= 16:
                while entries and entries[-1] is None:
                    entries.pop()
                break
        else:
            empty_streak = 0
            entries.append({"name": name, **read_stats(rom, move_id)})

    OUT.write_text(json.dumps(entries, indent=2) + "\n")
    print(f"Wrote {len(entries)} move entries to {OUT}")


if __name__ == "__main__":
    main()
