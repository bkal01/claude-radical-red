import ast
import json
import re
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).parent.parent
SOURCE_COMMIT = "488a0918194d567b5f7b02c396118d51fb9c81ce"
SOURCE_URL = f"https://raw.githubusercontent.com/JwowSquared/Radical-Red-Pokedex/{SOURCE_COMMIT}/data.js"
OUTPUT_PATHS = [
    ROOT / "tasks" / "giovanni" / "environment" / "data" / "species.json",
    ROOT / "tasks" / "giovanni-abilities-only" / "environment" / "data" / "species.json",
    ROOT / "tasks" / "giovanni-items-only" / "environment" / "data" / "species.json",
    ROOT / "tasks" / "giovanni-moves-only" / "environment" / "data" / "species.json",
]
LEVEL_REQUIREMENT_METHODS = {
    4,
    8,
    9,
    10,
    11,
    12,
    13,
    16,
    18,
    20,
    21,
    22,
    23,
    28,
    30,
    31,
}
LEVEL_UP_METHODS = {1, 2, 3, 17, 26, 27}
IMMEDIATE_METHODS = {7, 254}
MISSING_SOURCE_SPECIES_IDS = {920, 1036, 1038, 1214, 1224, 1261}


with urlopen(SOURCE_URL, timeout=30) as response:
    source_text = response.read().decode()

source_text = re.sub(r"\bnull\b", "None", source_text)
source_text = re.sub(r"\btrue\b", "True", source_text)
source_text = re.sub(r"\bfalse\b", "False", source_text)
source_data = ast.literal_eval(source_text)
source_species = source_data["species"]

for output_path in OUTPUT_PATHS:
    species = json.loads(output_path.read_text())
    missing_species_ids = [
        species_id
        for species_id, entry in enumerate(species)
        if entry
        and species_id not in source_species
        and species_id not in MISSING_SOURCE_SPECIES_IDS
    ]
    if missing_species_ids:
        raise ValueError(f"Missing source species data: {missing_species_ids}")

    incoming_species_ids = {
        evolution[2]
        for source_species_id, source_entry in source_species.items()
        if source_species_id < len(species) and species[source_species_id]
        for evolution in source_entry.get("evolutions", [])
        if evolution[2] < len(species) and species[evolution[2]]
    }
    minimum_levels = [
        1 if entry and species_id not in incoming_species_ids else None
        for species_id, entry in enumerate(species)
    ]
    for species_id in MISSING_SOURCE_SPECIES_IDS:
        if species_id < len(species) and species[species_id]:
            minimum_levels[species_id] = 1
    changed = True
    while changed:
        changed = False
        for source_species_id, source_entry in source_species.items():
            if source_species_id >= len(species) or not species[source_species_id]:
                continue
            for evolution in source_entry.get("evolutions", []):
                method, requirement, target_species_id = evolution[:3]
                if target_species_id >= len(species) or not species[target_species_id]:
                    continue
                source_minimum_level = minimum_levels[source_species_id]
                if source_minimum_level is None:
                    continue
                candidate = source_minimum_level
                if method in LEVEL_REQUIREMENT_METHODS or method == 14:
                    candidate = max(candidate, requirement)
                elif method in LEVEL_UP_METHODS:
                    candidate += 1
                elif method not in IMMEDIATE_METHODS:
                    raise ValueError(
                        f"Unknown evolution method {method} for species {source_species_id}"
                    )
                target_minimum_level = minimum_levels[target_species_id]
                if (
                    target_minimum_level is None
                    or candidate < target_minimum_level
                ):
                    minimum_levels[target_species_id] = candidate
                    changed = True

    for species_id, entry in enumerate(species):
        if entry:
            if minimum_levels[species_id] is None:
                raise ValueError(f"Could not determine minimum level for species {species_id}")
            entry["minimum_level"] = minimum_levels[species_id]
    output_path.write_text(json.dumps(species, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote minimum levels to {output_path}")
