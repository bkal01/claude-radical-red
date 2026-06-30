import json
from dataclasses import dataclass
from pathlib import Path


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

_STATUS_TABLE = [
    (STATUS_SLEEP,    "sleep"),
    (STATUS_TOXIC,    "badly_poisoned"),  # check before POISON — toxic sets both bits
    (STATUS_POISON,   "poison"),
    (STATUS_BURN,     "burn"),
    (STATUS_FREEZE,   "frozen"),
    (STATUS_PARALYZE, "paralyzed"),
]

def decode_status(raw: int) -> str | None:
    return next((name for mask, name in _STATUS_TABLE if raw & mask), None)


# Radical Red move data ROM table (empirically found; differs from vanilla FireRed 0x08250C04
# which only covers moves 1-354; Radical Red's full table including Gen 4-9 moves is here).
_MOVE_TABLE = 0x091521D0
_MOVE_SIZE  = 12
_MOVE_PP    = 4  # base PP byte offset within a move entry

# Move ID → data, generated from the ROM by scripts/extract_moves.py.
_moves     = json.loads((Path(__file__).parent / "data" / "moves.json").read_text())
MOVE_NAME  = {i: m["name"] for i, m in enumerate(_moves) if m}
MOVE_DATA  = {i: m for i, m in enumerate(_moves) if m}

# Ability ID → name, generated from the ROM by scripts/extract_abilities.py.
_abilities    = json.loads((Path(__file__).parent / "data" / "abilities.json").read_text())
ABILITY_NAME  = {i: name for i, name in enumerate(_abilities) if name}

# Species ID → name, generated from the ROM by scripts/extract_species.py.
_species     = json.loads((Path(__file__).parent / "data" / "species.json").read_text())
SPECIES_NAME = {i: name for i, name in enumerate(_species) if name}


@dataclass
class PartyPokemon:
    name: str
    species_id: int                     # raw national dex number; needed for ROM table lookups
    held_item: int
    moves: tuple[str, str, str, str]   # empty string for empty slots
    pp: tuple[int, int, int, int]
    current_hp: int
    max_hp: int
    status: str | None                  # None = healthy
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
    base = PARTY_BASE_ADDR + slot * SLOT_SIZE
    g0 = mem.u32[base + _G0]
    a0 = mem.u32[base + _A0]
    a1 = mem.u32[base + _A1]
    a2 = mem.u32[base + _A2]
    species_id = g0 & 0xFFFF
    move_ids   = (a0 & 0xFFFF, (a0 >> 16) & 0xFFFF, a1 & 0xFFFF, (a1 >> 16) & 0xFFFF)
    return PartyPokemon(
        name=SPECIES_NAME.get(species_id, f"species_{species_id}"),
        species_id=species_id,
        held_item=(g0 >> 16) & 0xFFFF,
        moves=tuple(MOVE_NAME.get(mid, "") for mid in move_ids),
        pp=(a2 & 0xFF, (a2 >> 8) & 0xFF, (a2 >> 16) & 0xFF, (a2 >> 24) & 0xFF),
        current_hp=mem.u16[base + _CURHP],
        max_hp=mem.u16[base + _MAXHP],
        status=decode_status(mem.u32[base + _STATUS]),
        level=mem.u8[base + _LEVEL],
    )


def write_slot(mem, slot: int, *, moves: tuple[int, int, int, int], held_item: int) -> None:
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


class Party:
    def __init__(self, mem) -> None:
        self._mem = mem
        self.refresh()
        self._sync_display_to_ewram()

    def refresh(self) -> None:
        self.members = read_party(self._mem)
        self._slot_map = {p.name: i for i, p in enumerate(self.members)}
        # Does NOT reset display_pos — it tracks the visual UI order independently.

    def _sync_display_to_ewram(self) -> None:
        # Reset visual display order to match current EWRAM slot order.
        # Call this when a faint causes Radical Red to reorder EWRAM to match
        # the party screen display, before navigating the forced-replacement screen.
        self.display_pos: dict[str, int] = {p.name: i for i, p in enumerate(self.members)}

    def _update_display_after_send(self, sent_name: str) -> None:
        # After the player selects a replacement at display slot S, Radical Red
        # swaps the display order: the sent-in Pokemon takes display slot 0 and
        # whoever was at slot 0 moves to slot S. This persists for future
        # voluntary-switch party screens (EWRAM itself is restored separately).
        slot0_name = next(k for k, v in self.display_pos.items() if v == 0)
        old_slot = self.display_pos[sent_name]
        self.display_pos[sent_name] = 0
        self.display_pos[slot0_name] = old_slot

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.members]

    def get_slot_number(self, name: str) -> int:
        return self._slot_map[name]

    def get_display_slot(self, name: str) -> int:
        """Visual party screen position for this Pokemon (may differ from EWRAM slot)."""
        return self.display_pos[name]

    def set_lead(self, name: str) -> None:
        if self.members[0].name == name:
            return

        # swap the two pokemon in game memory
        slot = next(i for i, p in enumerate(self.members) if p.name == name)
        base_a = PARTY_BASE_ADDR
        base_b = PARTY_BASE_ADDR + slot * SLOT_SIZE
        for i in range(0, SLOT_SIZE, 4):
            a_val = self._mem.u32[base_a + i]
            self._mem.u32[base_a + i] = self._mem.u32[base_b + i]
            self._mem.u32[base_b + i] = a_val
        self.members[0], self.members[slot] = self.members[slot], self.members[0]
        self._sync_display_to_ewram()
