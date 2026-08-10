import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build agent and validator data for a task from master game data."
    )
    parser.add_argument("task_dir", type=Path)
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    task_dir = arguments.task_dir.resolve()
    manifest_path = task_dir / "task.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    game_data_version = manifest.get("game_data_version")
    if not isinstance(game_data_version, str):
        raise ValueError("task.yaml must define game_data_version")
    allowed_locations = manifest.get("allowed_locations")
    if not isinstance(allowed_locations, list) or not all(
        isinstance(location, str) for location in allowed_locations
    ):
        raise ValueError("task.yaml must define allowed_locations as a list of strings")
    water_methods = manifest.get("available_water_methods", [])
    if not isinstance(water_methods, list) or not all(
        isinstance(method, str) for method in water_methods
    ):
        raise ValueError("available_water_methods must be a list of strings")
    excluded_species_categories = manifest.get("excluded_species_categories", [])
    if not isinstance(excluded_species_categories, list) or not all(
        isinstance(category, str) for category in excluded_species_categories
    ):
        raise ValueError("excluded_species_categories must be a list of strings")

    master_data_dir = root / "data" / "radical_red" / game_data_version
    route_map = json.loads((master_data_dir / "route_pokemon_map.json").read_text())
    route_pokemon_species_ids = json.loads(
        (master_data_dir / "route_pokemon_species_ids.json").read_text()
    )
    route_move_map = json.loads(
        (master_data_dir / "route_move_map.json").read_text()
    )
    route_item_map = json.loads(
        (master_data_dir / "route_item_map.json").read_text()
    )
    species = json.loads((master_data_dir / "species.json").read_text())
    moves = json.loads((master_data_dir / "moves.json").read_text())
    learnsets = json.loads((master_data_dir / "learnsets.json").read_text())
    items = json.loads((master_data_dir / "items.json").read_text())
    species_categories = json.loads(
        (master_data_dir / "species_categories.json").read_text()
    )
    excluded_species_ids = set()
    for category in excluded_species_categories:
        if category not in species_categories:
            raise ValueError(f"unknown excluded species category: {category}")
        excluded_species_ids.update(species_categories[category])

    direct_species_ids = set()
    for location in allowed_locations:
        if location not in route_map:
            raise ValueError(f"unknown allowed location: {location}")
        encounter_data = route_map[location]
        for source in ("grass_caves", "egg", "game_corner", "static", "fossil"):
            for pokemon_name in encounter_data.get(source, []):
                direct_species_ids.add(route_pokemon_species_ids[pokemon_name])
        fishing_surfing = encounter_data.get("fishing_surfing", {})
        for method in water_methods:
            if method not in {"old_rod", "good_rod", "super_rod", "surfing"}:
                raise ValueError(f"unknown water method: {method}")
            for pokemon_name in fishing_surfing.get(method, []):
                direct_species_ids.add(route_pokemon_species_ids[pokemon_name])
    direct_species_ids.difference_update(excluded_species_ids)

    move_name_aliases = {
        "Draining Kiss": "Drain Kiss",
        "Supercell Slam": "Soupercell Slam",
        "U-Turn": "U-turn",
    }
    move_ids_by_name = {
        move["name"]: move_id for move_id, move in enumerate(moves) if move
    }
    available_move_ids = {"tm_hm": set(), "tutor": set()}
    available_hm_names = set()
    known_hm_names = {
        move_name
        for location_data in route_move_map.values()
        for move_name in location_data["hms"]
    }
    for location in allowed_locations:
        for route_source, learnset_source in (
            ("tms", "tm_hm"),
            ("hms", "tm_hm"),
            ("tutors", "tutor"),
        ):
            for move_name in route_move_map.get(location, {}).get(route_source, []):
                resolved_move_name = move_name_aliases.get(move_name, move_name)
                if resolved_move_name not in move_ids_by_name:
                    raise ValueError(
                        f"unknown {route_source[:-1]} move at {location}: {move_name}"
                    )
                available_move_ids[learnset_source].add(
                    move_ids_by_name[resolved_move_name]
                )
                if route_source == "hms":
                    available_hm_names.add(resolved_move_name)

    items_by_id = {item["id"]: item for item in items}
    if len(items_by_id) != len(items):
        raise ValueError("items.json must contain unique item IDs")
    item_ids_by_name = defaultdict(list)
    for item in items:
        item_ids_by_name[item["name"]].append(item["id"])
    item_counts = defaultdict(int)
    for location in allowed_locations:
        item_data = route_item_map.get(location, {})
        if not isinstance(item_data, dict):
            raise ValueError(f"invalid item data at {location}")
        for requirement, item_entries in item_data.items():
            if requirement != "items" and requirement not in known_hm_names:
                raise ValueError(f"unknown item requirement at {location}: {requirement}")
            if requirement != "items" and requirement not in available_hm_names:
                continue
            if not isinstance(item_entries, list):
                raise ValueError(f"invalid item list at {location}: {requirement}")
            for item_entry in item_entries:
                if isinstance(item_entry, str):
                    matching_item_ids = item_ids_by_name.get(item_entry, [])
                    if len(matching_item_ids) != 1:
                        raise ValueError(
                            f"ambiguous or unknown item at {location}: {item_entry}"
                        )
                    item_counts[matching_item_ids[0]] += 1
                    continue
                if (
                    not isinstance(item_entry, dict)
                    or set(item_entry) != {"name", "id"}
                ):
                    raise ValueError(f"invalid item entry at {location}: {item_entry}")
                item_id = item_entry["id"]
                item_name = item_entry["name"]
                if (
                    type(item_id) is not int
                    or not isinstance(item_name, str)
                    or item_id not in items_by_id
                    or items_by_id[item_id]["name"] != item_name
                ):
                    raise ValueError(f"invalid item entry at {location}: {item_entry}")
                item_counts[item_id] += 1

    rotom_is_directly_available = any(
        species[species_id] and species[species_id]["name"] == "Rotom"
        for species_id in direct_species_ids
    )
    if rotom_is_directly_available:
        direct_species_ids.update(
            species_id
            for species_id, entry in enumerate(species)
            if entry
            and entry["name"] == "Rotom"
            and species_id not in excluded_species_ids
            and entry["minimum_level"] <= manifest["level_cap"]
        )

    evolutions = defaultdict(set)
    for species_id, learnset in enumerate(learnsets):
        if not learnset:
            continue
        for pre_evolution_id in learnset["pre_evolution_ids"]:
            evolutions[pre_evolution_id].add(species_id)

    allowed_species_ids = set(direct_species_ids)
    pending_species_ids = list(direct_species_ids)
    while pending_species_ids:
        species_id = pending_species_ids.pop()
        for evolution_id in evolutions[species_id]:
            evolution = species[evolution_id]
            if (
                evolution_id not in allowed_species_ids
                and evolution_id not in excluded_species_ids
                and evolution["minimum_level"] <= manifest["level_cap"]
            ):
                allowed_species_ids.add(evolution_id)
                pending_species_ids.append(evolution_id)

    has_drifloon_or_drifblim = any(
        species[species_id]["name"] in {"Drifloon", "Drifblim"}
        for species_id in allowed_species_ids
    )
    if has_drifloon_or_drifblim:
        air_balloon_ids = item_ids_by_name["Air Balloon"]
        if len(air_balloon_ids) != 1:
            raise ValueError("items.json must contain exactly one Air Balloon")
        item_counts.setdefault(air_balloon_ids[0], 1)

    agent_data_dir = task_dir / "data" / "agent"
    validation_data_dir = task_dir / "data" / "validation"
    agent_data_dir.mkdir(parents=True, exist_ok=True)
    validation_data_dir.mkdir(parents=True, exist_ok=True)
    allowed_species_id_list = sorted(allowed_species_ids)
    allowed_item_id_list = sorted(item_counts)

    agent_species = [
        entry if species_id in allowed_species_ids else None
        for species_id, entry in enumerate(species)
    ]
    agent_learnsets = []
    for species_id, entry in enumerate(learnsets):
        if species_id not in allowed_species_ids:
            agent_learnsets.append(None)
            continue
        agent_learnset = dict(entry)
        for source, allowed_move_ids in available_move_ids.items():
            agent_learnset[source] = [
                move_id for move_id in entry[source] if move_id in allowed_move_ids
            ]
        if "fuchsia_city" not in allowed_locations:
            agent_learnset["egg"] = []
        agent_learnsets.append(agent_learnset)
    agent_items = [
        {**item, "count": item_counts[item["id"]]}
        for item in items
        if item["id"] in item_counts
    ]
    (agent_data_dir / "species.json").write_text(
        json.dumps(agent_species, indent=2, ensure_ascii=False) + "\n"
    )
    serialized_agent_learnsets = (
        json.dumps(agent_learnsets, indent=2, ensure_ascii=False) + "\n"
    )
    (agent_data_dir / "learnsets.json").write_text(serialized_agent_learnsets)
    (agent_data_dir / "items.json").write_text(
        json.dumps(agent_items, indent=2, ensure_ascii=False) + "\n"
    )
    for filename in ("abilities.json", "moves.json"):
        (agent_data_dir / filename).write_text(
            (master_data_dir / filename).read_text()
        )
    (agent_data_dir / "metadata.json").write_text(
        json.dumps(
            {
                "game_data_version": game_data_version,
                "task_id": manifest["id"],
                "allowed_species_count": len(allowed_species_id_list),
                "available_tm_hm_move_count": len(available_move_ids["tm_hm"]),
                "available_tutor_move_count": len(available_move_ids["tutor"]),
                "available_hms": sorted(available_hm_names),
                "allowed_item_count": len(allowed_item_id_list),
                "egg_move_tutor_available": "fuchsia_city" in allowed_locations,
                "excluded_species_categories": excluded_species_categories,
            },
            indent=2,
        )
        + "\n"
    )
    (validation_data_dir / "allowed_species_ids.json").write_text(
        json.dumps(
            {
                "game_data_version": game_data_version,
                "task_yaml_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "species_ids": allowed_species_id_list,
            },
            indent=2,
        )
        + "\n"
    )
    (validation_data_dir / "allowed_item_ids.json").write_text(
        json.dumps(
            {
                "game_data_version": game_data_version,
                "task_yaml_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "item_ids": allowed_item_id_list,
                "item_counts": {
                    str(item_id): item_counts[item_id]
                    for item_id in allowed_item_id_list
                },
            },
            indent=2,
        )
        + "\n"
    )

    print(
        f"Built {len(allowed_species_id_list)} allowed species "
        f"and {len(allowed_item_id_list)} allowed items for {manifest['id']} "
        f"from {len(direct_species_ids)} direct encounters"
    )


if __name__ == "__main__":
    main()
