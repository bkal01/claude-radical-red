#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from rrbench.interface.service import BattleService
from rrbench.tasks import load_task
from rrbench.video import VideoRecorder


parser = argparse.ArgumentParser(
    description="Replay every episode from a Harbor job with the current battle server."
)
parser.add_argument("job_id", help="Harbor job UUID from jobs/<job-name>/result.json")
arguments = parser.parse_args()

repository_path = Path(__file__).resolve().parents[1]
job_paths = [
    result_path.parent
    for result_path in (repository_path / "jobs").glob("*/result.json")
    if json.loads(result_path.read_text()).get("id") == arguments.job_id
]
if not job_paths:
    raise SystemExit(f"No job found for ID {arguments.job_id!r}")
if len(job_paths) > 1:
    raise SystemExit(f"More than one job matches ID {arguments.job_id!r}")

trial_paths = sorted(
    path
    for path in job_paths[0].iterdir()
    if (path / "artifacts" / "var" / "log" / "battle" / "trajectory.jsonl").is_file()
)
if not trial_paths:
    raise SystemExit(f"Job {arguments.job_id!r} has no battle trajectories")

for trial_path in trial_paths:
    trajectory_path = (
        trial_path / "artifacts" / "var" / "log" / "battle" / "trajectory.jsonl"
    )
    events = [json.loads(line) for line in trajectory_path.read_text().splitlines()]
    request_events = [event for event in events if event.get("type") == "request"]
    if not request_events:
        raise SystemExit(f"{trial_path.name} has no replayable requests")

    trial_config = json.loads((trial_path / "config.json").read_text())
    task_path = (repository_path / trial_config["task"]["path"]).resolve()
    if not task_path.is_dir():
        raise SystemExit(f"Task directory no longer exists: {task_path}")

    video_path = trajectory_path.parent / "videos"
    video_path.mkdir(parents=True, exist_ok=True)
    existing_videos = list(video_path.glob("episode-*.mp4"))
    if existing_videos:
        raise SystemExit(
            f"Refusing to overwrite existing episode videos in {video_path}: "
            f"{existing_videos}"
        )

    service = BattleService(load_task(task_path))
    temporary_video_path = Path(tempfile.mkdtemp(prefix=".replay-", dir=video_path))
    active_episode = None
    recorder = None
    completed = False
    try:
        for index, event in enumerate(request_events, 1):
            episode = event.get("episode")
            if not isinstance(episode, int) or episode < 1:
                raise RuntimeError(f"Request {index} has an invalid episode number")
            if episode != active_episode:
                if recorder is not None:
                    service.emu.set_recorder(None)
                    recorder.close()
                active_episode = episode
                recorder = VideoRecorder(
                    str(temporary_video_path / f"episode-{episode:02d}.mp4")
                )
                service.emu.set_recorder(recorder)

            request = event.get("request")
            verb = event.get("verb")
            if not isinstance(request, dict):
                raise RuntimeError(f"Request {index} is not an object")
            if verb == "apply-team":
                actual = service.apply_team(request["team"])
                if actual["ok"]:
                    reset_result = service.reset()
                    if reset_result["ok"]:
                        actual["observation"] = reset_result["observation"]
                    else:
                        actual = reset_result
            elif verb == "lead":
                actual = service.lead(request["pokemon"])
            elif verb == "action":
                actual = service.action(request["command"])
            elif verb == "reset":
                actual = service.reset()
            else:
                raise RuntimeError(f"Request {index} uses unsupported verb {verb!r}")

            if actual != event.get("response"):
                raise RuntimeError(
                    f"Replay diverged at request {index} in episode {episode}"
                )
        completed = True
    finally:
        if recorder is not None:
            service.emu.set_recorder(None)
            recorder.close()
        if not completed:
            shutil.rmtree(temporary_video_path, ignore_errors=True)

    for temporary_video in temporary_video_path.glob("episode-*.mp4"):
        temporary_video.replace(video_path / temporary_video.name)
    temporary_video_path.rmdir()
    print(json.dumps({"trial": trial_path.name, "videos_path": str(video_path)}))
