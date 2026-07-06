from dataclasses import dataclass

from rrbench.emulator.emulator import Emulator, KEY_A, KEY_B
from rrbench.emulator.memory import Party, SPECIES_NAME
from rrbench.battle.addresses import (
    _EWRAM_BASE, MSG_BUFFER, MENU_SENTINEL,
    BATTLE_TYPE_FLAGS, BATTLE_MONS_BASE, OPP_MON_BASE,
    MON_SPECIES, MON_CUR_HP, MON_MAX_HP,
    INTRO_A_PRESSES, INTRO_SETTLE_FRAMES,
)

@dataclass
class MessageEvent:
    """
    One on-screen battle message plus the HP state captured while it was displayed.
    We capture HP state at the message-level because things like Sandstorm, Poison, Burn, etc.
    cause HP tick damage before returning to the battle menu and the agent needs this context
    so it doesn't inflate damage numbers.
    """
    text: str
    party_hp: dict                     # {name: (current_hp, max_hp)}
    opp_hp: tuple | None               # (current_hp, max_hp) of the opponent active, or None
    opp_species: str                   # opponent active when this message showed (can change mid-turn)


# Species names alone appear in the message buffer during send-out ("Hippowdon"); skip them
# so a send-out doesn't register as a message event.
_SPECIES_NAMES = {n for n in SPECIES_NAME.values() if n}


def decode_msg(raw: bytes) -> str:
    """
    Decode a raw buffer message to a single clean line.
    """
    out = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0xFF:
            break
        if 0xBB <= b <= 0xD4:   out.append(chr(ord('A') + b - 0xBB))
        elif 0xD5 <= b <= 0xEE: out.append(chr(ord('a') + b - 0xD5))
        elif b in (0x00, 0xA0): out.append(' ')
        elif b == 0xAD:         out.append('.')
        elif b == 0xAE:         out.append('-')
        elif 0xA1 <= b <= 0xAA: out.append(str(b - 0xA1))
        elif b == 0xFE:         out.append(' ')
        elif b == 0xFB:         pass
        elif b == 0xFC:         i += 1
        elif b == 0xFD:         i += 1
        elif b == 0x5B:         out.append('%')
        elif b == 0xB4:         out.append("'")
        elif b == 0xB8:         out.append(',')
        elif b == 0xAB:         out.append('!')
        elif b == 0xAC:         out.append('?')
        i += 1
    return ' '.join(''.join(out).split())


def hp_snapshot(mem, active_party: Party) -> tuple[dict, tuple | None, str]:
    """
    Read HP for all party Pokemon and the active opponent Pokemon.
    """
    active_party.refresh()
    party_hp = {p.name: (p.current_hp, p.max_hp) for p in active_party.members}

    active_species = mem.u16[BATTLE_MONS_BASE + MON_SPECIES]
    active_name = SPECIES_NAME.get(active_species)
    if active_name in party_hp:
        party_hp[active_name] = (mem.u16[BATTLE_MONS_BASE + MON_CUR_HP],
                                 mem.u16[BATTLE_MONS_BASE + MON_MAX_HP])

    opp_cur = mem.u16[OPP_MON_BASE + MON_CUR_HP]
    opp_max = mem.u16[OPP_MON_BASE + MON_MAX_HP]
    opp_hp = (opp_cur, opp_max) if 0 <= opp_cur <= opp_max <= 2000 else None
    opp_sp = mem.u16[OPP_MON_BASE + MON_SPECIES]
    opp_species = SPECIES_NAME.get(opp_sp, f"species_{opp_sp}")
    return party_hp, opp_hp, opp_species


class TurnRecorder:
    """
    Poll the message buffer and build a list of MessageEvents.
    In each poll, we check text/HP and dedup accordingly.
    We poll until we reach the battle menu.
    """

    def __init__(self) -> None:
        self.events: list[MessageEvent] = []

    @property
    def started(self) -> bool:
        return bool(self.events)

    def poll(self, emu: Emulator, active_party: Party) -> bool:
        """
        Sample the message buffer + HP of party Pokemon and opposing Pokemon once.
        Returns whether we end up on the battle menu.
        """
        off = MSG_BUFFER - _EWRAM_BASE
        msg = decode_msg(bytes(emu.mem.wram[off:off + 160]))
        is_menu = MENU_SENTINEL in msg
        party_hp, opp_hp, opp_species = hp_snapshot(emu.mem, active_party)

        if self.events:
            cur = self.events[-1]
            cur.party_hp, cur.opp_hp, cur.opp_species = party_hp, opp_hp, opp_species

        # A new, distinct message opens a new event. Bare species names (send-out text)
        # and the "What will X do?" menu are not messages.
        is_message = msg and not is_menu and msg not in _SPECIES_NAMES
        if is_message and (not self.events or msg != self.events[-1].text):
            self.events.append(MessageEvent(msg, party_hp, opp_hp, opp_species))
        return is_menu


def capture_turn(
    emu: Emulator,
    active_party: Party,
    max_polls: int = 400,
    step_frames: int = 4
) -> tuple[list[MessageEvent], bool, bool]:
    """
    Advance a turn's text with B, capturing messages. Returns (events, ended, won).
    Stops on the battle menu, on the forced-replacement screen, or on battle end.
    Returns the MessageEvents for the turn, along with whether battle is over and
    if it's a victory.
    """
    rec = TurnRecorder()
    faint_flushes = 0
    for _ in range(max_polls):
        is_menu = rec.poll(emu, active_party)

        if is_menu and rec.started:
            emu.step(30)   # let the menu become input-ready before the caller acts
            return rec.events, False, False

        if emu.mem.u32[BATTLE_TYPE_FLAGS] == 0:
            won = emu.mem.u16[BATTLE_MONS_BASE + MON_CUR_HP] > 0
            return rec.events, True, won

        # A fainted active reads 0 HP well before the "choose next Pokemon" screen opens.
        # Advance with a long settle to flush faint text and let that screen appear, then
        # give up so the caller inherits the now-open party screen for the replacement.
        if emu.mem.u16[BATTLE_MONS_BASE + MON_CUR_HP] == 0:
            emu.press(KEY_B, hold_frames=1)
            emu.step(60)
            faint_flushes += 1
            if faint_flushes >= 12:
                return rec.events, False, False
            continue

        emu.press(KEY_B, hold_frames=1)
        emu.step(step_frames)
    return rec.events, False, False


def capture_intro(emu: Emulator, active_party: Party) -> list[MessageEvent]:
    """
    Capture the intro/setup text (send-outs, abilities, weather) with the A-press-then-
    settle sequence, polling for messages throughout. Returns the captured events.
    """
    rec = TurnRecorder()
    for _ in range(INTRO_A_PRESSES):
        emu.press(KEY_A, hold_frames=3)
        for _ in range(5):
            emu.step(8)
            rec.poll(emu, active_party)
    for _ in range(INTRO_SETTLE_FRAMES // 8):
        emu.step(8)
        if rec.poll(emu, active_party) and rec.started:
            break
    emu.step(30)   # let the battle menu become input-ready before the first action
    return rec.events
