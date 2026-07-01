#!/usr/bin/env python3
"""
Dump the player's party to notes/team.md by reading data from the emulator.

Usage:
    uv run python scripts/dump_team.py
Output: notes/team.md
"""

from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from emulator import Emulator
from context import build_team_description

ROM        = ROOT / "radicalred.gba"
SAVE_STATE = ROOT / "save_state.ss0"
OUTPUT     = ROOT / "notes" / "team.md"


def main() -> None:
    emu = Emulator(ROM, SAVE_STATE)
    emu.load_state()
    OUTPUT.write_text(build_team_description(emu.mem, ROM.read_bytes()))
    print(f"Written to {OUTPUT}")


if __name__ == "__main__":
    main()
