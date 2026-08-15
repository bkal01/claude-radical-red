import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    ("allowed_locations", "simipour_available"),
    [(["route_22"], False), (["route_22", "celadon_city"], True)],
)
def test_build_task_data_gates_item_evolutions_by_location(
    tmp_path, allowed_locations, simipour_available
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
                "level_cap": 15,
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

    assert (species[569] is not None) is simipour_available
