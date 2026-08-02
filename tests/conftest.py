import pytest

from rrbench.emulator.memory import PARTY_BASE_ADDR, PARTY_COUNT_ADDR, SLOT_SIZE
from tests.support.fakes import FakeMemory


@pytest.fixture
def party_memory() -> FakeMemory:
    """
    fake snapshot of a Pokemon party RAM w/Bulbasaur and Incineroar.
    we just give them simple items, abilities, natures, moves, etc. for use in tests.
    """
    memory = FakeMemory()
    memory.load_u8(PARTY_COUNT_ADDR, 2)

    bulbasaur = PARTY_BASE_ADDR
    memory.load_u32(bulbasaur, 0)
    memory.load_u32(bulbasaur + 0x20, 7 << 16 | 1)
    memory.load_u32(bulbasaur + 0x2C, 1 | 45 << 16)
    memory.load_u32(bulbasaur + 0x30, 0)
    memory.load_u32(bulbasaur + 0x34, 10 | 12 << 8)
    memory.load_u32(bulbasaur + 0x48, 0)
    memory.load_u32(bulbasaur + 0x50, 0x08)
    memory.load_u8(bulbasaur + 0x54, 50)
    memory.load_u16(bulbasaur + 0x56, 100)
    memory.load_u16(bulbasaur + 0x58, 120)

    incineroar = PARTY_BASE_ADDR + SLOT_SIZE
    memory.load_u32(incineroar, 1)
    memory.load_u32(incineroar + 0x20, 12 << 16 | 944)
    memory.load_u32(incineroar + 0x2C, 52 | 45 << 16)
    memory.load_u32(incineroar + 0x30, 0)
    memory.load_u32(incineroar + 0x34, 20 | 15 << 8)
    memory.load_u32(incineroar + 0x48, 0x80000000)
    memory.load_u32(incineroar + 0x50, 0)
    memory.load_u8(incineroar + 0x54, 50)
    memory.load_u16(incineroar + 0x56, 88)
    memory.load_u16(incineroar + 0x58, 150)

    return memory
