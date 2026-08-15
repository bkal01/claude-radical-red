import ast
import json
import re
from pathlib import Path
from urllib.request import urlopen


root = Path(__file__).parent.parent
source_commit = "488a0918194d567b5f7b02c396118d51fb9c81ce"
source_url = f"https://raw.githubusercontent.com/JwowSquared/Radical-Red-Pokedex/{source_commit}/data.js"
output_path = root / "data/radical_red/v4.1/evolutions.json"
species_path = root / "data/radical_red/v4.1/species.json"
method_names = {
    1: "friendship",
    2: "friendship_day",
    3: "friendship_night",
    4: "level",
    7: "item",
    8: "level_attack_greater_than_defense",
    9: "level_attack_equal_to_defense",
    10: "level_attack_less_than_defense",
    11: "level_silcoon",
    12: "level_cascoon",
    13: "level_ninjask",
    14: "level_shedinja",
    16: "level_rain",
    17: "move_type",
    18: "level_dark_type_party_member",
    20: "level_male",
    21: "level_female",
    22: "level_night",
    23: "level_day",
    26: "move",
    27: "specific_party_member",
    28: "rockruff_special",
    30: "toxel_amped",
    31: "toxel_low_key",
    254: "mega_evolution",
}

with urlopen(source_url, timeout=30) as response:
    source_text = response.read().decode()

source_text = re.sub(r"\bnull\b", "None", source_text)
source_text = re.sub(r"\btrue\b", "True", source_text)
source_text = re.sub(r"\bfalse\b", "False", source_text)
source_data = ast.literal_eval(source_text)
species = json.loads(species_path.read_text())
evolutions = []

for source_species_id, source_species in source_data["species"].items():
    if source_species_id >= len(species) or not species[source_species_id]:
        continue
    for evolution in source_species.get("evolutions", []):
        if not isinstance(evolution, list) or len(evolution) != 4 or any(
            type(value) is not int for value in evolution
        ):
            raise ValueError(
                f"Invalid evolution for species {source_species_id}: {evolution!r}"
            )
        method_code, requirement, target_species_id, condition = evolution
        if target_species_id >= len(species) or not species[target_species_id]:
            continue
        method = method_names.get(method_code)
        if method is None:
            raise ValueError(
                f"Unknown evolution method {method_code} for species {source_species_id}"
            )
        evolutions.append(
            {
                "source_species_id": source_species_id,
                "target_species_id": target_species_id,
                "method_code": method_code,
                "method": method,
                "requirement": requirement,
                "condition": condition,
            }
        )

evolutions.sort(
    key=lambda evolution: (
        evolution["source_species_id"],
        evolution["target_species_id"],
        evolution["method_code"],
        evolution["requirement"],
        evolution["condition"],
    )
)
output_path.write_text(json.dumps(evolutions, indent=2) + "\n")
print(f"Wrote {len(evolutions)} evolution edges to {output_path}")
