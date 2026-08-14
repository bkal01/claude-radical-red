import json
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "species_path",
    [
        "data/radical_red/v4.1/species.json",
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


def test_evolution_data_retains_requirements() -> None:
    repository = Path(__file__).resolve().parents[1]
    data_directory = repository / "data" / "radical_red" / "v4.1"
    species = json.loads((data_directory / "species.json").read_text())
    learnsets = json.loads((data_directory / "learnsets.json").read_text())
    evolutions = json.loads((data_directory / "evolutions.json").read_text())

    assert evolutions
    assert all(
        set(evolution)
        == {
            "source_species_id",
            "target_species_id",
            "method_code",
            "method",
            "requirement",
            "condition",
        }
        and type(evolution["source_species_id"]) is int
        and type(evolution["target_species_id"]) is int
        and type(evolution["method_code"]) is int
        and isinstance(evolution["method"], str)
        and type(evolution["requirement"]) is int
        and type(evolution["condition"]) is int
        and species[evolution["source_species_id"]]
        and species[evolution["target_species_id"]]
        for evolution in evolutions
    )
    assert {
        (evolution["source_species_id"], evolution["target_species_id"])
        for evolution in evolutions
    } == {
        (source_species_id, target_species_id)
        for target_species_id, learnset in enumerate(learnsets)
        if learnset
        for source_species_id in learnset["pre_evolution_ids"]
    }
    assert {
        "source_species_id": 568,
        "target_species_id": 569,
        "method_code": 7,
        "method": "item",
        "requirement": 97,
        "condition": 0,
    } in evolutions
