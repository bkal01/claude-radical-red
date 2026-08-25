from enum import Enum

from rrbench.battle.addresses import MSG_BUFFER, MENU_SENTINEL, REPLACEMENT_PROMPT_BUFFER


class BattleControlState(str, Enum):
    """Which player-controlled battle screen is currently active."""

    ACTION_SELECT = "action_select"
    REPLACEMENT_SELECT = "replacement_select"
    TRANSITION = "transition"


# The battle menu prompt and replacement prompt live in different game buffers.
# These are UI-state indicators, not gameplay-state inferences.
ACTION_PROMPT_BYTES = 160
REPLACEMENT_PROMPT_BYTES = 64
REPLACEMENT_PROMPT = "Choose a Pokémon."
REPLACEMENT_PROMPT_RAW = bytes(
    (0xBD, 0xDC, 0xE3, 0xE3, 0xE7, 0xD9, 0x00, 0xD5, 0x00,
     0xCA, 0xE3, 0xDF, 0x1B, 0xE1, 0xE3, 0xE2, 0xAD, 0xFF)
)


def decode_msg(raw: bytes) -> str:
    """Decode a Radical Red text buffer into one clean line."""
    out = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0xFF:
            break
        if 0xBB <= b <= 0xD4:
            out.append(chr(ord("A") + b - 0xBB))
        elif 0xD5 <= b <= 0xEE:
            out.append(chr(ord("a") + b - 0xD5))
        elif b in (0x00, 0xA0):
            out.append(" ")
        elif b == 0xAD:
            out.append(".")
        elif b == 0xAE:
            out.append("-")
        elif 0xA1 <= b <= 0xAA:
            out.append(str(b - 0xA1))
        elif b == 0xFE:
            out.append(" ")
        elif b == 0xFB:
            pass
        elif b == 0xFC:
            i += 1
        elif b == 0xFD:
            i += 1
        elif b == 0x5B:
            out.append("%")
        elif b == 0xB4:
            out.append("'")
        elif b == 0xB5:
            out.append("♂")
        elif b == 0xB6:
            out.append("♀")
        elif b == 0xB8:
            out.append(",")
        elif b == 0xAB:
            out.append("!")
        elif b == 0xAC:
            out.append("?")
        elif b == 0xF0:
            out.append(":")
        elif b == 0x1B:
            out.append("é")
        i += 1
    return " ".join("".join(out).split())


def _read_text(mem, address: int, length: int) -> str:
    return decode_msg(bytes(mem.u8[address + i] for i in range(length)))


def read_battle_control_state(mem) -> BattleControlState:
    """Read the current player-control screen from the ROM's UI buffers.

    The battle lifecycle flag is intentionally handled separately by
    ``in_battle``.  HP is not used here: a living Pokemon can require a forced
    replacement (for example, Emergency Exit), while a fainted Pokemon is not
    necessarily ready for selection until the replacement screen appears.
    """
    if _read_text(mem, REPLACEMENT_PROMPT_BUFFER, REPLACEMENT_PROMPT_BYTES) == REPLACEMENT_PROMPT:
        return BattleControlState.REPLACEMENT_SELECT

    if MENU_SENTINEL in _read_text(mem, MSG_BUFFER, ACTION_PROMPT_BYTES):
        return BattleControlState.ACTION_SELECT

    return BattleControlState.TRANSITION
