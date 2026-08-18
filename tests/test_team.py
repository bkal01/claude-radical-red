from rrbench.emulator.memory import (
    PARTY_BASE_ADDR,
    PARTY_COUNT_ADDR,
    PARTY_MAX_SIZE,
    SLOT_SIZE,
)
from rrbench.team import PokemonConfig, TeamConfig


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
