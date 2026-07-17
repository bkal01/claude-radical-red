from rrbench.emulator.emulator import (
    Emulator,
    KEY_A, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
)
from rrbench.emulator.memory import Party
from rrbench.battle.addresses import LAST_MOVES
from rrbench.battle.capture import MessageEvent, capture_intro, capture_turn
from rrbench.battle.state import BattleSession, BattleState, StepLog, in_battle, read_battle_state


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
        emu.step()
        emu._core.set_keys()

    # Advance dialogue until the battle actually starts. Hold A for 3 frames (registers
    # the press + speeds text scroll), then release for 20 so the game processes the edge.
    for _ in range(120):
        if in_battle(emu.mem):
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
        party=party,
    )
    return session, battle_state, intro_messages

def fight(emu: Emulator, move_name: str, active_party: Party, active_slot: int) -> None:
    move_slot = active_party.members[active_slot].moves.index(move_name)
    row, col  = divmod(move_slot, 2)   # 2-column move grid: slot 0→(0,0), 1→(0,1), 2→(1,0), 3→(1,1)

    emu.press(KEY_A)      # open Fight submenu
    emu.step(20)          # wait for submenu to fully open
    # cursor persists from prior turn; reset to top-left before navigating
    emu.press(KEY_UP)
    emu.step(8)
    emu.press(KEY_LEFT)
    emu.step(8)
    for _ in range(row):
        emu.press(KEY_DOWN)
        emu.step(8)
    for _ in range(col):
        emu.press(KEY_RIGHT)
        emu.step(8)
    emu.press(KEY_A)      # confirm move


def _nav_party_slot(emu: Emulator, target: int) -> None:
    # Party screen is a 2x3 grid, slot n is at row=n//2, col=n%2
    # Party screen is a 2×3 grid: slot n is at row=n//2, col=n%2.
    # The cursor persists between party screen openings, so reset to slot 0 first.
    # Assumes no wrap at edges (UP at row 0 stays, LEFT at col 0 stays).
    # for _ in range(3):
    #     emu.press(KEY_UP)
    #     emu.step(8)
    # for _ in range(2):
    #     emu.press(KEY_LEFT)
    #     emu.step(8)
    row, col = divmod(target, 2)
    for _ in range(row):
        emu.press(KEY_DOWN)
        emu.step(8)
    for _ in range(col):
        emu.press(KEY_RIGHT)
        emu.step(8)


def switch(emu: Emulator, pokemon_name: str, active_party: Party) -> None:
    """
    Switch pokemon_name in for the active pokemon.
    """
    # Use the visual display slot, not the EWRAM slot. After a forced replacement
    # Radical Red caches a display order that diverges from EWRAM (see send() below).
    # Validate before any key press so an invalid target can't desync the menu.
    target = active_party.resolve_switch_target(pokemon_name)
    emu.press(KEY_DOWN)   # FIGHT → POKÉMON in the 2×2 battle menu
    emu.step(15)
    emu.press(KEY_A)      # open party screen
    emu.step(80)          # wait for party screen transition to complete (~60 frames)
    _nav_party_slot(emu, target)
    emu.press(KEY_A)      # select Pokemon → SHIFT/CANCEL submenu
    emu.step(20)
    emu.press(KEY_A)      # confirm SHIFT
    emu.step(60)          # allow party screen to close before caller's B-press loop starts
    # Radical Red updates its display cache on voluntary switches the same way it does for
    # forced replacements: the switched-in pokemon swaps to display slot 0.
    active_party.update_display_after_send(pokemon_name)


def send(emu: Emulator, pokemon_name: str, active_party: Party) -> None:
    """
    Forced replacement — party screen is already open after a faint.
    The faint animation may still be playing; wait for the party screen to appear first.

    Radical Red reorders EWRAM when the active Pokemon faints (fainted mons go to the
    front), and the party screen shows that reordered layout. After the player selects a
    replacement at display slot S, the game caches a new display order with the sent-in
    Pokemon at slot 0 (swap of slots 0 and S) — but EWRAM is then restored to its
    pre-faint order. Future voluntary-switch party screens use the cached display order,
    not the current EWRAM order, so we must track it explicitly.
    """
    # At this point active_party.members already reflects the faint-reordered EWRAM
    # (captured by the top-of-loop refresh()). Sync display_pos to that same order so
    # the visual slot == EWRAM slot, which is true at forced-replacement time.
    active_party.resolve_switch_target(pokemon_name)
    active_party._sync_display_to_ewram()
    target = active_party.get_display_slot(pokemon_name)
    emu.step(80)          # wait for party screen transition to complete
    _nav_party_slot(emu, target)
    emu.press(KEY_A)      # select → SEND OUT submenu
    emu.step(20)
    emu.press(KEY_A)      # confirm SEND OUT
    emu.step(60)
    # Game swaps display order: sent-in Pokemon → slot 0, old slot-0 → sent-in's old slot.
    active_party.update_display_after_send(pokemon_name)

def execute(
    emu: Emulator,
    action_type: str,
    action_arg: str,
    active_party: Party,
    active_slot: int
) -> None:
    if action_type == "FIGHT":
        fight(emu, action_arg, active_party, active_slot)
    elif action_type == "SWITCH":
        switch(emu, action_arg, active_party)
    elif action_type == "SEND":
        send(emu, action_arg, active_party)
    else:
        raise ValueError(f"Unknown action type: {action_type!r}")

def do_action(
    emu: Emulator,
    party: Party,
    session: BattleSession,
    action_type: str,
    action_arg: str,
) -> tuple[BattleSession, BattleState, StepLog]:
    """
    Execute the given `action` from the agent in the environment.
    Returns the StepLog from the action, along with an updated BattleSession.
    """
    party.refresh()
    battle_state = read_battle_state(
        mem=emu.mem,
        party=party,
    )

    if not action_arg:
        raise ValueError("Action must be FIGHT, SWITCH, or SEND followed by a name")
    execute(emu, action_type, action_arg, party, battle_state.active_slot)
    messages, ended, won = capture_turn(emu, party)
    session.ended, session.won = ended, won
    session.num_steps += 1

    opp_move = emu.mem.u16[LAST_MOVES + 2]
    step_log = StepLog(
        step=session.num_steps,
        action=f"{action_type} {action_arg}",
        opponent_move=opp_move,
        hp_snapshot=tuple((p.current_hp, p.max_hp) for p in party.members),
        opp_species=battle_state.opp_species,
        opp_species_id=battle_state.opp_species_id,
        opp_ability=battle_state.opp_ability,
        messages=messages,
    )
    new_battle_state = read_battle_state(
        mem=emu.mem,
        party=party,
    )
    session.active_slot = new_battle_state.active_slot
    
    return session, new_battle_state, step_log
