import argparse
import json
import os

from liarsdeck.agents.base_agent import RandomAgent
from liarsdeck.envs.liarsdeck_text_env_v0 import LiarsDeckTextEnvV0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log_save_path", type=str, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num_players", type=int, default=4)
    parser.add_argument("--max_steps", type=int, default=2000)
    args = parser.parse_args()

    env = LiarsDeckTextEnvV0(
        num_players=args.num_players,
        seed=args.seed,
        ruleset="basic",
        env_version="v0.1",
        log_save_path=args.log_save_path,
    )
    env.reset(
        game_id="game_0001",
        player_meta=[
            {
                "player_id": player_id,
                "model_name": "single_policy_smoke",
                "provider": "local",
                "temperature": 0.0,
            }
            for player_id in range(1, args.num_players + 1)
        ],
    )

    agent = RandomAgent(seed=args.seed)
    done = False
    step_count = 0

    while not done and step_count < args.max_steps:
        obs = env.get_observation()
        player_id = obs["current_act_idx"]
        action = agent.act(obs)

        # record minimal per-player decision trace row for schema contract
        trace_row = {
            "game_id": env.game.game_id,
            "event_id": env.game.event_id + 1,
            "player_id": player_id,
            "phase": obs["phase"],
            "message": obs["phase"],
            "prompt": "smoke_step_prompt",
            "observation_summary": {
                "table_rank": obs["public_state"]["table_rank"],
                "pile_size": obs["public_state"]["pile_size"],
                "alive_players": [
                    int(pid)
                    for pid, status in obs["public_state"]["players_status"].items()
                    if status["is_alive"]
                ],
                "self_card_count": len(obs["private_state"]["self_hand"]),
            },
            "valid_actions": [
                {"type": item[0], "payload": item[1]} for item in obs.get("valid_action", [])
            ],
            "response": json.dumps(action, ensure_ascii=False),
            "selected_action": action,
            "action_parse_status": "ok",
            "gen_times": 1,
            "latency_ms": 0,
        }
        env.record_player_trace(player_id, trace_row)

        _, _, done, _ = env.step(action)
        step_count += 1

    if not done:
        raise RuntimeError("Smoke test did not finish within max_steps")

    # Ensure files exist
    required_files = [
        "game_log.json",
        "game_meta.json",
        *[f"Player_{player_id}.jsonl" for player_id in range(1, args.num_players + 1)],
    ]
    missing = [file_name for file_name in required_files if not os.path.exists(os.path.join(args.log_save_path, file_name))]
    if missing:
        raise RuntimeError(f"Missing required files: {missing}")

    print("Smoke test success.")
    print("Output directory:", args.log_save_path)


if __name__ == "__main__":
    main()
