from rrbench.emulator.memory import (
    PARTY_BASE_ADDR,
    PARTY_COUNT_ADDR,
    PARTY_MAX_SIZE,
    SLOT_SIZE,
    checksum,
)
from rrbench.team import PokemonConfig, TeamConfig, _SPECIES_TABLE_SIZE


def test_checksum_collision_skips_reserved_species_ids(party_memory) -> None:
    base = PARTY_BASE_ADDR
    # Make the checksum 251 before PokemonConfig.apply(). The old guard would
    # stop at the unmapped-but-ROM-readable ID 252.
    for offset in range(0x20, 0x50, 4):
        party_memory.load_u32(base + offset, 0)
    party_memory.load_u32(base + 0x20, 1)
    party_memory.load_u32(base + 0x24, 250)

    PokemonConfig(
        species_id=1,
        evs={key: 0 for key in ("HP", "ATK", "DEF", "SPE", "SPA", "SPDEF")},
        level=1,
        nature_id=0,
        move_ids=None,
    ).apply(party_memory, 0)

    assert checksum(party_memory, base) == _SPECIES_TABLE_SIZE
    assert checksum(party_memory, base) != 252


def test_applying_smaller_team_erases_unused_party_slots(party_memory) -> None:
    party_memory.load_u8(PARTY_COUNT_ADDR, PARTY_MAX_SIZE)
    for slot in range(2, PARTY_MAX_SIZE):
        base = PARTY_BASE_ADDR + slot * SLOT_SIZE
        for offset in range(0, SLOT_SIZE, 4):
            party_memory.load_u32(base + offset, 0xDEADBEEF)

    TeamConfig(members=[PokemonConfig.from_mem(party_memory, 0)]).apply(party_memory)

    assert party_memory.u8[PARTY_COUNT_ADDR] == 1
    for slot in range(1, PARTY_MAX_SIZE):
        base = PARTY_BASE_ADDR + slot * SLOT_SIZE
        assert all(
            party_memory.u32[base + offset] == 0
            for offset in range(0, SLOT_SIZE, 4)
        )
