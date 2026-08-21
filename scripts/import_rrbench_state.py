#!/usr/bin/env python3
"""Convert an rrbench gzip raw state into an mGBA quick-slot state."""

import argparse
import gzip
from pathlib import Path

import mgba.core
import mgba.log
from mgba._pylib import lib
from mgba.image import Image


mgba.log.silence()

GBA_WIDTH = 240
GBA_HEIGHT = 160
STATE_FLAGS = 31


def repository_path(root: Path, supplied_path: Path, description: str) -> Path:
    if supplied_path.is_absolute():
        raise ValueError(f"{description} must be a path relative to the repository root")

    path = (root / supplied_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{description} must stay within the repository root") from error
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an rrbench gzip raw state into an mGBA quick-slot state."
    )
    parser.add_argument("save_state", type=Path, help="rrbench save_state.ss0")
    parser.add_argument(
        "--rom",
        type=Path,
        default=Path("radicalred.gba"),
        help="matching ROM to open in mGBA (default: radicalred.gba)",
    )
    parser.add_argument(
        "--slot", type=int, default=0, choices=range(10), help="mGBA slot (0-9)"
    )
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    state_path = repository_path(root, arguments.save_state, "save_state")
    rom_path = repository_path(root, arguments.rom, "rom")
    if not state_path.is_file():
        raise FileNotFoundError(state_path)
    if not rom_path.is_file():
        raise FileNotFoundError(rom_path)

    output_path = rom_path.with_suffix(f".ss{arguments.slot}")
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing mGBA state: {output_path}")

    try:
        raw_state = gzip.decompress(state_path.read_bytes())
    except gzip.BadGzipFile as error:
        raise ValueError(f"save_state is not an rrbench gzip raw state: {state_path}") from error

    core = mgba.core.load_path(str(rom_path))
    if core is None:
        raise RuntimeError(f"Failed to load ROM: {rom_path}")
    # mCoreSaveState needs a video buffer when writing its screenshot metadata.
    core.set_video_buffer(Image(GBA_WIDTH, GBA_HEIGHT))
    core.reset()
    if not core.load_raw_state(raw_state):
        raise RuntimeError(
            "Failed to load save state; ensure --rom is the same Radical Red build "
            "used to create the task"
        )
    if not lib.mCoreSaveState(core._core, arguments.slot, STATE_FLAGS):
        raise RuntimeError(f"Failed to write mGBA state: {output_path}")

    print(f"Imported {state_path.relative_to(root)}")
    print(f"Wrote {output_path.relative_to(root)}")


if __name__ == "__main__":
    main()
