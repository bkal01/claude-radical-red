import json
from dataclasses import dataclass
from pathlib import Path

from party import (
    PARTY_BASE_ADDR, PARTY_COUNT_ADDR, SLOT_SIZE,
    _checksum, _G0,
)

_base_stats = json.loads((Path(__file__).parent / "data" / "base_stats.json").read_text())

# EWRAM offsets not already in party.py
_PID   = 0x00   # u32: PID % 25 = nature index
_E0    = 0x38   # u32: HP_EV | ATK_EV<<8 | DEF_EV<<16 | SPE_EV<<24
_E1    = 0x3C   # u32: SPA_EV | SPDEF_EV<<8 | (contest stats, preserved)
_LEVEL = 0x54   # u8
_CURHP = 0x56   # u16
_MAXHP = 0x58   # u16
_ATK   = 0x5A   # u16
_DEF   = 0x5C   # u16
_SPE   = 0x5E   # u16
_SPA   = 0x60   # u16
_SPDEF = 0x62   # u16

# nature_id (PID % 25) → (boosted_stat, reduced_stat); None = neutral
_NATURE_MODS = [
    (None, None),           # 0  Hardy
    ("ATK", "DEF"),         # 1  Lonely
    ("ATK", "SPE"),         # 2  Brave
    ("ATK", "SPA"),         # 3  Adamant
    ("ATK", "SPDEF"),       # 4  Naughty
    ("DEF", "ATK"),         # 5  Bold
    (None, None),           # 6  Docile
    ("DEF", "SPE"),         # 7  Relaxed
    ("DEF", "SPA"),         # 8  Impish
    ("DEF", "SPDEF"),       # 9  Lax
    ("SPE", "ATK"),         # 10 Timid
    ("SPE", "DEF"),         # 11 Hasty
    (None, None),           # 12 Serious
    ("SPE", "SPA"),         # 13 Jolly
    ("SPE", "SPDEF"),       # 14 Naive
    ("SPA", "ATK"),         # 15 Modest
    ("SPA", "DEF"),         # 16 Mild
    ("SPA", "SPE"),         # 17 Quiet
    (None, None),           # 18 Bashful
    ("SPA", "SPDEF"),       # 19 Rash
    ("SPDEF", "ATK"),       # 20 Calm
    ("SPDEF", "DEF"),       # 21 Gentle
    ("SPDEF", "SPE"),       # 22 Sassy
    ("SPDEF", "SPA"),       # 23 Careful
    (None, None),           # 24 Quirky
]

EV_KEYS = ("HP", "ATK", "DEF", "SPE", "SPA", "SPDEF")


def _nature_mult(nature_id: int, stat: str) -> float:
    boosted, reduced = _NATURE_MODS[nature_id]
    if stat == boosted:
        return 1.1
    if stat == reduced:
        return 0.9
    return 1.0


def _calc_all_stats(species_id: int, evs: dict, level: int, nature_id: int) -> dict[str, int]:
    bs = _base_stats[species_id]
    if bs is None:
        raise ValueError(f"No base stats for species_id {species_id}")

    def stat(base_stat: int, ev: int, mult: float) -> int:
        return int(((2 * base_stat + ev // 4) * level // 100 + 5) * mult)

    def hp(base_stat: int, ev: int) -> int:
        return (2 * base_stat + ev // 4) * level // 100 + level + 10

    return {
        "MAXHP": hp(bs["hp"], evs.get("HP", 0)),
        "ATK":   stat(bs["atk"],   evs.get("ATK",   0), _nature_mult(nature_id, "ATK")),
        "DEF":   stat(bs["def"],   evs.get("DEF",   0), _nature_mult(nature_id, "DEF")),
        "SPE":   stat(bs["spe"],   evs.get("SPE",   0), _nature_mult(nature_id, "SPE")),
        "SPA":   stat(bs["spa"],   evs.get("SPA",   0), _nature_mult(nature_id, "SPA")),
        "SPDEF": stat(bs["spdef"], evs.get("SPDEF", 0), _nature_mult(nature_id, "SPDEF")),
    }


@dataclass
class PokemonConfig:
    species_id: int
    evs: dict[str, int]  # keys: HP ATK DEF SPE SPA SPDEF

    @classmethod
    def from_mem(cls, mem, slot: int) -> "PokemonConfig":
        base = PARTY_BASE_ADDR + slot * SLOT_SIZE
        e0 = mem.u32[base + _E0]
        e1 = mem.u32[base + _E1]
        return cls(
            species_id=mem.u32[base + _G0] & 0xFFFF,
            evs={
                "HP":    (e0 >> 0)  & 0xFF,
                "ATK":   (e0 >> 8)  & 0xFF,
                "DEF":   (e0 >> 16) & 0xFF,
                "SPE":   (e0 >> 24) & 0xFF,
                "SPA":   (e1 >> 0)  & 0xFF,
                "SPDEF": (e1 >> 8)  & 0xFF,
            },
        )

    def apply(self, mem, slot: int) -> None:
        base = PARTY_BASE_ADDR + slot * SLOT_SIZE

        # Write EVs to E substruct (IV=0; see team.py module docstring)
        e0 = (
            (self.evs.get("HP",    0) & 0xFF)        |
            ((self.evs.get("ATK",  0) & 0xFF) << 8)  |
            ((self.evs.get("DEF",  0) & 0xFF) << 16) |
            ((self.evs.get("SPE",  0) & 0xFF) << 24)
        )
        e1 = (mem.u32[base + _E1] & 0xFFFF0000) | (self.evs.get("SPA", 0) & 0xFF) | ((self.evs.get("SPDEF", 0) & 0xFF) << 8)
        mem.u32[base + _E0] = e0
        mem.u32[base + _E1] = e1
        mem.u16[base + 0x1C] = _checksum(mem, base)

        level  = mem.u8[base + _LEVEL]
        nature = mem.u32[base + _PID] % 25
        stats  = _calc_all_stats(self.species_id, self.evs, level, nature)
        mem.u16[base + _MAXHP] = stats["MAXHP"]
        mem.u16[base + _CURHP] = stats["MAXHP"]
        mem.u16[base + _ATK]   = stats["ATK"]
        mem.u16[base + _DEF]   = stats["DEF"]
        mem.u16[base + _SPE]   = stats["SPE"]
        mem.u16[base + _SPA]   = stats["SPA"]
        mem.u16[base + _SPDEF] = stats["SPDEF"]


@dataclass
class TeamConfig:
    members: list[PokemonConfig]

    @classmethod
    def from_mem(cls, mem) -> "TeamConfig":
        count = mem.u8[PARTY_COUNT_ADDR]
        return cls(members=[PokemonConfig.from_mem(mem, i) for i in range(count)])

    def apply(self, mem) -> None:
        for slot, cfg in enumerate(self.members):
            cfg.apply(mem, slot)
