from collections.abc import Callable
from dataclasses import dataclass, field
from emulator import Emulator, KEY_A, KEY_B, KEY_DOWN, KEY_RIGHT, KEY_UP
import party


# EWRAM addresses — verified empirically against the Radical Red ROM.
BATTLE_TYPE_FLAGS = 0x02022B4C  # u32: non-zero while in a trainer battle; clears when battle ends
LAST_MOVES        = 0x02023D90  # u16[4]: chosen/last-used move ID per battler slot (battler 1 = opponent)
# Note: _BATTLE_OUTCOME at 0x02022B70 (assumed vanilla+shift) always reads 0.
# Battle end is detected via BATTLE_TYPE_FLAGS → 0, and win/loss by reading party HP at that moment.

# Weather — confirmed by watching 0x08 stay constant through all snap0–snap3 in scan_hazards.py.
BATTLE_WEATHER    = 0x02022B50  # u32 bitmask: 0x08 = sandstorm (WEATHER_SANDSTORM_PERMANENT)
WEATHER_TIMER     = 0x02022883  # u8 countdown; decrements each turn (observed 32→31→30)

# gBattleMons — active battler structs (0x58 bytes each, 4 slots).
# Slot 0 = player's active Pokemon; slot 1 = opponent's active Pokemon.
# Confirmed by matching species u16 at base: 0x03B0=944=Incineroar (slot 0), 0x02F7=759=Hippowdon (slot 1).
BATTLE_MONS_BASE  = 0x02023BE4  # gBattleMons[0] base address (player active)
BATTLE_MON_SIZE   = 0x58        # bytes per battler struct

# Offsets within a gBattleMons entry:
_MON_SPECIES     = 0x00  # u16
_MON_ABILITY     = 0x20  # u8 (Intimidate=22, Sand Stream=45)
_MON_STAT_STAGES = 0x19  # u8[7]: ATK DEF SPE SPA SPD ACC EVA; neutral=6, range 0–12

# Side status — bit 0x10 = SIDE_STATUS_STEALTH_ROCK; set when SR is placed on that side.
# 0x02023DDE confirmed to flip 0→16 when Hippowdon uses Stealth Rock (persistent across turns).
# 0x02023DEE is 16 bytes away and likely the opponent-side mirror — verify with Rapid Spin.
SIDE_STATUS_PLAYER = 0x02023DDE  # u8/u32 bitmask, player's field side
SIDE_STATUS_OPP    = 0x02023DEE  # u8/u32 bitmask, opponent's field side

# Frame budgets
INTRO_A_PRESSES     = 30   # A presses after battle flag to advance trainer/send-out dialogue
INTRO_SETTLE_FRAMES = 500  # additional wait for auto-advancing messages (Intimidate, weather)
TURN_WAIT_B_PRESSES = 30   # B presses per turn: advances text boxes; safe on battle menu (cursor stays at FIGHT)
POLL_FRAMES         = 5    # poll BATTLE_TYPE_FLAGS every N frames inside the B-press loop


def build_slot_map(mem) -> dict[str, int]:
    return {p.name: i for i, p in enumerate(party.read_party(mem))}


@dataclass
class BattleState:
    party: list[party.PartyPokemon]   # all party members in party-slot order
    active_slot: int                   # which party slot is currently on the field
    weather: int                       # BATTLE_WEATHER bitmask (0x08 = sandstorm)
    weather_turns_left: int            # WEATHER_TIMER countdown
    stat_stages: tuple[int, ...]       # player active: (ATK,DEF,SPE,SPA,SPD,ACC,EVA) neutral=6
    opp_stat_stages: tuple[int, ...]   # opponent active: same layout
    stealth_rock_player: bool          # SR on player's side
    stealth_rock_opp: bool             # SR on opponent's side


def _read_stat_stages(mem, battler_idx: int) -> tuple[int, ...]:
    base = BATTLE_MONS_BASE + battler_idx * BATTLE_MON_SIZE + _MON_STAT_STAGES
    return tuple(mem.u8[base + i] for i in range(7))


def read_battle_state(mem, active_slot: int) -> BattleState:
    return BattleState(
        party=party.read_party(mem),
        active_slot=active_slot,
        weather=mem.u32[BATTLE_WEATHER] & 0xFF,
        weather_turns_left=mem.u8[WEATHER_TIMER],
        stat_stages=_read_stat_stages(mem, 0),
        opp_stat_stages=_read_stat_stages(mem, 1),
        stealth_rock_player=bool(mem.u8[SIDE_STATUS_PLAYER] & 0x10),
        stealth_rock_opp=bool(mem.u8[SIDE_STATUS_OPP] & 0x10),
    )


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
    return tuple((p.current_hp, p.max_hp) for p in party.read_party(mem))


def _battle_active(mem) -> bool:
    return mem.u32[BATTLE_TYPE_FLAGS] != 0


def _find_move_slot(mem, move_name: str, active_slot: int) -> int:
    poke = party.read_slot(mem, active_slot)
    for i, name in enumerate(poke.moves):
        if name == move_name:
            return i
    raise ValueError(f"{move_name!r} not in party slot {active_slot}'s moveset")


def _parse_action(action: str) -> tuple[str, list[str]]:
    parts = action.split()
    return parts[0], parts[1:]


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------

def _fight(emu: Emulator, move_name: str, active_slot: int) -> None:
    move_slot = _find_move_slot(emu.mem, move_name, active_slot)
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
    Press B up to TURN_WAIT_B_PRESSES times to advance text boxes.
    Polls BATTLE_TYPE_FLAGS every POLL_FRAMES frames.
    When the battle ends (flags → 0), immediately captures party HP and opponent move
    before EWRAM is overwritten by the post-battle sequence.

    Returns: (battle_ended, hp_snapshot_at_end, opponent_move_at_end)
    If battle is still ongoing: (False, None, last_opponent_move)
    """
    frames_per_press = 60 // POLL_FRAMES
    for _ in range(TURN_WAIT_B_PRESSES):
        emu.press(KEY_B, hold_frames=1)
        for _ in range(frames_per_press):
            emu.step(POLL_FRAMES)
            if not _battle_active(emu.mem):
                hp_snap    = _hp_snapshot(emu.mem)
                opp_move   = emu.mem.u16[LAST_MOVES + 2]
                return True, hp_snap, opp_move
    opp_move = emu.mem.u16[LAST_MOVES + 2]
    return False, None, opp_move


def run(emu: Emulator, get_action: Callable[[BattleState, list[StepLog]], str]) -> BattleResult:
    """
    Execute one full Giovanni battle attempt.

    get_action is called each turn with the current BattleState and the full step
    history so far; it returns one action string:
      FIGHT <move_name>  — voluntary move from the battle menu
      SWITCH <pokemon>   — voluntary switch from the battle menu
      SEND <pokemon>     — forced replacement after a faint

    Battle end is detected by polling BATTLE_TYPE_FLAGS every 5 frames inside
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
    for _ in range(INTRO_A_PRESSES):
        emu.press(KEY_A, hold_frames=3)
        emu.step(40)
    emu.step(INTRO_SETTLE_FRAMES)

    slot_of     = build_slot_map(emu.mem)
    active_slot = 0  # lead is always party slot 0; updated after each switch

    steps = []
    won   = False
    step  = 0

    while True:
        state  = read_battle_state(emu.mem, active_slot)
        action = get_action(state, steps)

        _execute(emu, action, slot_of, active_slot)
        ended, end_hp, opp_move = _b_press_loop(emu)

        kind, args = _parse_action(action)
        if kind in ("SWITCH", "SEND"):
            active_slot = slot_of[args[0]]

        step += 1
        # Use HP captured at flags-clear when the battle ended; otherwise read current EWRAM.
        hp_snap = end_hp if ended else _hp_snapshot(emu.mem)
        steps.append(StepLog(
            step=step,
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
