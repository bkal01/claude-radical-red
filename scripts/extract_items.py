#!/usr/bin/env python3
import argparse
import json
import struct
from pathlib import Path


ROOT = Path(__file__).parent.parent
ROM = ROOT / "radicalred.gba"
ITEM_TABLE_OFFSET = 0x013C0000
ITEM_TABLE_ENTRY_SIZE = 44
ITEM_COUNT = 750
DESCRIPTION_POINTER_OFFSET = 20
DESCRIPTION_OVERRIDES = {
    748: "This hooded cloak conceals the holder, protecting it from the additional effects of moves.",
}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "items.json",
    )
    arguments = parser.parse_args()
    rom = ROM.read_bytes()
    items = [None]
    for item_id in range(1, ITEM_COUNT):
        entry_offset = ITEM_TABLE_OFFSET + item_id * ITEM_TABLE_ENTRY_SIZE
        description_address = struct.unpack_from(
            "<I", rom, entry_offset + DESCRIPTION_POINTER_OFFSET
        )[0]
        description_offset = description_address - 0x08000000
        if not 0 <= description_offset < len(rom):
            raise ValueError(f"Invalid description pointer for item {item_id}")
        text = []
        for text_offset, max_length in ((entry_offset, 14), (description_offset, 256)):
            characters = []
            for value in rom[text_offset : text_offset + max_length]:
                if value == 0xFF:
                    break
                if 0xBB <= value <= 0xD4:
                    characters.append(chr(ord("A") + value - 0xBB))
                elif 0xD5 <= value <= 0xEE:
                    characters.append(chr(ord("a") + value - 0xD5))
                elif value in (0x00, 0xA0, 0xFE):
                    characters.append(" ")
                elif value == 0xAD:
                    characters.append(".")
                elif value == 0xAE:
                    characters.append("-")
                elif 0xA1 <= value <= 0xAA:
                    characters.append(str(value - 0xA1))
                elif value == 0xAB:
                    characters.append("!")
                elif value == 0xAC:
                    characters.append("?")
                elif value == 0xB4:
                    characters.append("'")
                elif value == 0xB8:
                    characters.append(",")
                elif value == 0xBA:
                    characters.append("/")
                elif value == 0x1B:
                    characters.append("é")
                elif value == 0x2D:
                    characters.append("-")
                elif value == 0x2E:
                    characters.append("+")
                elif value == 0x5B:
                    characters.append("%")
                elif value == 0x5C:
                    characters.append("(")
                elif value == 0x5D:
                    characters.append(")")
                elif value not in (0xB1, 0xB2):
                    characters.append("?")
            text.append(" ".join("".join(characters).split()))
        items.append(
            {
                "name": text[0],
                "description": DESCRIPTION_OVERRIDES.get(
                    item_id, text[1]
                ),
            }
        )

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(items, indent=2) + "\n")
    print(f"Wrote {len(items)} item entries to {arguments.output}")


if __name__ == "__main__":
    main()
