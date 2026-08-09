import ast
import json
import re
from pathlib import Path
from urllib.request import urlopen


root = Path(__file__).parent.parent
source_commit = "488a0918194d567b5f7b02c396118d51fb9c81ce"
source_url = f"https://raw.githubusercontent.com/JwowSquared/Radical-Red-Pokedex/{source_commit}/data.js"
output_paths = [root / "data/radical_red/v4.1/learnsets.json"]
moves_path = root / "data/radical_red/v4.1/moves.json"
species_path = root / "data/radical_red/v4.1/species.json"

with urlopen(source_url, timeout=30) as response:
    source_text = response.read().decode()

source_text = re.sub(r"\bnull\b", "None", source_text)
source_text = re.sub(r"\btrue\b", "True", source_text)
source_text = re.sub(r"\bfalse\b", "False", source_text)
source_data = ast.literal_eval(source_text)
moves = json.loads(moves_path.read_text())
species = json.loads(species_path.read_text())
valid_move_ids = {move_id for move_id, move in enumerate(moves) if move}


def filter_move_ids(move_ids):
    return [move_id for move_id in move_ids if move_id in valid_move_ids]


pre_evolution_ids = [set() for _ in species]
for source_species_id, source_species in source_data["species"].items():
    if not species[source_species_id]:
        continue
    for evolution in source_species.get("evolutions", []):
        target_species_id = evolution[2]
        if species[target_species_id]:
            pre_evolution_ids[target_species_id].add(source_species_id)

learnsets = []
for species_id, entry in enumerate(species):
    if not entry:
        learnsets.append(None)
        continue

    source_species = source_data["species"].get(species_id)
    if not source_species:
        learnsets.append(
            {
                "level_up": [],
                "tm_hm": [],
                "tutor": [],
                "egg": [],
                "pre_evolution_ids": [],
                "pre_evolution": [],
                "event": [],
            }
        )
        continue

    level_up = []
    for move_id, level in source_species.get("levelupMoves", []):
        if move_id not in valid_move_ids:
            raise ValueError(f"Invalid level-up move {move_id} for {entry['name']}")
        level_up.append({"move_id": move_id, "level": level})

    learnsets.append(
        {
            "level_up": level_up,
            "tm_hm": filter_move_ids(
                source_data["tmMoves"].get(tm_id)
                for tm_id in source_species.get("tmMoves", [])
            ),
            "tutor": filter_move_ids(
                source_data["tutorMoves"].get(tutor_id)
                for tutor_id in source_species.get("tutorMoves", [])
            ),
            "egg": filter_move_ids(source_species.get("eggMoves", [])),
            "pre_evolution_ids": sorted(pre_evolution_ids[species_id]),
            "pre_evolution": filter_move_ids(source_species.get("prevoMoves", [])),
            "event": filter_move_ids(source_species.get("eventMoves", [])),
        }
    )

serialized_learnsets = f"{json.dumps(learnsets, indent=2)}\n"
for output_path in output_paths:
    output_path.write_text(serialized_learnsets)

print(f"Wrote {len(learnsets)} learnsets to {', '.join(map(str, output_paths))}")
