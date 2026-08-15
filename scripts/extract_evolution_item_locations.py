import json
import re
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree


root = Path(__file__).parent.parent
workbook_path = root / "Item, TM, and Move Tutor Locations v4.1 - Radical Red.xlsx"
data_directory = root / "data" / "radical_red" / "v4.1"
items_path = data_directory / "items.json"
evolutions_path = data_directory / "evolutions.json"
output_path = data_directory / "route_evolution_item_map.json"
namespaces = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
shop_location_names = {"CELADON DEPT. STORE (4F)": "celadon_city"}

items = json.loads(items_path.read_text())
evolutions = json.loads(evolutions_path.read_text())
items_by_id = {item["id"]: item for item in items}
if len(items_by_id) != len(items):
    raise ValueError("items.json must contain unique item IDs")
evolution_item_ids = {
    evolution["requirement"]
    for evolution in evolutions
    if evolution["method_code"] == 7
}
if not evolution_item_ids <= set(items_by_id):
    raise ValueError("evolution item requirements must exist in items.json")
item_ids_by_name = defaultdict(list)
for item in items:
    item_ids_by_name[re.sub(r"[^a-z0-9]", "", item["name"].lower())].append(
        item["id"]
    )

with ZipFile(workbook_path) as archive:
    shared_strings_xml = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    shared_strings = [
        "".join(
            node.text or ""
            for node in entry.iter(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
            )
        )
        for entry in shared_strings_xml.findall("main:si", namespaces)
    ]
    shops_xml = ElementTree.fromstring(archive.read("xl/worksheets/sheet7.xml"))

location_item_ids = defaultdict(set)
current_location = None
for row in shops_xml.findall(".//main:row", namespaces):
    cells = {}
    for cell in row.findall("main:c", namespaces):
        value = cell.findtext("main:v", namespaces=namespaces)
        if value is None:
            continue
        if cell.get("t") == "s":
            value = shared_strings[int(value)]
        cells[re.match(r"[A-Z]+", cell.get("r")).group()] = value
    location_name = cells.get("F")
    if location_name:
        current_location = shop_location_names.get(location_name)
    item_name = cells.get("G")
    if current_location is None or not isinstance(item_name, str):
        continue
    normalized_item_name = re.sub(r"[^a-z0-9]", "", item_name.lower())
    matching_item_ids = item_ids_by_name.get(normalized_item_name, [])
    matching_evolution_item_ids = set(matching_item_ids) & evolution_item_ids
    if len(matching_evolution_item_ids) > 1:
        raise ValueError(f"Ambiguous evolution item in Shops sheet: {item_name}")
    location_item_ids[current_location].update(matching_evolution_item_ids)

if set().union(*location_item_ids.values()) != evolution_item_ids:
    missing_item_ids = sorted(evolution_item_ids - set().union(*location_item_ids.values()))
    raise ValueError(f"Missing evolution item locations: {missing_item_ids}")

route_item_map = {
    location: [
        {"id": item_id, "name": items_by_id[item_id]["name"]}
        for item_id in sorted(item_ids)
    ]
    for location, item_ids in sorted(location_item_ids.items())
}
output_path.write_text(json.dumps(route_item_map, indent=2) + "\n")
print(f"Wrote evolution item locations for {len(route_item_map)} locations to {output_path}")
