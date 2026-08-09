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
    species = json.loads((master_data_dir / "species.json").read_text())
    moves = json.loads((master_data_dir / "moves.json").read_text())
    learnsets = json.loads((master_data_dir / "learnsets.json").read_text())
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

    agent_data_dir = task_dir / "data" / "agent"
    validation_data_dir = task_dir / "data" / "validation"
    agent_data_dir.mkdir(parents=True, exist_ok=True)
    validation_data_dir.mkdir(parents=True, exist_ok=True)
    allowed_species_id_list = sorted(allowed_species_ids)

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
    (agent_data_dir / "species.json").write_text(
        json.dumps(agent_species, indent=2, ensure_ascii=False) + "\n"
    )
    serialized_agent_learnsets = json.dumps(agent_learnsets, indent=2, ensure_ascii=False) + "\n"
    (agent_data_dir / "learnsets.json").write_text(serialized_agent_learnsets)
    for filename in ("abilities.json", "moves.json", "items.json"):
        (agent_data_dir / filename).write_text((master_data_dir / filename).read_text())
    (agent_data_dir / "metadata.json").write_text(
        json.dumps(
            {
                "game_data_version": game_data_version,
                "task_id": manifest["id"],
                "allowed_species_count": len(allowed_species_id_list),
                "available_tm_hm_move_count": len(available_move_ids["tm_hm"]),
                "available_tutor_move_count": len(available_move_ids["tutor"]),
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

    print(
        f"Built {len(allowed_species_id_list)} allowed species "
        f"for {manifest['id']} from {len(direct_species_ids)} direct encounters"
    )


if __name__ == "__main__":
    main()
