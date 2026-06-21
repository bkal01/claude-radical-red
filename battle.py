from dataclasses import dataclass, field
from emulator import Emulator, KEY_A, KEY_B, KEY_DOWN, KEY_RIGHT, KEY_UP
import memory


# EWRAM addresses — verified empirically against the Radical Red ROM.
_BATTLE_TYPE_FLAGS = 0x02022B4C  # u32: non-zero while in a trainer battle; clears when battle ends
_LAST_MOVES        = 0x02023D90  # u16[4]: chosen/last-used move ID per battler slot (battler 1 = opponent)
# Note: _BATTLE_OUTCOME at 0x02022B70 (assumed vanilla+shift) always reads 0.
# Battle end is detected via _BATTLE_TYPE_FLAGS → 0, and win/loss by reading party HP at that moment.

# Frame budgets
_INTRO_A_PRESSES    = 30   # A presses after battle flag to advance trainer/send-out dialogue
_INTRO_SETTLE_FRAMES = 500  # additional wait for auto-advancing messages (Intimidate, weather)
_TURN_WAIT_B_PRESSES = 30  # B presses per turn: advances text boxes; safe on battle menu (cursor stays at FIGHT)
_POLL_FRAMES        = 5    # poll _BATTLE_TYPE_FLAGS every N frames inside the B-press loop

# Move name → ID for this benchmark's moveset.
# Radical Red IDs may differ from canonical Bulbapedia values; verify empirically.
_MOVE_ID = {
    "Fake Out": 252, "Taunt": 269, "Flare Blitz": 434, "Darkest Lariat": 585,
    "Crunch": 242,  "Aqua Tail": 358, "Ice Fang": 432,
    "Play Nice": 491, "Power Whip": 390, "Hi Jump Kick": 136, "Rapid Spin": 229,
    "Iron Head": 382, "Play Rough": 463, "Sucker Punch": 458, "Rock Slide": 157,
    "Kowtow Cleave": 784, "Assurance": 485,
    "Calm Mind": 347, "Psychic": 94, "Armor Cannon": 769, "Will-o-Wisp": 261,
}

# Species ID → name for the benchmark team.
# Uses national dex numbers, which Radical Red stores in EWRAM — verify empirically.
_SPECIES_NAME = {
    130: "Gyarados",  355: "Mawile",
    935: "Armarouge", 936: "Kingambit",
    944: "Incineroar", 980: "Tsareena",
}


def _build_slot_map(mem) -> dict[str, int]:
    """Map Pokemon name → current party slot index by reading live party data."""
    return {
        _SPECIES_NAME[p.species]: i
        for i, p in enumerate(memory.read_party(mem))
        if p.species in _SPECIES_NAME
    }


@dataclass
class StepLog:
    step: int
    action: str          # e.g. "FIGHT Ice Fang", "SWITCH Gyarados", "SEND Mawile"
    opponent_move: int   # last move ID used by battler 1; 0 if undetected
    hp_snapshot: tuple   # ((current_hp, max_hp), ...) per party slot after this step


@dataclass
class BattleResult:
    won: bool
    turns: int
    pokemon_remaining: int
    steps: list[StepLog] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hp_snapshot(mem) -> tuple:
    return tuple((p.current_hp, p.max_hp) for p in memory.read_party(mem))


def _battle_active(mem) -> bool:
    return mem.u32[_BATTLE_TYPE_FLAGS] != 0


def _find_move_slot(mem, move_id: int, active_slot: int) -> int:
    poke = memory.read_slot(mem, active_slot)
    for i, mid in enumerate(poke.moves):
        if mid == move_id:
            return i
    raise ValueError(f"Move ID {move_id} not in party slot {active_slot}'s moveset")


def _parse_action(action: str) -> tuple[str, list[str]]:
    parts = action.split()
    return parts[0], parts[1:]


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------

def _fight(emu: Emulator, move_name: str, active_slot: int) -> None:
    move_id   = _MOVE_ID[move_name]
    move_slot = _find_move_slot(emu.mem, move_id, active_slot)
    row, col  = divmod(move_slot, 2)   # 2-column move grid: slot 0→(0,0), 1→(0,1), 2→(1,0), 3→(1,1)

    emu.press(KEY_A)      # open Fight submenu
    emu.step(20)          # wait for submenu to fully open
    for _ in range(row):
        emu.press(KEY_DOWN)
        emu.step(8)
    for _ in range(col):
        emu.press(KEY_RIGHT)
        emu.step(8)
    emu.press(KEY_A)      # confirm move


def _nav_party_slot(emu: Emulator, target: int) -> None:
    # Party screen is a 2×3 grid: slot n is at row=n//2, col=n%2.
    row, col = divmod(target, 2)
    for _ in range(row):
        emu.press(KEY_DOWN)
        emu.step(8)
    for _ in range(col):
        emu.press(KEY_RIGHT)
        emu.step(8)


def _switch(emu: Emulator, pokemon_name: str, slot_of: dict[str, int]) -> None:
    target = slot_of[pokemon_name]
    emu.press(KEY_DOWN)   # FIGHT → POKÉMON in the 2×2 battle menu
    emu.step(15)
    emu.press(KEY_A)      # open party screen
    emu.step(80)          # wait for party screen transition to complete (~60 frames)
    _nav_party_slot(emu, target)
    emu.press(KEY_A)      # select Pokemon → SHIFT/CANCEL submenu
    emu.step(20)
    emu.press(KEY_A)      # confirm SHIFT
    emu.step(60)          # allow party screen to close before caller's B-press loop starts


def _send(emu: Emulator, pokemon_name: str, slot_of: dict[str, int]) -> None:
    """Forced replacement — party screen is already open after a faint.
    The faint animation may still be playing; wait for the party screen to appear first."""
    target = slot_of[pokemon_name]
    emu.step(80)          # wait for party screen transition to complete
    _nav_party_slot(emu, target)
    emu.press(KEY_A)      # select → SEND OUT submenu
    emu.step(20)
    emu.press(KEY_A)      # confirm SEND OUT
    emu.step(60)


def _execute(emu: Emulator, action: str, slot_of: dict[str, int], active_slot: int) -> None:
    kind, args = _parse_action(action)
    if kind == "FIGHT":
        _fight(emu, " ".join(args), active_slot)
    elif kind == "SWITCH":
        _switch(emu, args[0], slot_of)
    elif kind == "SEND":
        _send(emu, args[0], slot_of)
    elif kind == "ITEM":
        raise NotImplementedError("ITEM actions are not yet implemented")
    else:
        raise ValueError(f"Unknown action kind: {kind!r}")


def _b_press_loop(emu: Emulator) -> tuple[bool, tuple | None, int]:
    """
    Press B up to _TURN_WAIT_B_PRESSES times to advance text boxes.
    Polls _BATTLE_TYPE_FLAGS every _POLL_FRAMES frames.
    When the battle ends (flags → 0), immediately captures party HP and opponent move
    before EWRAM is overwritten by the post-battle sequence.

    Returns: (battle_ended, hp_snapshot_at_end, opponent_move_at_end)
    If battle is still ongoing: (False, None, last_opponent_move)
    """
    frames_per_press = 60 // _POLL_FRAMES
    for _ in range(_TURN_WAIT_B_PRESSES):
        emu.press(KEY_B, hold_frames=1)
        for _ in range(frames_per_press):
            emu.step(_POLL_FRAMES)
            if not _battle_active(emu.mem):
                hp_snap    = _hp_snapshot(emu.mem)
                opp_move   = emu.mem.u16[_LAST_MOVES + 2]
                return True, hp_snap, opp_move
    opp_move = emu.mem.u16[_LAST_MOVES + 2]
    return False, None, opp_move


def run(emu: Emulator, action_sequence: list[str]) -> BattleResult:
    """
    Execute one full Giovanni battle attempt using the given action sequence.

    action_sequence entries:
      FIGHT <move_name>  — voluntary move from the battle menu
      SWITCH <pokemon>   — voluntary switch from the battle menu
      SEND <pokemon>     — forced replacement after a faint

    Battle end is detected by polling _BATTLE_TYPE_FLAGS every 5 frames inside
    the post-action B-press loop. When the flags clear, party HP is read immediately
    (before EWRAM is overwritten) to determine win/loss.
    """
    # Walk into the room to trigger Giovanni's encounter script.
    for _ in range(60):
        emu._core.set_keys(KEY_UP)
        emu._core.run_frame()
        emu._core.set_keys()

    # Advance through Giovanni's dialogue until the battle flag is set.
    # Hold A for 3 frames (registers the press + speeds up text scroll),
    # then release for 20 frames so the game can process the edge.
    for _ in range(120):
        if _battle_active(emu.mem):
            break
        emu.press(KEY_A, hold_frames=3)
        emu.step(20)
    else:
        raise RuntimeError("Battle did not start — check the save state position")

    # Advance trainer intro and send-out dialogue with A, then let auto-advance
    # messages (Intimidate, weather abilities) finish on their own.
    for _ in range(_INTRO_A_PRESSES):
        emu.press(KEY_A, hold_frames=3)
        emu.step(40)
    emu.step(_INTRO_SETTLE_FRAMES)

    slot_of     = _build_slot_map(emu.mem)
    active_slot = 0  # lead is always party slot 0; updated after each switch

    steps   = []
    won     = False
    ended   = False

    for i, action in enumerate(action_sequence):
        _execute(emu, action, slot_of, active_slot)
        ended, end_hp, opp_move = _b_press_loop(emu)

        kind, args = _parse_action(action)
        if kind in ("SWITCH", "SEND"):
            active_slot = slot_of[args[0]]

        # Use HP captured at flags-clear when the battle ended; otherwise read current EWRAM.
        hp_snap = end_hp if ended else _hp_snapshot(emu.mem)
        steps.append(StepLog(
            step=i + 1,
            action=action,
            opponent_move=opp_move,
            hp_snapshot=hp_snap,
        ))

        if ended:
            # won = any party pokemon still standing at the exact frame the battle ended
            won = any(hp > 0 for hp, _ in hp_snap)
            break

    final_hp = steps[-1].hp_snapshot if steps else _hp_snapshot(emu.mem)
    pokemon_remaining = sum(1 for hp, _ in final_hp if hp > 0)
    return BattleResult(
        won=won,
        turns=len(steps),
        pokemon_remaining=pokemon_remaining,
        steps=steps,
    )
