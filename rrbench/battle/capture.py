from dataclasses import dataclass

from rrbench.emulator.emulator import Emulator, KEY_A, KEY_B
from rrbench.emulator.memory import Party, SPECIES_NAME, species_label
from rrbench.battle.addresses import (
    EWRAM_BASE, MSG_BUFFER,
    BATTLE_TYPE_FLAGS, BATTLE_MONS_BASE, OPP_MON_BASE,
    MON_SPECIES, MON_CUR_HP, MON_MAX_HP,
    INTRO_TEXT_ADVANCE_PRESSES, INTRO_SETTLE_FRAMES,
)
from rrbench.battle.control import (
    ACTION_PROMPT_BYTES,
    BattleControlState,
    MENU_SENTINEL,
    decode_msg,
    read_battle_control_state,
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
    party_hp: dict                     # {canonical label: (current_hp, max_hp)}
    opp_hp: tuple | None               # (current_hp, max_hp) of the opponent active, or None
    opp_species: str                   # opponent active when this message showed (can change mid-turn)


# Species names alone appear in the message buffer during send-out ("Hippowdon"); skip them
# so a send-out doesn't register as a message event.
_SPECIES_NAMES = {n for n in SPECIES_NAME.values() if n}


def hp_snapshot(mem, active_party: Party) -> tuple[dict, tuple | None, str]:
    """
    Read HP for all party Pokemon and the active opponent Pokemon.
    """
    active_party.refresh()
    party_hp = {p.label: (p.current_hp, p.max_hp) for p in active_party.members}

    active_species = mem.u16[BATTLE_MONS_BASE + MON_SPECIES]
    active_label = species_label(active_species)
    if active_label in party_hp:
        party_hp[active_label] = (mem.u16[BATTLE_MONS_BASE + MON_CUR_HP],
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
        self.last_message: str | None = None

    @property
    def started(self) -> bool:
        return bool(self.events)

    def poll(self, emu: Emulator, active_party: Party) -> bool:
        """
        Sample the message buffer + HP of party Pokemon and opposing Pokemon once.
        Returns whether we end up on the battle menu.
        """
        off = MSG_BUFFER - EWRAM_BASE
        msg = decode_msg(bytes(emu.mem.wram[off:off + ACTION_PROMPT_BYTES]))
        is_menu = MENU_SENTINEL in msg
        party_hp, opp_hp, opp_species = hp_snapshot(emu.mem, active_party)

        if self.events:
            cur = self.events[-1]
            cur.party_hp, cur.opp_hp, cur.opp_species = party_hp, opp_hp, opp_species

        # A new, distinct message opens a new event. Bare species names (send-out text)
        # and the "What will X do?" menu are not messages.
        is_message = msg and not is_menu and msg not in _SPECIES_NAMES
        if is_message and msg != self.last_message:
            self.events.append(MessageEvent(msg, party_hp, opp_hp, opp_species))
            self.last_message = msg
        elif not is_message:
            self.last_message = None
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
    action_select_frames = 0
    for _ in range(max_polls):
        rec.poll(emu, active_party)

        # The battle flag is authoritative for terminal state. Check it before
        # honoring any stale UI text because the ROM can clear the flag while
        # the final message is still displayed.
        if emu.mem.u32[BATTLE_TYPE_FLAGS] == 0:
            active_party.refresh()
            opponent_fainted = emu.mem.u16[OPP_MON_BASE + MON_CUR_HP] == 0
            player_survived = any(pokemon.current_hp > 0 for pokemon in active_party.members)
            return rec.events, True, opponent_fainted and player_survived

        control_state = read_battle_control_state(emu.mem)
        if control_state is BattleControlState.REPLACEMENT_SELECT:
            # The game, rather than HP heuristics, tells us that SEND is now
            # the only legal command. This also handles living Pokemon whose
            # ability forces a switch.
            return rec.events, False, False

        if control_state is BattleControlState.ACTION_SELECT:
            # Require the prompt to remain present for a short settle period;
            # this prevents returning during a transition that briefly leaves
            # stale menu text in the buffer.
            action_select_frames += step_frames
            if action_select_frames >= 120:
                return rec.events, False, False
            emu.step(step_frames)
            continue

        action_select_frames = 0
        emu.press(KEY_B, hold_frames=1)
        emu.step(step_frames)
    return rec.events, False, False


def capture_intro(emu: Emulator, active_party: Party) -> list[MessageEvent]:
    """
    Capture the intro/setup text (send-outs, abilities, weather) with the A-press-then-
    settle sequence, polling for messages throughout. Returns the captured events.
    """
    rec = TurnRecorder()
    for _ in range(INTRO_TEXT_ADVANCE_PRESSES):
        emu.press(KEY_B, hold_frames=3)
        for _ in range(5):
            emu.step(8)
            rec.poll(emu, active_party)
    for _ in range(INTRO_SETTLE_FRAMES // 8):
        emu.step(8)
        if rec.poll(emu, active_party) and rec.started:
            break
    emu.step(30)   # let the battle menu become input-ready before the first action
    return rec.events
