import gzip
from pathlib import Path

import mgba.core
from mgba.gba import GBA
from mgba.image import Image


GBA_WIDTH  = 240
GBA_HEIGHT = 160

KEY_A      = GBA.KEY_A
KEY_B      = GBA.KEY_B
KEY_SELECT = GBA.KEY_SELECT
KEY_START  = GBA.KEY_START
KEY_UP     = GBA.KEY_UP
KEY_DOWN   = GBA.KEY_DOWN
KEY_LEFT   = GBA.KEY_LEFT
KEY_RIGHT  = GBA.KEY_RIGHT
KEY_L      = GBA.KEY_L
KEY_R      = GBA.KEY_R


class Emulator:
    def __init__(self, rom_path: str | Path, save_state_path: str | Path):
        self._save_state_path = Path(save_state_path)

        core = mgba.core.load_path(str(rom_path))
        if core is None:
            raise RuntimeError(f"Failed to load ROM: {rom_path}")
        self._core: GBA = core

        self._image = Image(GBA_WIDTH, GBA_HEIGHT)
        self._core.set_video_buffer(self._image)
        self._core.reset()

    def load_state(self) -> None:
        """Reset to the save state loaded at construction time."""
        raw = gzip.decompress(self._save_state_path.read_bytes())
        if not self._core.load_raw_state(raw):
            raise RuntimeError(f"Failed to load save state: {self._save_state_path}")

    @property
    def mem(self):
        """Memory object for use with memory.py functions."""
        return self._core.memory

    def step(self, frames: int = 1) -> None:
        for _ in range(frames):
            self._core.run_frame()

    def press(self, key: int, hold_frames: int = 1) -> None:
        self._core.set_keys(key)
        self.step(hold_frames)
        self._core.set_keys()
        self.step(1)

    def screenshot(self) -> Image:
        return self._image
