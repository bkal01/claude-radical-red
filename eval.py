import argparse
from pathlib import Path

from agents import REGISTRY
from battle import EpisodeRecord, run as run_battle
from context import build_team_description
from emulator import Emulator
from party import Party
from team import TeamConfig
from video import VideoRecorder

ROM_PATH        = "radicalred.gba"
SAVE_STATE_PATH = "save_state.ss0"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-episodes", type=int, default=1)
    parser.add_argument("--agent", default="simple", choices=REGISTRY.keys())
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--optimize-team", action="store_true")
    parser.add_argument("--debug", action="store_true",
                        help="log the exact full LLM input prompt and output for each agent step")
    args = parser.parse_args()

    emu = Emulator(ROM_PATH, SAVE_STATE_PATH)
    emu.load_state()
    rom = Path(ROM_PATH).read_bytes()
    team_config = TeamConfig.from_mem(emu.mem)
    team = build_team_description(emu.mem, rom)

    agent = REGISTRY[args.agent].from_args(team, args)

    recorder = None
    if args.record:
        video_path = f"logs/battle_{agent.run_id}.mp4"
        recorder = VideoRecorder(video_path)
        emu.set_recorder(recorder)
        print(f"Recording to {video_path}")

    try:
        for episode_idx in range(agent.max_episodes):
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

            if args.optimize_team and episode_idx < agent.max_episodes - 1:
                proposed = agent.propose_team(team_config)
                if proposed is not None:
                    team_config = proposed
                    team_config.apply(emu.mem)
                    agent.team = build_team_description(emu.mem, rom)

    finally:
        if recorder is not None:
            recorder.close()
        if hasattr(agent, "total_input_tokens"):
            print(f"\nTokens used: {agent.total_input_tokens:,} in / {agent.total_output_tokens:,} out")


if __name__ == "__main__":
    main()
