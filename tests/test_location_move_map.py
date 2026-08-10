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


def test_route_item_map_contains_battle_holdable_items():
    data_dir = Path(__file__).resolve().parents[1] / "data" / "radical_red" / "v4.1"
    route_item_map = json.loads((data_dir / "route_item_map.json").read_text())
    route_move_map = json.loads((data_dir / "route_move_map.json").read_text())
    route_map = json.loads((data_dir / "route_pokemon_map.json").read_text())
    items = json.loads((data_dir / "items.json").read_text())
    item_ids_by_name = {}
    for item in items:
        item_ids_by_name.setdefault(item["name"], []).append(item["id"])
    locations = set(route_map) | set(route_move_map)
    hm_names = {
        move_name
        for location_data in route_move_map.values()
        for move_name in location_data["hms"]
    }

    assert set(route_item_map) <= locations
    for entry in route_item_map.values():
        assert "items" in entry
        assert set(entry) <= {"items"} | hm_names
        for item_entries in entry.values():
            assert isinstance(item_entries, list)
            for item_entry in item_entries:
                if isinstance(item_entry, str):
                    assert len(item_ids_by_name[item_entry]) == 1
                else:
                    assert set(item_entry) == {"name", "id"}
                    assert item_entry["id"] in item_ids_by_name[item_entry["name"]]


def test_items_have_explicit_unique_ids():
    data_dir = Path(__file__).resolve().parents[1] / "data" / "radical_red" / "v4.1"
    items = json.loads((data_dir / "items.json").read_text())

    assert all(set(item) == {"id", "name", "description"} for item in items)
    assert [item["id"] for item in items] == list(range(1, 750))
