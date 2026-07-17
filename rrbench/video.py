import imageio
import numpy as np
from PIL import Image


class VideoRecorder:
    def __init__(self, output_path: str, fps: int = 30):
        self.writer = imageio.get_writer(
            output_path,
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
        )

    def capture(self, image) -> None:
        pil = image.to_pil().convert("RGB")
        scale = 4
        pil = pil.resize(
            (pil.width * scale, pil.height * scale),
            Image.NEAREST,
        )
        self.writer.append_data(np.asarray(pil))

    def close(self) -> None:
        self.writer.close()
