import argparse
from pathlib import Path

from agents import REGISTRY
from battle import EpisodeRecord, run as run_battle
from emulator import Emulator
from party import Party
from team import TeamConfig
from video import VideoRecorder

ROM_PATH        = "radicalred.gba"
SAVE_STATE_PATH = "save_state.ss0"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", default="default")
    parser.add_argument("--max-episodes", type=int, default=1)
    parser.add_argument("--agent", default="simple", choices=REGISTRY.keys())
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--optimize-team", action="store_true")
    args = parser.parse_args()

    team = Path(f"data/teams/{args.team}.md").read_text()
    emu = Emulator(ROM_PATH, SAVE_STATE_PATH)
    agent = REGISTRY[args.agent].from_args(team, args)

    recorder = None
    if args.record:
        video_path = f"logs/battle_{agent.run_id}.mp4"
        recorder = VideoRecorder(video_path)
        emu.set_recorder(recorder)
        print(f"Recording to {video_path}")

    emu.load_state()
    team_config = TeamConfig.from_mem(emu.mem)

    try:
        for _ in range(agent.max_episodes):
            emu.load_state()
            team_config.apply(emu.mem)

            party = Party(emu.mem)
            lead = agent.pick_lead()
            party.set_lead(lead)

            result = run_battle(emu, agent, party)

            record = EpisodeRecord(
                episode_num=len(agent.prior_episodes) + 1,
                won=result.won,
                turns=result.turns,
                pokemon_remaining=result.pokemon_remaining,
                party_names=party.names,
                steps=result.steps,
            )
            agent.prior_episodes.append(record)

            outcome = "WIN" if result.won else "LOSS"
            print(f"Episode {record.episode_num}: {outcome} in {result.turns} turns")

            if result.won:
                break

            if args.optimize_team:
                proposed = agent.propose_team(team_config)
                if proposed is not None:
                    team_config = proposed

    finally:
        if recorder is not None:
            recorder.close()
        if hasattr(agent, "total_input_tokens"):
            print(f"\nTokens used: {agent.total_input_tokens:,} in / {agent.total_output_tokens:,} out")


if __name__ == "__main__":
    main()
