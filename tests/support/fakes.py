from collections.abc import Callable

from rrbench.battle.addresses import EWRAM_BASE, EWRAM_SIZE


class MemoryView:
    """
    this is a simplified copy of `MemoryView` from mgba Python bindings
    it's basically mem.u8, mem.u16, and mem.u32 from rrbench prod code
    and is a convenient way to index into memory in tests
    """
    def __init__(self, memory, width: int) -> None:
        self.memory = memory
        self.width = width

    def __getitem__(self, address: int) -> int:
        return int.from_bytes(self.memory.read(address, self.width), "little")

    def __setitem__(self, address: int, value: int) -> None:
        self.memory.load_value(address, value, self.width)


class FakeMemory:
    """
    a test version of `mem` in rrbench prod code
    """
    def __init__(self) -> None:
        self.wram = bytearray(EWRAM_SIZE)
        self.other_bytes: dict[int, int] = {}
        self.u8 = MemoryView(self, 1)
        self.u16 = MemoryView(self, 2)
        self.u32 = MemoryView(self, 4)

    def read(self, address: int, width: int) -> bytes:
        values = []
        for byte_address in range(address, address + width):
            if EWRAM_BASE <= byte_address < EWRAM_BASE + EWRAM_SIZE:
                values.append(self.wram[byte_address - EWRAM_BASE])
            else:
                values.append(self.other_bytes.get(byte_address, 0))
        return bytes(values)

    def load_bytes(self, address: int, values: bytes) -> None:
        for offset, value in enumerate(values):
            byte_address = address + offset
            if EWRAM_BASE <= byte_address < EWRAM_BASE + EWRAM_SIZE:
                self.wram[byte_address - EWRAM_BASE] = value
            else:
                self.other_bytes[byte_address] = value

    def load_value(self, address: int, value: int, width: int) -> None:
        self.load_bytes(address, value.to_bytes(width, "little"))

    def load_u8(self, address: int, value: int) -> None:
        self.load_value(address, value, 1)

    def load_u16(self, address: int, value: int) -> None:
        self.load_value(address, value, 2)

    def load_u32(self, address: int, value: int) -> None:
        self.load_value(address, value, 4)

    def snapshot(self) -> tuple[bytes, dict[int, int]]:
        return bytes(self.wram), dict(self.other_bytes)

    def restore(self, snapshot: tuple[bytes, dict[int, int]]) -> None:
        wram, other_bytes = snapshot
        self.wram[:] = wram
        self.other_bytes = dict(other_bytes)


class FakeEmulator:
    def __init__(self, memory: FakeMemory) -> None:
        self.mem = memory
        self.calls: list[tuple] = []
        self.recorder = None
        self.saved_state = memory.snapshot()
        self.press_callback: Callable[[FakeEmulator, int, int], None] | None = None
        self.step_callback: Callable[[FakeEmulator, int], None] | None = None

    def press(self, key: int, hold_frames: int = 1) -> None:
        self.calls.append(("press", key, hold_frames))
        if self.press_callback is not None:
            self.press_callback(self, key, hold_frames)

    def step(self, frames: int) -> None:
        self.calls.append(("step", frames))
        if self.step_callback is not None:
            self.step_callback(self, frames)

    def set_recorder(self, recorder) -> None:
        self.recorder = recorder

    def load_state(self) -> None:
        self.mem.restore(self.saved_state)


class FakeService:
    def __init__(self, results: dict[str, dict] | None = None) -> None:
        self.emu = FakeEmulator(FakeMemory())
        self.calls: list[tuple] = []
        self.results = results or {}

    def configured_result(self, operation: str) -> dict:
        return self.results.get(operation, {"ok": True})

    def observe(self) -> dict:
        self.calls.append(("observe",))
        return self.configured_result("observe")

    def team(self) -> dict:
        self.calls.append(("team",))
        return self.configured_result("team")

    def lead(self, pokemon: str) -> dict:
        self.calls.append(("lead", pokemon))
        return self.configured_result("lead")

    def action(self, command: str) -> dict:
        self.calls.append(("action", command))
        return self.configured_result("action")

    def reset(self) -> dict:
        self.calls.append(("reset",))
        return self.configured_result("reset")

    def apply_team(self, team: dict) -> dict:
        self.calls.append(("apply_team", team))
        return self.configured_result("apply_team")


class FakeVideoRecorder:
    instances: list["FakeVideoRecorder"] = []

    def __init__(self, output_path: str) -> None:
        self.output_path = output_path
        self.closed = False
        self.instances.append(self)

    def close(self) -> None:
        self.closed = True
