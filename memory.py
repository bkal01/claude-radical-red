from dataclasses import dataclass


"""
Magic Numbers

We have a few magic numbers that we need to track that will let us read/write to memory directly
rather than navigating the in-game menus.
"""

# FireRed party memory layout (EWRAM)
PARTY_COUNT_ADDR = 0x02024029
PARTY_BASE_ADDR  = 0x02024284
SLOT_SIZE        = 100  # bytes per party slot

# Empirically verified: EWRAM party data is stored decrypted with fixed GAEM substruct order.
# The PID^OTID XOR and PID%24 substruct shuffle only apply to SRAM save data, not EWRAM.
#
# Fixed offsets within a party slot (100 bytes):
_CHECKSUM = 0x1C  # u16 — sum of all 16-bit halves of the 48 substruct bytes
_G0       = 0x20  # u32 — G substruct word 0: species (low 16) | held_item (high 16)
_G2       = 0x28  # u32 — G substruct word 2: PP bonus byte (bits 0-7, 2 bits per move slot)
_A0       = 0x2C  # u32 — A substruct word 0: move1 (low 16) | move2 (high 16)
_A1       = 0x30  # u32 — A substruct word 1: move3 (low 16) | move4 (high 16)
_A2       = 0x34  # u32 — A substruct word 2: pp1 | pp2<<8 | pp3<<16 | pp4<<24
_STATUS   = 0x50  # u32
_LEVEL    = 0x54  # u8
_CURHP    = 0x56  # u16
_MAXHP    = 0x58  # u16

# Status word bit masks
STATUS_SLEEP    = 0x07
STATUS_POISON   = 0x08
STATUS_BURN     = 0x10
STATUS_FREEZE   = 0x20
STATUS_PARALYZE = 0x40
STATUS_TOXIC    = 0x80

# Radical Red move data ROM table (empirically found; differs from vanilla FireRed 0x08250C04
# which only covers moves 1-354; Radical Red's full table including Gen 4-9 moves is here).
_MOVE_TABLE = 0x091521D0
_MOVE_SIZE  = 12
_MOVE_PP    = 4  # base PP byte offset within a move entry


@dataclass
class PartyPokemon:
    """
    Represents a single pokemon in the party.
    """
    species: int
    held_item: int
    moves: tuple[int, int, int, int]
    pp: tuple[int, int, int, int]
    current_hp: int
    max_hp: int
    status: int
    level: int


def _checksum(mem, base: int) -> int:
    total = sum((mem.u32[base + 0x20 + i * 4] & 0xFFFF) + (mem.u32[base + 0x20 + i * 4] >> 16)
                for i in range(12))
    return total & 0xFFFF


def _max_pp(mem, move_id: int, pp_ups: int) -> int:
    if move_id == 0:
        return 0
    base_pp = mem.u8[_MOVE_TABLE + move_id * _MOVE_SIZE + _MOVE_PP]
    return base_pp * (5 + pp_ups) // 5


def read_slot(mem, slot: int) -> PartyPokemon:
    """
    Read a single pokemon in the party from memory.
    The party is stored in memory as a contiguous block of memory, with each pokemon being 100 bytes.
    We read 4 specific words from this memory block to get the data for the pokemon at `slot`.
    """
    base = PARTY_BASE_ADDR + slot * SLOT_SIZE
    g0 = mem.u32[base + _G0]
    a0 = mem.u32[base + _A0]
    a1 = mem.u32[base + _A1]
    a2 = mem.u32[base + _A2]
    return PartyPokemon(
        species=g0 & 0xFFFF,
        held_item=(g0 >> 16) & 0xFFFF,
        moves=(a0 & 0xFFFF, (a0 >> 16) & 0xFFFF, a1 & 0xFFFF, (a1 >> 16) & 0xFFFF),
        pp=(a2 & 0xFF, (a2 >> 8) & 0xFF, (a2 >> 16) & 0xFF, (a2 >> 24) & 0xFF),
        current_hp=mem.u16[base + _CURHP],
        max_hp=mem.u16[base + _MAXHP],
        status=mem.u32[base + _STATUS],
        level=mem.u8[base + _LEVEL],
    )


def write_slot(mem, slot: int, *, moves: tuple[int, int, int, int], held_item: int) -> None:
    """
    Write a single pokemon to memory in the party.
    Functionally follows the same pattern as read_slot.
    """
    base = PARTY_BASE_ADDR + slot * SLOT_SIZE

    species = mem.u32[base + _G0] & 0xFFFF
    mem.u32[base + _G0] = species | (held_item << 16)

    pp_bonus_byte = mem.u32[base + _G2] & 0xFF
    pp_ups = [(pp_bonus_byte >> (i * 2)) & 0x3 for i in range(4)]

    mem.u32[base + _A0] = moves[0] | (moves[1] << 16)
    mem.u32[base + _A1] = moves[2] | (moves[3] << 16)
    full_pp = [_max_pp(mem, moves[i], pp_ups[i]) for i in range(4)]
    mem.u32[base + _A2] = (
        full_pp[0] | (full_pp[1] << 8) | (full_pp[2] << 16) | (full_pp[3] << 24)
    )

    mem.u16[base + _CHECKSUM] = _checksum(mem, base)
    mem.u16[base + _CURHP] = mem.u16[base + _MAXHP]
    mem.u32[base + _STATUS] = 0


def party_count(mem) -> int:
    return mem.u8[PARTY_COUNT_ADDR]


def read_party(mem) -> list[PartyPokemon]:
    return [read_slot(mem, i) for i in range(party_count(mem))]
