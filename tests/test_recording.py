import sys
from pathlib import Path
from types import SimpleNamespace

from rrbench.harness.recording import TrialRecorder


def test_trial_recorder_creates_and_finalizes_episode_videos(
    tmp_path: Path, monkeypatch
) -> None:
    recorders = []

    class FakeEmulator:
        def __init__(self) -> None:
            self.recorder = None

        def set_recorder(self, recorder) -> None:
            self.recorder = recorder

    class FakeRecorder:
        def __init__(self, output_path: str) -> None:
            self.output_path = output_path
            self.closed = False
            recorders.append(self)

        def close(self) -> None:
            self.closed = True

    monkeypatch.setitem(sys.modules, "rrbench.video", SimpleNamespace(VideoRecorder=FakeRecorder))
    emulator = FakeEmulator()
    recorder = TrialRecorder(tmp_path / "videos")

    assert recorder.start(emulator)
    recorder.close(emulator)
    recorder.next_episode()
    assert recorder.start(emulator)
    recorder.close(emulator)

    assert [Path(item.output_path).name for item in recorders] == [
        "episode-01.mp4",
        "episode-02.mp4",
    ]
    assert all(item.closed for item in recorders)
