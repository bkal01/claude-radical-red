import json
import sys
from types import ModuleType
from pathlib import Path

from rrbench.harness.trial import Trial
from rrbench.tasks import TaskSpec
from tests.support.fakes import FakeService, FakeVideoRecorder


def test_winning_action_writes_score_and_closes_active_recorder(monkeypatch, tmp_path) -> None:
    fake_video_module = ModuleType("rrbench.video")
    fake_video_module.VideoRecorder = FakeVideoRecorder
    monkeypatch.setitem(sys.modules, "rrbench.video", fake_video_module)
    FakeVideoRecorder.instances.clear()

    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
    )
    service = FakeService(
        results={
            "action": {
                "ok": True,
                "messages": ["You won!"],
                "observation": {"phase": "ended", "won": True},
                "ended": True,
                "won": True,
            }
        }
    )
    score_path = tmp_path / "score.json"
    trial = Trial(
        task=task,
        max_episodes=1,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=score_path,
        record=True,
        videos_path=tmp_path / "videos",
    )

    trial.start(service)
    active_recorder = FakeVideoRecorder.instances[0]
    result = trial.handle({"verb": "action", "command": "FIGHT Tackle"}, service)

    assert result["won"] is True
    assert json.loads(score_path.read_text()) == {
        "task_id": "test",
        "status": "won",
        "reason": "environment_reported_win",
        "episodes": 1,
    }
    assert active_recorder.output_path == str(tmp_path / "videos" / "episode-01.mp4")
    assert active_recorder.closed is True
    assert service.emu.recorder is None
    assert trial.recorder.recorder is None


def test_losing_action_at_episode_limit_writes_no_win_score_and_closes_recorder(
    monkeypatch,
    tmp_path,
) -> None:
    fake_video_module = ModuleType("rrbench.video")
    fake_video_module.VideoRecorder = FakeVideoRecorder
    monkeypatch.setitem(sys.modules, "rrbench.video", fake_video_module)
    FakeVideoRecorder.instances.clear()

    task = TaskSpec(
        id="test",
        rom_path=Path("test.gba"),
        save_state_path=Path("test.ss0"),
        allowed_team_modifications=frozenset(),
    )
    service = FakeService(
        results={
            "action": {
                "ok": True,
                "messages": ["You lost!"],
                "observation": {"phase": "ended", "won": False},
                "ended": True,
                "won": False,
            }
        }
    )
    score_path = tmp_path / "score.json"
    trial = Trial(
        task=task,
        max_episodes=1,
        trajectory_path=tmp_path / "trajectory.jsonl",
        score_path=score_path,
        record=True,
        videos_path=tmp_path / "videos",
    )

    trial.start(service)
    active_recorder = FakeVideoRecorder.instances[0]
    result = trial.handle({"verb": "action", "command": "FIGHT Tackle"}, service)

    assert result["won"] is False
    assert json.loads(score_path.read_text()) == {
        "task_id": "test",
        "status": "no_win",
        "reason": "episode_budget_exhausted",
        "episodes": 1,
    }
    assert active_recorder.closed is True
    assert service.emu.recorder is None
    assert trial.recorder.recorder is None
