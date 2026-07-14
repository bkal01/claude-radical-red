import json
from pathlib import Path

from rrbench.tasks import TaskSpec


class Trial:
    def __init__(
        self,
        task: TaskSpec,
        max_episodes: int,
        trajectory_path: Path,
        score_path: Path,
        service_factory=None,
    ) -> None:
        if max_episodes < 1:
            raise ValueError("max_episodes must be at least 1")
        if service_factory is None:
            raise ValueError("service_factory is required")

        self.task = task
        self.service_factory = service_factory
        self.service = service_factory(task)
        self.max_episodes = max_episodes
        self.episodes = 1
        self.trajectory_path = trajectory_path
        self.score_path = score_path
        self.episode_events: list[dict] = []
        self.finished = False

        self.trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        self.score_path.parent.mkdir(parents=True, exist_ok=True)
        self.trajectory_path.write_text("")
        self.write_event(
            {
                "type": "trial",
                "task_id": task.id,
                "max_episodes": max_episodes,
            }
        )

    def handle(self, request: object) -> dict:
        if self.finished:
            return {"ok": False, "error": "trial is complete"}
        if not isinstance(request, dict):
            return {"ok": False, "error": "request must be a JSON object"}

        verb = request.get("verb")
        if verb == "observe":
            return self.service.observe()
        if verb == "lead":
            pokemon = request.get("pokemon")
            if not isinstance(pokemon, str):
                return {"ok": False, "error": "lead requires a string pokemon"}
            result = self.service.lead(pokemon)
        elif verb == "action":
            command = request.get("command")
            if not isinstance(command, str):
                return {"ok": False, "error": "action requires a string command"}
            result = self.service.action(command)
        elif verb == "reset":
            if self.episodes >= self.max_episodes:
                self.finish("no_win", "episode_budget_exhausted")
                return {"ok": False, "error": "episode budget exhausted"}
            result = self.service.reset()
            if result["ok"]:
                self.episodes += 1
                self.episode_events = []
        else:
            return {"ok": False, "error": "unknown request verb"}

        if result["ok"] and verb in {"lead", "action", "reset"}:
            event = {
                "type": "request",
                "episode": self.episodes,
                "verb": verb,
                "request": request,
                "response": result,
            }
            self.write_event(event)
            if verb in {"lead", "action"}:
                self.episode_events.append(event)

        if result["ok"] and verb == "action" and result.get("ended"):
            if result.get("won"):
                if self.replay_winning_episode():
                    self.finish("won", "replay_verified")
                else:
                    self.finish("no_win", "replay_failed")
            elif self.episodes == self.max_episodes:
                self.finish("no_win", "episode_budget_exhausted")

        return result

    def replay_winning_episode(self) -> bool:
        service = self.service_factory(self.task)
        result: dict | None = None

        for event in self.episode_events:
            request = event["request"]
            if event["verb"] == "lead":
                result = service.lead(request["pokemon"])
            else:
                result = service.action(request["command"])
            if not result["ok"]:
                return False

        return bool(result and result.get("ended") and result.get("won"))

    def finish(self, status: str, reason: str) -> None:
        if self.finished:
            return

        score = {
            "task_id": self.task.id,
            "status": status,
            "reason": reason,
            "episodes": self.episodes,
        }
        self.score_path.write_text(json.dumps(score, separators=(",", ":")) + "\n")
        self.write_event({"type": "score", **score})
        self.finished = True

    def write_event(self, event: dict) -> None:
        with self.trajectory_path.open("a") as trajectory_file:
            trajectory_file.write(json.dumps(event, separators=(",", ":")) + "\n")
