#!/usr/bin/env python3
import argparse
import gzip
from pathlib import Path

import mgba.core
import mgba.log
from mgba._pylib import ffi, lib


mgba.log.silence()


STATE_FLAGS = 31


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export an mGBA quick-slot state as an rrbench gzip state."
    )
    parser.add_argument("slot_state", type=Path)
    arguments = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    supplied_path = arguments.slot_state
    if supplied_path.is_absolute():
        raise ValueError("slot_state must be a path relative to the repository root")

    source_path = (root / supplied_path).resolve()
    try:
        source_path.relative_to(root)
    except ValueError as error:
        raise ValueError("slot_state must stay within the repository root") from error
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    suffix = source_path.suffix
    if len(suffix) != 4 or not suffix.startswith(".ss") or not suffix[-1].isdigit():
        raise ValueError("slot_state must use mGBA's .ss0 through .ss9 slot filename")
    slot = int(suffix[-1])
    rom_path = source_path.with_suffix(".gba")
    if not rom_path.is_file():
        raise FileNotFoundError(
            f"Expected the matching ROM beside the slot state: {rom_path}"
        )

    output_path = root / "save_state.ss0"
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing save state: {output_path}")

    core = mgba.core.load_path(str(rom_path))
    if core is None:
        raise RuntimeError(f"Failed to load ROM: {rom_path}")
    core.reset()
    if not lib.mCoreLoadState(core._core, slot, STATE_FLAGS):
        raise RuntimeError(f"Failed to load mGBA slot state: {source_path}")

    raw_state = ffi.buffer(core.save_raw_state())[:]
    output_path.write_bytes(gzip.compress(raw_state, compresslevel=9))
    print(f"Exported {source_path.relative_to(root)}")
    print(f"Wrote {output_path.relative_to(root)}")


if __name__ == "__main__":
    main()
