import json
from pathlib import Path
from types import SimpleNamespace

from rrbench.harness.trial import Trial


class FakeService:
    def __init__(self, task: object) -> None:
        self.task = task

    def observe(self) -> dict:
        return {"ok": True, "observation": {"phase": "no_battle"}}

    def lead(self, pokemon: str) -> dict:
        return {"ok": True, "ended": False, "won": False}

    def action(self, command: str) -> dict:
        won = command == "FIGHT Win"
        return {"ok": True, "ended": True, "won": won}

    def reset(self) -> dict:
        return self.observe()


def test_trial_counts_episodes_and_verifies_a_winning_replay(tmp_path: Path) -> None:
    task = SimpleNamespace(id="test")
    trajectory_path = tmp_path / "trajectory.jsonl"
    score_path = tmp_path / "score.json"
    trial = Trial(task, 2, trajectory_path, score_path, service_factory=FakeService)

    assert trial.handle({"verb": "lead", "pokemon": "Mawile"})["ok"]
    assert trial.handle({"verb": "reset"})["ok"]
    assert trial.handle({"verb": "lead", "pokemon": "Mawile"})["ok"]
    assert trial.handle({"verb": "action", "command": "FIGHT Win"})["won"]

    score = json.loads(score_path.read_text())
    events = [json.loads(line) for line in trajectory_path.read_text().splitlines()]
    assert score == {
        "task_id": "test",
        "status": "won",
        "reason": "replay_verified",
        "episodes": 2,
    }
    assert [event["type"] for event in events] == [
        "trial",
        "request",
        "request",
        "request",
        "request",
        "score",
    ]


def test_trial_finishes_when_last_episode_loses(tmp_path: Path) -> None:
    task = SimpleNamespace(id="test")
    score_path = tmp_path / "score.json"
    trial = Trial(
        task,
        1,
        tmp_path / "trajectory.jsonl",
        score_path,
        service_factory=FakeService,
    )

    trial.handle({"verb": "lead", "pokemon": "Mawile"})
    result = trial.handle({"verb": "action", "command": "FIGHT Lose"})

    assert result["won"] is False
    assert json.loads(score_path.read_text())["reason"] == "episode_budget_exhausted"
