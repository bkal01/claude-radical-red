import pytest

from rrbench.battle.addresses import (
    BATTLE_WEATHER, MAP_HEADER_WEATHER, WEATHER_RAIN, WEATHER_TIMER,
)
from rrbench.battle.engine import start_battle
from rrbench.emulator.memory import Party
from rrbench.interface.service import create_emulator
from rrbench.tasks import load_task
from rrbench.team import PokemonConfig, TeamConfig


@pytest.mark.integration
@pytest.mark.parametrize(
    ("task_path", "map_weather", "expected"),
    [
        ("tasks/archer-mt-moon", 0, ("none", 0)),
        ("tasks/bugsy-route-25", 3, ("rain", None)),
    ],
)
def test_live_weather_memory_matches_map_weather(task_path, map_weather, expected) -> None:
    """Regression test for RR v4.1's actual weather state, not vanilla offsets."""
    task = load_task(task_path)
    emulator = create_emulator(task)
    party = Party(emulator.mem)

    _, state, _ = start_battle(
        emulator, party, party.members[0].label, task.battle_trigger,
    )

    assert emulator.mem.u8[MAP_HEADER_WEATHER] == map_weather
    assert (state.weather_kind, state.weather_turns_left) == expected


@pytest.mark.integration
def test_pelipper_drizzle_sets_temporary_rain_in_live_weather_memory() -> None:
    """Drizzle's switch-in effect uses the same state as a weather move."""
    task = load_task("tasks/archer-mt-moon")
    emulator = create_emulator(task)
    # Pelipper's hidden ability is Drizzle. Apply directly because this focused
    # emulator fixture intentionally tests a species outside this task's allowlist.
    team = TeamConfig([
        PokemonConfig(
            species_id=310,
            evs={},
            level=task.level_cap,
            nature_id=0,
            ability_id=2,
            move_ids=(1,),
        )
        for _ in range(task.team_size)
    ])
    team.apply(emulator.mem)
    party = Party(emulator.mem)

    _, state, _ = start_battle(
        emulator, party, party.members[0].label, task.battle_trigger,
    )

    assert emulator.mem.u32[BATTLE_WEATHER] == WEATHER_RAIN
    assert emulator.mem.u32[WEATHER_TIMER] == 5
    assert (state.weather_kind, state.weather_turns_left) == ("rain", 5)
