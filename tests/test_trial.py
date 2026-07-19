import json
from pathlib import Path
from types import SimpleNamespace

from rrbench.harness.trial import Trial


class FakeService:
    def __init__(self, task: object) -> None:
        self.task = task
        self.applied_team = None
        self.reset_calls = 0

    def observe(self) -> dict:
        return {"ok": True, "observation": {"phase": "no_battle"}}

    def team(self) -> dict:
        return {"ok": True, "team": {"members": []}}

    def lead(self, pokemon: str) -> dict:
        return {"ok": True, "ended": False, "won": False}

    def action(self, command: str) -> dict:
        won = command == "FIGHT Win"
        return {"ok": True, "ended": True, "won": won}

    def reset(self) -> dict:
        self.reset_calls += 1
        return self.observe()

    def apply_team(self, team: dict) -> dict:
        self.applied_team = team
        return {"ok": True}


def test_trial_counts_episodes_and_records_a_reported_win(tmp_path: Path) -> None:
    task = SimpleNamespace(id="test")
    service = FakeService(task)
    trajectory_path = tmp_path / "trajectory.jsonl"
    score_path = tmp_path / "score.json"
    trial = Trial(task, 2, trajectory_path, score_path)

    assert trial.handle({"verb": "lead", "pokemon": "Mawile"}, service)["ok"]
    assert trial.handle({"verb": "reset"}, service)["ok"]
    assert trial.handle({"verb": "lead", "pokemon": "Mawile"}, service)["ok"]
    assert trial.handle({"verb": "action", "command": "FIGHT Win"}, service)["won"]

    score = json.loads(score_path.read_text())
    events = [json.loads(line) for line in trajectory_path.read_text().splitlines()]
    assert score == {
        "task_id": "test",
        "status": "won",
        "reason": "environment_reported_win",
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
    service = FakeService(task)
    score_path = tmp_path / "score.json"
    trial = Trial(
        task,
        1,
        tmp_path / "trajectory.jsonl",
        score_path,
    )

    trial.handle({"verb": "lead", "pokemon": "Mawile"}, service)
    result = trial.handle({"verb": "action", "command": "FIGHT Lose"}, service)

    assert result["won"] is False
    assert json.loads(score_path.read_text())["reason"] == "episode_budget_exhausted"


def test_apply_team_resets_and_advances_the_episode(tmp_path: Path) -> None:
    task = SimpleNamespace(id="test")
    service = FakeService(task)
    trial = Trial(task, 2, tmp_path / "trajectory.jsonl", tmp_path / "score.json")
    team = {"members": []}

    assert trial.handle({"verb": "lead", "pokemon": "Mawile"}, service)["ok"]
    result = trial.handle({"verb": "apply-team", "team": team}, service)

    assert result == {"ok": True, "observation": {"phase": "no_battle"}}
    assert service.applied_team == team
    assert service.reset_calls == 1
    assert trial.episodes == 2


def test_team_is_read_only_and_available_before_a_battle(tmp_path: Path) -> None:
    task = SimpleNamespace(id="test")
    service = FakeService(task)
    trial = Trial(task, 1, tmp_path / "trajectory.jsonl", tmp_path / "score.json")

    result = trial.handle({"verb": "team"}, service)

    assert result == {"ok": True, "team": {"members": []}}
    assert trial.episodes == 1
