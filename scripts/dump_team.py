#!/usr/bin/env python3
"""
Dump the player's party to notes/team.md by reading data from the emulator.

All names and descriptions come from the ROM; nothing is hardcoded from training knowledge.

From EWRAM (live game state):
  - level, current/max HP, actual stat values (ATK/DEF/SPATK/SPDEF/SPD)
  - nature  (PID % 25, PID at slot offset 0x00)
  - ability index (PID & 1, with HA fallback for extended-table species)
  - move IDs and current PP

From ROM data tables:
  - move names    (0x010eeedc, stride 17)
  - move data     (0x091521D0, stride 12: power/accuracy/PP/type/category)
  - move descs    (pointer table at 0x0103df70)
  - ability names (0x010E32C0, stride 17)
  - ability descs (pointer table at 0x01009b84)
  - item names    (0x013c0000, stride 44, name starts at byte 0)
  - item descs    (item entry byte 20-23 is a GBA pointer to description string)
  - species ability IDs:
      Gen 3 species:       ROM 0x00254784, stride 28, ability[0]=byte[22] ability[1]=byte[23]
      Gen 7-9 species:     ROM 0x017b98ec, stride 28, same layout + HA at byte[26]

Usage:
    uv run python scripts/dump_team.py
Output: notes/team.md
"""

import struct
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from emulator import Emulator
import party

ROM        = ROOT / "radicalred.gba"
SAVE_STATE = ROOT / "save_state.ss0"
OUTPUT     = ROOT / "notes" / "team.md"

GBA_ROM = 0x08000000

# ── ROM table addresses ───────────────────────────────────────────────────────
_MOVE_NAME_TABLE  = 0x010EEEDC   # stride 17, covers all moves incl. Gen 4-9
_MOVE_NAME_STRIDE = 17
_MOVE_DATA_TABLE  = 0x011521D0   # stride 12; byte1=power, byte2=type, byte3=acc, byte4=PP, byte10=cat
_MOVE_DATA_STRIDE = 12
_MOVE_DESC_PTRS   = 0x0103DF70   # array of GBA pointers, indexed by move ID

_ABILITY_NAME_TABLE  = 0x010E32C0  # stride 17
_ABILITY_NAME_STRIDE = 17
_ABILITY_DESC_PTRS   = 0x01009B84  # array of GBA pointers, indexed by ability ID

_ITEM_TABLE       = 0x013C0000   # stride 44; name at bytes 0-13; desc ptr at bytes 20-23
_ITEM_STRIDE      = 44

_SPECIES3_TABLE   = 0x00254784   # original Gen 3 species table, stride 28
_SPECIES_EXT_TABLE = 0x017B98EC  # Radical Red extended table (Gen 4-9), stride 28
_SPECIES_STRIDE   = 28
# Within each entry: ability[0]=byte[22], ability[1]=byte[23], HA(extended only)=byte[26]

# ── EWRAM offsets within a party slot (100 bytes each) ───────────────────────
_PID    = 0x00   # u32 — PID % 25 = nature index, PID & 1 = ability index
_ATK    = 0x5A   # u16
_DEF    = 0x5C   # u16
_SPD    = 0x5E   # u16
_SPATK  = 0x60   # u16
_SPDEF  = 0x62   # u16

# ── 25 natures ────────────────────────────────────────────────────────────────
_NATURES = [
    "Hardy",   "Lonely",  "Brave",   "Adamant", "Naughty",
    "Bold",    "Docile",  "Relaxed", "Impish",  "Lax",
    "Timid",   "Hasty",   "Serious", "Jolly",   "Naive",
    "Modest",  "Mild",    "Quiet",   "Bashful", "Rash",
    "Calm",    "Gentle",  "Sassy",   "Careful", "Quirky",
]
_NATURE_EFFECT = {
    "Hardy": None,   "Lonely": ("+ATK","-DEF"),   "Brave": ("+ATK","-SPD"),
    "Adamant": ("+ATK","-SPATK"), "Naughty": ("+ATK","-SPDEF"),
    "Bold": ("+DEF","-ATK"),     "Docile": None,  "Relaxed": ("+DEF","-SPD"),
    "Impish": ("+DEF","-SPATK"), "Lax": ("+DEF","-SPDEF"),
    "Timid": ("+SPD","-ATK"),    "Hasty": ("+SPD","-DEF"),  "Serious": None,
    "Jolly": ("+SPD","-SPATK"),  "Naive": ("+SPD","-SPDEF"),
    "Modest": ("+SPATK","-ATK"), "Mild": ("+SPATK","-DEF"), "Quiet": ("+SPATK","-SPD"),
    "Bashful": None,             "Rash": ("+SPATK","-SPDEF"),
    "Calm": ("+SPDEF","-ATK"),   "Gentle": ("+SPDEF","-DEF"), "Sassy": ("+SPDEF","-SPD"),
    "Careful": ("+SPDEF","-SPATK"), "Quirky": None,
}

_TYPES = {
    0: "Normal", 1: "Fighting", 2: "Flying", 3: "Poison", 4: "Ground",
    5: "Rock",   6: "Bug",      7: "Ghost",  8: "Steel",  9: "???",
    10: "Fire",  11: "Water",   12: "Grass", 13: "Electric", 14: "Psychic",
    15: "Ice",   16: "Dragon",  17: "Dark",  18: "Fairy",
    23: "Fairy",   # Radical Red reassigned Fairy to ID 23
}
_CATEGORIES = {0: "Physical", 1: "Special", 2: "Status"}

_SPECIES = {
    130: "Gyarados", 355: "Mawile",
    935: "Armarouge", 936: "Kingambit",
    944: "Incineroar", 980: "Tsareena",
}

# Gen 3 species are in the original table; Gen 4-9 in the extended table
_GEN3_SPECIES = set(range(1, 387))


# ── ROM decode helpers ────────────────────────────────────────────────────────

def _decode(rom: bytes, offset: int, max_len: int = 200) -> str:
    out = []
    for b in rom[offset:offset + max_len]:
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
        elif b == 0xFE:
            out.append('\n')
        elif b == 0x5B:
            out.append('%')
        elif b == 0xB4:
            out.append("'")
        elif b == 0xB8:
            out.append(',')
        elif b == 0x1B:
            out.append('e')   # é in Pokémon
        elif b == 0xAB:
            out.append('!')
        elif b == 0xAC:
            out.append('?')
        else:
            break  # unknown byte — stop rather than emit garbage
    return ''.join(out).strip()


def _read_gba_ptr(rom: bytes, offset: int) -> int | None:
    v = struct.unpack_from('<I', rom, offset)[0]
    rom_off = v - GBA_ROM
    return rom_off if 0 < rom_off < len(rom) else None


def _move_name(rom: bytes, move_id: int) -> str:
    if move_id == 0:
        return '(none)'
    addr = _MOVE_NAME_TABLE + move_id * _MOVE_NAME_STRIDE
    return _decode(rom, addr, _MOVE_NAME_STRIDE)


def _move_data(rom: bytes, move_id: int) -> dict:
    if move_id == 0:
        return {}
    addr = _MOVE_DATA_TABLE + move_id * _MOVE_DATA_STRIDE
    return {
        'power':    rom[addr + 1],
        'type':     _TYPES.get(rom[addr + 2], f'type{rom[addr + 2]}'),
        'accuracy': rom[addr + 3],
        'base_pp':  rom[addr + 4],
        'category': _CATEGORIES.get(rom[addr + 10], '?'),
    }


def _move_desc(rom: bytes, move_id: int) -> str:
    ptr_addr = _MOVE_DESC_PTRS + move_id * 4
    p = _read_gba_ptr(rom, ptr_addr)
    return _decode(rom, p, 300) if p else ''


def _ability_name(rom: bytes, ability_id: int) -> str:
    if ability_id == 0:
        return '(none)'
    addr = _ABILITY_NAME_TABLE + ability_id * _ABILITY_NAME_STRIDE
    return _decode(rom, addr, _ABILITY_NAME_STRIDE)


def _ability_desc(rom: bytes, ability_id: int) -> str:
    if ability_id == 0:
        return ''
    ptr_addr = _ABILITY_DESC_PTRS + ability_id * 4
    p = _read_gba_ptr(rom, ptr_addr)
    return _decode(rom, p, 200) if p else ''


def _item_name(rom: bytes, item_id: int) -> str:
    if item_id == 0:
        return 'None'
    addr = _ITEM_TABLE + item_id * _ITEM_STRIDE
    return _decode(rom, addr, 14)


def _item_desc(rom: bytes, item_id: int) -> str:
    if item_id == 0:
        return ''
    addr = _ITEM_TABLE + item_id * _ITEM_STRIDE + 20
    p = _read_gba_ptr(rom, addr)
    return _decode(rom, p, 200) if p else ''


def _species_ability_id(rom: bytes, species_id: int, ability_index: int) -> int:
    """Return the ROM ability ID for this species at the given ability slot (0 or 1)."""
    if species_id in _GEN3_SPECIES:
        base = _SPECIES3_TABLE + species_id * _SPECIES_STRIDE
        ab0, ab1 = rom[base + 22], rom[base + 23]
        return ab1 if ability_index == 1 else ab0
    else:
        base = _SPECIES_EXT_TABLE + species_id * _SPECIES_STRIDE
        ab0, ab1, ha = rom[base + 22], rom[base + 23], rom[base + 26]
        if ability_index == 1:
            return ab1 if ab1 != 0 else ha  # fall back to HA when ability[1] is empty
        return ab0


def _read_slot_extra(mem, slot: int) -> dict:
    base = party.PARTY_BASE_ADDR + slot * party.SLOT_SIZE
    a0 = mem.u32[base + 0x2C]
    a1 = mem.u32[base + 0x30]
    a2 = mem.u32[base + 0x34]
    return {
        'pid':      mem.u32[base + _PID],
        'atk':      mem.u16[base + _ATK],
        'def_':     mem.u16[base + _DEF],
        'spd':      mem.u16[base + _SPD],
        'spatk':    mem.u16[base + _SPATK],
        'spdef':    mem.u16[base + _SPDEF],
        'move_ids': (a0 & 0xFFFF, (a0 >> 16) & 0xFFFF, a1 & 0xFFFF, (a1 >> 16) & 0xFFFF),
        'move_pps': (a2 & 0xFF, (a2 >> 8) & 0xFF, (a2 >> 16) & 0xFF, (a2 >> 24) & 0xFF),
    }


# ── Markdown assembly ─────────────────────────────────────────────────────────

def _format_desc(text: str) -> str:
    """Collapse newlines/extra spaces in a description to a single line."""
    return ' '.join(text.split())


def main() -> None:
    emu = Emulator(ROM, SAVE_STATE)
    emu.load_state()
    mem = emu.mem
    rom = ROM.read_bytes()

    lines: list[str] = ["# Player Team\n"]

    for slot in range(party.party_count(mem)):
        poke  = party.read_slot(mem, slot)
        extra = _read_slot_extra(mem, slot)

        name   = poke.name
        pid    = extra['pid']
        nature = _NATURES[pid % 25]
        effect = _NATURE_EFFECT[nature]
        nature_str = f"{nature} ({effect[0]}, {effect[1]})" if effect else f"{nature} (neutral)"

        ab_idx  = pid & 1
        ab_id   = _species_ability_id(rom, poke.species_id, ab_idx)
        ab_name = _ability_name(rom, ab_id)
        ab_desc = _format_desc(_ability_desc(rom, ab_id))

        item_name = _item_name(rom, poke.held_item)
        item_desc = _format_desc(_item_desc(rom, poke.held_item))

        lines.append(f"## {name}\n")
        lines.append(
            f"**Level:** {poke.level}  "
            f"**Nature:** {nature_str}  "
            f"**HP:** {poke.max_hp}\n"
        )
        lines.append(
            f"**Stats:** ATK {extra['atk']} | DEF {extra['def_']} | "
            f"SPATK {extra['spatk']} | SPDEF {extra['spdef']} | SPD {extra['spd']}\n"
        )
        lines.append(
            f"**Ability:** {ab_name}"
            + (f" — {ab_desc}" if ab_desc else "") + "\n"
        )
        item_line = item_name + (f" — {item_desc}" if item_desc else "")
        lines.append(f"**Item:** {item_line}\n")
        lines.append("**Moves:**\n")

        for move_id, cur_pp in zip(extra['move_ids'], extra['move_pps']):
            if move_id == 0:
                continue
            mname = _move_name(rom, move_id)
            mdata = _move_data(rom, move_id)
            mdesc = _format_desc(_move_desc(rom, move_id))
            power_str = str(mdata['power']) if mdata.get('power') else '—'
            acc_str   = f"{mdata['accuracy']}%" if mdata.get('accuracy') else '—'
            lines.append(
                f"  - **{mname}** | {mdata.get('type','?')} | "
                f"{mdata.get('category','?')} | "
                f"Power: {power_str} | Acc: {acc_str} | "
                f"PP: {cur_pp}/{mdata.get('base_pp','?')}\n"
                f"    {mdesc}\n"
            )

        lines.append("\n")

    OUTPUT.write_text("\n".join(lines))
    print(f"Written to {OUTPUT}")


if __name__ == "__main__":
    main()
