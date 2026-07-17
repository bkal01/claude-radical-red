from types import SimpleNamespace

from rrbench.battle.addresses import (
    BATTLE_MONS_BASE,
    BATTLE_TYPE_FLAGS,
    MON_CUR_HP,
)
from rrbench.battle.capture import TurnRecorder, capture_turn


class MemoryValues(dict):
    def __getitem__(self, address):
        return self.get(address, 0)


class FakeMemory:
    def __init__(self) -> None:
        self.u16 = MemoryValues({BATTLE_MONS_BASE + MON_CUR_HP: 0})
        self.u32 = MemoryValues({BATTLE_TYPE_FLAGS: 0xC})
        self.wram = bytearray(0x40000)


class FakeEmulator:
    def __init__(self) -> None:
        self.mem = FakeMemory()

    def press(self, key, hold_frames=1) -> None:
        pass

    def step(self, frames) -> None:
        pass


class FakeParty:
    def __init__(self, hp_values: list[int]) -> None:
        self.members = [
            SimpleNamespace(name=f"Pokemon {index}", current_hp=hp, max_hp=100)
            for index, hp in enumerate(hp_values)
        ]

    def refresh(self) -> None:
        pass


def test_capture_turn_marks_loss_when_battle_flag_lingers() -> None:
    events, ended, won = capture_turn(
        FakeEmulator(),
        FakeParty([0, 0, 0, 0, 0, 0]),
        max_polls=12,
    )

    assert events == []
    assert ended is True
    assert won is False


def test_capture_turn_waits_for_replacement_when_party_member_remains() -> None:
    events, ended, won = capture_turn(
        FakeEmulator(),
        FakeParty([0, 25, 0, 0, 0, 0]),
        max_polls=12,
    )

    assert events == []
    assert ended is False
    assert won is False


def test_turn_recorder_keeps_repeated_messages_after_buffer_clears() -> None:
    emulator = FakeEmulator()
    party = FakeParty([100])
    message = "The opposing Kangaskhan's Attack rose!"
    encoded_message = bytes(
        0xBB + ord(character) - ord("A") if "A" <= character <= "Z"
        else 0xD5 + ord(character) - ord("a") if "a" <= character <= "z"
        else 0x00 if character == " "
        else 0xB4 if character == "'"
        else 0xAB if character == "!"
        else 0xFF
        for character in message
    ) + b"\xff"
    message_offset = 0x0202298C - 0x02000000
    emulator.mem.wram[message_offset:message_offset + len(encoded_message)] = encoded_message

    recorder = TurnRecorder()
    recorder.poll(emulator, party)

    emulator.mem.wram[message_offset] = 0xFF
    recorder.poll(emulator, party)

    emulator.mem.wram[message_offset:message_offset + len(encoded_message)] = encoded_message
    recorder.poll(emulator, party)

    assert [event.text for event in recorder.events] == [message, message]
