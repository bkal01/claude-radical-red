import json
from pathlib import Path


def test_route_move_map_contains_obtainable_tms_and_hms():
    data_dir = Path(__file__).resolve().parents[1] / "data" / "radical_red" / "v4.1"
    route_move_map = json.loads((data_dir / "route_move_map.json").read_text())
    route_map = json.loads((data_dir / "route_pokemon_map.json").read_text())

    assert all(set(entry) == {"tms", "hms", "tutors"} for entry in route_move_map.values())
    assert all(
        all(isinstance(move, str) for move in entry[move_type])
        for entry in route_move_map.values()
        for move_type in ("tms", "hms", "tutors")
    )

    tms = [move for entry in route_move_map.values() for move in entry["tms"]]
    hms = [move for entry in route_move_map.values() for move in entry["hms"]]
    assert len(tms) == len(set(tms)) == 118
    assert len(hms) == len(set(hms)) == 7
    assert sum(len(entry["tutors"]) for entry in route_move_map.values()) == 56
    assert route_move_map["one_island"]["hms"] == ["Waterfall"]
    assert "one_island" in route_map
