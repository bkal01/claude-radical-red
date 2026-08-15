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
