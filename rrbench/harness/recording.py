from pathlib import Path


class TrialRecorder:
    def __init__(self, videos_path: Path) -> None:
        self.videos_path = videos_path
        self.episode = 1
        self.recorder = None
        self.video_path = None
        self.videos_path.mkdir(parents=True, exist_ok=True)

    def start(self, emulator) -> bool:
        if self.recorder is not None:
            return False

        from rrbench.video import VideoRecorder

        self.video_path = self.videos_path / f"episode-{self.episode:02d}.mp4"
        self.recorder = VideoRecorder(str(self.video_path))
        emulator.set_recorder(self.recorder)
        return True

    def close(self, emulator) -> None:
        if self.recorder is None:
            return
        emulator.set_recorder(None)
        self.recorder.close()
        self.recorder = None

    def discard(self, emulator) -> None:
        self.close(emulator)
        if self.video_path is not None:
            self.video_path.unlink(missing_ok=True)
            self.video_path = None

    def next_episode(self) -> None:
        self.episode += 1
