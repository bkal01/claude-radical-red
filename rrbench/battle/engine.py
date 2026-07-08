from rrbench.emulator.emulator import Emulator, KEY_A, KEY_UP
from rrbench.emulator.memory import Party
from rrbench.battle.addresses import BATTLE_TYPE_FLAGS
from rrbench.battle.capture import MessageEvent, capture_intro
from rrbench.battle.state import BattleSession, BattleState, read_battle_state


def start_battle(emu: Emulator, party: Party, lead: str) -> tuple[BattleSession, BattleState, list[MessageEvent]]:
    """
    Put `lead` at the front of the party, trigger the encounter, and advance through all
    pre-battle dialogue. Returns the ready-to-act session plus the intro messages
    (send-outs, Intimidate, weather) captured while the battle opened.
    """
    # TODO: Generalize past Giovanni — the walk + dialogue script is battle-specific.
    party.set_lead(lead)

    # Walk up into the room to trigger the encounter script.
    for _ in range(60):
        emu._core.set_keys(KEY_UP)
        emu._core.run_frame()
        emu._core.set_keys()

    # Advance dialogue until the battle actually starts. Hold A for 3 frames (registers
    # the press + speeds text scroll), then release for 20 so the game processes the edge.
    for _ in range(120):
        if emu.mem.u32[BATTLE_TYPE_FLAGS] != 0:
            break
        emu.press(KEY_A, hold_frames=3)
        emu.step(20)
    else:
        raise RuntimeError("Battle did not start — check the save state position")

    intro_messages = capture_intro(emu, party)
    party.refresh()

    session = BattleSession(emu=emu, party=party, active_slot=0)

    battle_state = read_battle_state(
        mem=emu.mem,
        active_slot=0,
        poke_party=party.members,
    )
    return session, battle_state, intro_messages
