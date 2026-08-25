import pytest

from rrbench.battle.addresses import (
    BATTLE_MONS_BASE,
    BATTLE_MON_SIZE,
    BATTLE_MENU_READY,
    BATTLE_TERRAIN,
    BATTLE_TYPE_FLAGS,
    BATTLE_WEATHER,
    OPP_MON_BASE,
    WEATHER_RAIN,
    WEATHER_SANDSTORM,
    WEATHER_SNOW,
    WEATHER_SUN,
    WEATHER_TIMER,
    MON_ABILITY,
    MON_CUR_HP,
    MON_MAX_HP,
    MON_SPECIES,
    MON_STAT_STAGES,
    MSG_BUFFER,
    SIDE_HAZARDS_OPP,
    SIDE_HAZARDS_PLAYER,
    TERRAIN_TIMER,
)
from rrbench.battle.capture import TurnRecorder, capture_intro, capture_turn, decode_msg
from rrbench.battle.state import decode_weather, read_battle_state
from rrbench.emulator.emulator import KEY_B
from rrbench.emulator.memory import PARTY_BASE_ADDR, Party, SLOT_SIZE
from rrbench.interface.protocol import render_observation, render_pre_battle
from tests.support.fakes import FakeEmulator


def test_pre_battle_observation_reads_party_memory(party_memory) -> None:
    """
    tests whether we read the pre-battle state correctly
    should just be information about the user's team
    """
    party = Party(party_memory)

    observation = render_pre_battle(party)

    assert observation == {
        "phase": "no_battle",
        "party": [
            {
                "name": "Bulbasaur",
                "form": None,
                "current_hp": 100,
                "max_hp": 120,
                "status": "poison",
                "active": False,
                "fainted": False,
                "moves": [
                    {"name": "Pound", "pp_remaining": 10},
                    {"name": "Growl", "pp_remaining": 12},
                ],
            },
            {
                "name": "Incineroar",
                "form": None,
                "current_hp": 88,
                "max_hp": 150,
                "status": None,
                "active": False,
                "fainted": False,
                "moves": [
                    {"name": "Ember", "pp_remaining": 20},
                    {"name": "Growl", "pp_remaining": 15},
                ],
            },
        ],
    }


def test_pre_battle_observation_renders_each_rotom_form(party_memory) -> None:
    party_memory.load_u16(PARTY_BASE_ADDR + 0x20, 714)
    party_memory.load_u16(PARTY_BASE_ADDR + SLOT_SIZE + 0x20, 715)

    observation = render_pre_battle(Party(party_memory))

    assert [
        (pokemon["name"], pokemon["form"])
        for pokemon in observation["party"]
    ] == [
        ("Rotom", "wash"),
        ("Rotom", "frost"),
    ]


@pytest.mark.parametrize(
    ("weather", "timer", "expected"),
    [
        (0, 0, ("none", 0)),
        (WEATHER_RAIN, 4, ("rain", 4)),
        (WEATHER_RAIN | 0x04, 0, ("rain", None)),  # Route 25's permanent rain
        (WEATHER_SANDSTORM, 4, ("sandstorm", 4)),
        (WEATHER_SUN, 4, ("sun", 4)),
        (WEATHER_SNOW, 4, ("snow", 4)),
    ],
)
def test_decode_weather(weather, timer, expected) -> None:
    assert decode_weather(weather, timer) == expected


def test_battle_observation_reads_field_state_and_replacement(party_memory) -> None:
    """
    as setup, we:
    - set the active slot in the Party as Incineroar with 0 HP and various stat stage changes
    - set the opponent active Pokemon to Ivysaur with 71 HP and various stat stage changes
    then we observe() and see if it matches the setup
    """
    opponent = BATTLE_MONS_BASE + BATTLE_MON_SIZE
    incineroar = PARTY_BASE_ADDR + SLOT_SIZE
    party_memory.load_u16(incineroar + 0x56, 0)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_SPECIES, 944)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 0)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_MAX_HP, 150)
    party_memory.load_bytes(
        BATTLE_MONS_BASE + MON_STAT_STAGES,
        bytes((8, 6, 5, 6, 7, 6, 6)),
    )
    party_memory.load_u16(opponent + MON_SPECIES, 2)
    party_memory.load_u8(opponent + MON_ABILITY, 34)
    party_memory.load_u16(opponent + MON_CUR_HP, 71)
    party_memory.load_u16(opponent + MON_MAX_HP, 100)
    party_memory.load_bytes(
        opponent + MON_STAT_STAGES,
        bytes((6, 5, 6, 8, 6, 7, 6)),
    )
    party_memory.load_u32(BATTLE_WEATHER, WEATHER_SANDSTORM)
    party_memory.load_u32(WEATHER_TIMER, 4)
    party_memory.load_u8(BATTLE_TERRAIN, 2)
    party_memory.load_u8(TERRAIN_TIMER, 3)
    party_memory.load_u8(SIDE_HAZARDS_PLAYER, 0x3B)
    party_memory.load_u8(SIDE_HAZARDS_OPP, 0x15)
    party = Party(party_memory)

    observation = render_observation(read_battle_state(party_memory, party))

    assert observation["phase"] == "in_battle"
    assert observation["needs_replacement"] is True
    assert observation["active"] == {"name": "Incineroar", "form": None, "slot": 1}
    assert observation["party"][1]["fainted"] is True
    assert observation["opponent"] == {
        "species": "Ivysaur",
        "form": None,
        "species_id": 2,
        "ability": "Chlorophyll",
        "current_hp": 71,
        "max_hp": 100,
    }
    assert observation["weather"] == {"kind": "sandstorm", "turns_left": 4}
    assert observation["terrain"] == {"kind": "grassy", "turns_left": 3}
    assert observation["hazards"] == {
        "player": {
            "stealth_rock": True,
            "spikes": 3,
            "toxic_spikes": 2,
            "sticky_web": True,
        },
        "opponent": {
            "stealth_rock": True,
            "spikes": 1,
            "toxic_spikes": 1,
            "sticky_web": False,
        },
    }
    assert observation["stat_stages"] == {
        "player": {
            "ATK": 2,
            "DEF": 0,
            "SPE": -1,
            "SPA": 0,
            "SPD": 1,
            "ACC": 0,
            "EVA": 0,
        },
        "opponent": {
            "ATK": 0,
            "DEF": -1,
            "SPE": 0,
            "SPA": 2,
            "SPD": 0,
            "ACC": 1,
            "EVA": 0,
        },
    }


@pytest.mark.parametrize(
    ("battle_species_id", "party_species_id"),
    [
        (737, 608),   # Darmanitan Zen Mode -> Darmanitan
        (751, 474),   # Cherrim Sunshine Form -> Cherrim
        (833, 789),   # Aegislash Blade Forme -> Shield Forme
        (839, 766),   # Ash-Greninja -> Greninja
        (1065, 991),  # Minior Core Form -> Minior Meteor Form
    ],
)
def test_battle_observation_matches_a_unique_transformation_form_in_party(
    party_memory, battle_species_id, party_species_id
) -> None:
    """A fainted transformed Pokemon reverts to its persistent party form."""
    party_memory.load_u16(PARTY_BASE_ADDR + 0x20, party_species_id)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_SPECIES, battle_species_id)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 0)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_MAX_HP, 120)

    state = read_battle_state(party_memory, Party(party_memory))

    assert state.active_slot == 0
    assert state.needs_replacement is True


def test_message_decoding_handles_controls_whitespace_and_terminator() -> None:
    """
    the gba/gba emulators have a text encoding format that is non-standard
    this format also includes things like controls/terminators, not just text characters.
    """
    raw = bytes(
        (
            0xBB,
            0x00,
            0xFB,
            0xBC,
            0xFC,
            0x12,
            0xFE,
            0xD7,
            0xFD,
            0x01,
            0xA0,
            0xA0,
            0xA1,
            0xAD,
            0xFF,
            0xD4,
        )
    )

    assert decode_msg(raw) == "A B c 0."


def test_turn_recorder_captures_message_reappearance_after_clear(party_memory) -> None:
    """
    one edge case that happens is with multi-hit moves (e.g. Mega Kangaskhan w/Parental Bond)
    say Mega Kangaskhan uses Crunch on a Psychic type Pokemon. The move will hit twice and text
    indicating that the move was super effective will also be rendered on the screen twice.

    we want to ensure that we're not merging these MessageEvents into a single one based on just
    their raw text and instead representing that they come from two different states of the battle.
    """
    party_memory.load_u16(BATTLE_MONS_BASE + MON_SPECIES, 1)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 90)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_MAX_HP, 120)
    opponent = BATTLE_MONS_BASE + BATTLE_MON_SIZE
    party_memory.load_u16(opponent + MON_SPECIES, 2)
    party_memory.load_u16(opponent + MON_CUR_HP, 75)
    party_memory.load_u16(opponent + MON_MAX_HP, 100)
    message = bytes((0xC2, 0xDD, 0xE8, 0xAB, 0xFF))
    party_memory.load_bytes(MSG_BUFFER, message)
    emulator = FakeEmulator(party_memory)
    party = Party(party_memory)
    recorder = TurnRecorder()

    recorder.poll(emulator, party)
    party_memory.load_u8(MSG_BUFFER, 0xFF)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 80)
    party_memory.load_u16(opponent + MON_CUR_HP, 70)
    recorder.poll(emulator, party)
    party_memory.load_bytes(MSG_BUFFER, message)
    recorder.poll(emulator, party)

    assert [event.text for event in recorder.events] == ["Hit!", "Hit!"]
    assert recorder.events[0].party_hp["Bulbasaur"] == (80, 120)
    assert recorder.events[0].opp_hp == (70, 100)
    assert recorder.events[1].party_hp["Bulbasaur"] == (80, 120)


def test_capture_turn_collects_messages_in_order_and_waits_for_menu(party_memory) -> None:
    """
    after an action is performed, we spam B to move through all the text that is
    rendered to get back to the battle menu for the next turn

    this tests whether we correctly capture all that text into MessageEvents
    """
    party_memory.load_u32(BATTLE_TYPE_FLAGS, 0xC)
    party_memory.load_u8(BATTLE_MENU_READY, 1)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_SPECIES, 1)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 100)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_MAX_HP, 120)
    party_memory.load_bytes(MSG_BUFFER, bytes((0xC9, 0xE2, 0xD9, 0xAB, 0xFF)))
    emulator = FakeEmulator(party_memory)
    party = Party(party_memory)
    message_steps = 0

    def advance_messages(current_emulator, frames: int) -> None:
        nonlocal message_steps
        if frames != 4:
            return
        message_steps += 1
        if message_steps == 1:
            current_emulator.mem.load_bytes(
                MSG_BUFFER,
                bytes((0xCE, 0xEB, 0xE3, 0xAB, 0xFF)),
            )
        else:
            current_emulator.mem.load_bytes(
                MSG_BUFFER,
                bytes(
                    (
                        0xD1,
                        0xDC,
                        0xD5,
                        0xE8,
                        0x00,
                        0xEB,
                        0xDD,
                        0xE0,
                        0xE0,
                        0x00,
                        0xD2,
                        0x00,
                        0xD8,
                        0xE3,
                        0xAC,
                        0xFF,
                    )
                ),
            )

    emulator.step_callback = advance_messages

    events, ended, won = capture_turn(emulator, party, max_polls=32)

    assert [event.text for event in events] == ["One!", "Two!"]
    assert (ended, won) == (False, False)
    assert emulator.calls[:4] == [
        ("press", KEY_B, 1),
        ("step", 4),
        ("press", KEY_B, 1),
        ("step", 4),
    ]
    assert emulator.calls[4:] == [("step", 4)] * 29


def test_capture_intro_uses_b_to_advance_text(party_memory) -> None:
    party_memory.load_u32(BATTLE_TYPE_FLAGS, 0xC)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_SPECIES, 1)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 100)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_MAX_HP, 120)
    party_memory.load_bytes(MSG_BUFFER, bytes((0xC9, 0xE2, 0xD9, 0xAB, 0xFF)))
    emulator = FakeEmulator(party_memory)

    events = capture_intro(emulator, Party(party_memory))

    assert [event.text for event in events] == ["One!"]
    assert [call for call in emulator.calls if call[0] == "press"] == [
        ("press", KEY_B, 3)
    ] * 30


@pytest.mark.parametrize(
    ("active_hp", "expected_won"),
    ((40, True), (0, False)),
)
def test_capture_turn_detects_battle_end(
    party_memory, active_hp: int, expected_won: bool
) -> None:
    """
    if the battle is over, then we should correctly set the `ended`/`won` fields
    """
    party_memory.load_u32(BATTLE_TYPE_FLAGS, 0)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, active_hp)
    emulator = FakeEmulator(party_memory)

    events, ended, won = capture_turn(emulator, Party(party_memory))

    assert events == []
    assert ended is True
    assert won is expected_won
    assert emulator.calls == []


def test_capture_turn_checks_battle_end_after_final_faint_settle(party_memory) -> None:
    """A simultaneous final faint may clear the battle flag after the normal
    replacement-screen flush limit; termination must win that race.
    """
    party_memory.load_u32(BATTLE_TYPE_FLAGS, 0xC)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 0)
    party_memory.load_u16(OPP_MON_BASE + MON_CUR_HP, 0)
    party_memory.load_u16(PARTY_BASE_ADDR + 0x56, 0)
    party_memory.load_u16(PARTY_BASE_ADDR + SLOT_SIZE + 0x56, 88)
    emulator = FakeEmulator(party_memory)
    settle_count = 0

    def clear_battle_flag_after_terminal_settle(emu, frames) -> None:
        nonlocal settle_count
        if frames == 60:
            settle_count += 1
            if settle_count == 13:
                emu.mem.load_u32(BATTLE_TYPE_FLAGS, 0)

    emulator.step_callback = clear_battle_flag_after_terminal_settle

    events, ended, won = capture_turn(emulator, Party(party_memory), max_polls=32)

    assert events == []
    assert ended is True
    # Outcome classification is covered separately; the active Pokemon is fainted
    # in this simultaneous-KO case, so the existing heuristic reports False here.
    assert won is False
    assert settle_count == 13


@pytest.mark.parametrize(
    ("bench_hp", "expected_ended"),
    ((88, False), (0, True)),
)
def test_capture_turn_handles_fainted_active(
    party_memory, bench_hp: int, expected_ended: bool
) -> None:
    """
    if the active Pokemon faints but there is another Pokemon in the party,
    then we want to make sure the battle has not ended and `won` is False.
    """
    party_memory.load_u32(BATTLE_TYPE_FLAGS, 0xC)
    party_memory.load_u16(BATTLE_MONS_BASE + MON_CUR_HP, 0)
    party_memory.load_u16(PARTY_BASE_ADDR + 0x56, 0)
    party_memory.load_u16(PARTY_BASE_ADDR + SLOT_SIZE + 0x56, bench_hp)
    emulator = FakeEmulator(party_memory)

    events, ended, won = capture_turn(emulator, Party(party_memory), max_polls=12)

    assert events == []
    assert ended is expected_ended
    assert won is False
    assert emulator.calls == [
        call
        for pair in ((("press", KEY_B, 1), ("step", 60)) for _ in range(12))
        for call in pair
    ]
