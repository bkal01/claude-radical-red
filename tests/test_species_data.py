import json
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "species_path",
    [
        "data/radical_red/v4.1/species.json",
        "tasks/giovanni-abilities-only/environment/data/species.json",
        "tasks/giovanni-items-only/environment/data/species.json",
        "tasks/giovanni-moves-only/environment/data/species.json",
    ],
)
def test_task_species_data_is_clean_and_categorized(species_path) -> None:
    repository = Path(__file__).resolve().parents[1]
    species = json.loads((repository / species_path).read_text())

    assert len(species) == 1376
    assert species[412] is None
    assert species[1375]["name"] == "Chillet"
    assert species[1375]["source"] == "radical_red"
    assert species[1286]["form"] == "sevii"
    assert species[1286]["source"] == "radical_red"
    assert species[29]["name"] == "Nidoran♀"
    assert species[32]["name"] == "Nidoran♂"
    assert species[777]["name"] == "Flabébé"
    assert species[989]["name"] == "Type: Null"
    assert all(
        entry is None or {
            "name",
            "form",
            "source",
            "types",
            "base_stats",
            "growth_rate",
            "abilities",
            "minimum_level",
        } <= set(entry)
        for entry in species
    )
    assert all(
        entry is None
        or type(entry["minimum_level"]) is int
        and entry["minimum_level"] >= 1
        for entry in species
    )
    assert species[404]["growth_rate"] == "slow"
    assert species[935]["growth_rate"] == "medium_fast"
    assert species[942]["minimum_level"] == 1
    assert species[943]["minimum_level"] == 16
    assert species[944]["minimum_level"] == 36
    legendary_names = {
        "Mewtwo",
        "Lugia",
        "Ho-Oh",
        "Dialga",
        "Palkia",
        "Giratina",
        "Reshiram",
        "Zekrom",
        "Kyurem",
        "Xerneas",
        "Yveltal",
        "Zacian",
        "Zamazenta",
        "Eternatus",
        "Koraidon",
        "Miraidon",
    }
    assert all(
        entry is None
        or entry["name"] not in legendary_names
        or entry["minimum_level"] == 1
        for entry in species
    )
