import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    (
        "allowed_locations",
        "level_cap",
        "simipour_available",
        "starter_line_available",
        "starter_evolution_available",
    ),
    [
        (["route_22"], 15, False, True, False),
        (["route_22", "celadon_city"], 15, True, False, False),
        (["route_22"], 16, False, True, True),
    ],
)
def test_build_task_data_gates_item_evolutions_and_starters_by_location(
    tmp_path,
    allowed_locations,
    level_cap,
    simipour_available,
    starter_line_available,
    starter_evolution_available,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    task_directory = tmp_path / "task"
    task_directory.mkdir()
    (task_directory / "task.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "test",
                "game_data_version": "v4.1",
                "save_state": "save_state.ss0",
                "level_cap": level_cap,
                "allowed_locations": allowed_locations,
            }
        )
    )

    subprocess.run(
        [
            sys.executable,
            str(repository / "scripts" / "build_task_data.py"),
            str(task_directory),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    species = json.loads((task_directory / "data" / "agent" / "species.json").read_text())
    validation_data = json.loads(
        (task_directory / "data" / "validation" / "allowed_species_ids.json").read_text()
    )
    starter_species_ids = json.loads(
        (repository / "data" / "radical_red" / "v4.1" / "starter_species_ids.json").read_text()
    )

    assert (species[569] is not None) is simipour_available
    assert all(species[species_id] is not None for species_id in starter_species_ids)
    if starter_line_available:
        starter_line_species_ids = validation_data["starter_line_species_ids"]
        assert set(starter_species_ids) <= set(starter_line_species_ids)
        assert (2 in starter_line_species_ids) is starter_evolution_available
    else:
        assert "starter_line_species_ids" not in validation_data


def test_build_task_data_enforces_task_and_field_move_gates(tmp_path) -> None:
    repository = Path(__file__).resolve().parents[1]
    moves = json.loads(
        (repository / "data" / "radical_red" / "v4.1" / "moves.json").read_text()
    )

    def build(task_id: int, allowed_locations: list[str]) -> tuple[set[str], set[str]]:
        task_directory = tmp_path / str(task_id) / "task"
        task_directory.mkdir(parents=True, exist_ok=True)
        (task_directory / "task.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": f"test_{task_id}",
                    "task_id": task_id,
                    "game_data_version": "v4.1",
                    "save_state": "save_state.ss0",
                    "level_cap": 100,
                    "allowed_locations": allowed_locations,
                }
            )
        )
        subprocess.run(
            [
                sys.executable,
                str(repository / "scripts" / "build_task_data.py"),
                str(task_directory),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        learnsets = json.loads(
            (task_directory / "data" / "agent" / "learnsets.json").read_text()
        )
        move_names = {
            moves[move_id]["name"]
            for learnset in learnsets
            if learnset
            for move_id in learnset["tm_hm"]
        }
        items = json.loads((task_directory / "data" / "agent" / "items.json").read_text())
        return move_names, {item["name"] for item in items}

    before_brock, _ = build(6, ["pewter_city"])
    after_brock, _ = build(7, ["pewter_city"])
    assert "Rock Tomb" not in before_brock  # unlocked_after: 6 is strict
    assert "Rock Tomb" in after_brock
    assert "Stone Edge" not in after_brock  # unlocked_after: 63

    bugsy, _ = build(16, ["route_25"])
    after_bugsy, _ = build(17, ["route_25"])
    assert "U-turn" not in bugsy  # Bugsy cannot use his own reward.
    assert "U-turn" in after_bugsy

    without_cut, _ = build(22, ["route_2"])
    with_cut, _ = build(22, ["route_2", "s_s_anne"])
    assert "Temper Flare" not in without_cut
    assert "Temper Flare" in with_cut

    without_surf, _ = build(17, ["viridian_city", "celadon_city"])
    with_surf, items_with_surf = build(
        17, ["viridian_city", "celadon_city", "safari_zone"]
    )
    assert "Ice Spinner" not in without_surf
    assert "Ice Spinner" in with_surf
    assert "Light Clay" in items_with_surf

    without_rock_smash, _ = build(62, ["fuchsia_city", "mt_moon_b2f"])
    with_rock_smash, items_with_rock_smash = build(
        63, ["fuchsia_city", "mt_moon_b2f"]
    )
    assert "Rock Smash" not in without_rock_smash
    assert "Rock Smash" in with_rock_smash
    assert "Scope Lens" in items_with_rock_smash
