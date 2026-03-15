import argparse
import json
import os
from typing import Any, Dict

import yaml

from liarsdeck.agents.base_agent import RandomAgent
from liarsdeck.envs.liarsdeck_text_env_v0 import LiarsDeckTextEnvV0
from liarsdeck.registry import AGENT_REGISTRY


def _build_agents(num_players: int, agent_config: Dict[str, Any], log_save_path: str):
	default_cfg = agent_config.get("default_model", {"model_type": "random", "model_params": {}})
	per_player_cfg = agent_config.get("per_player", {})

	agents = {}
	player_meta = []

	for player_id in range(1, num_players + 1):
		cfg = per_player_cfg.get(str(player_id), default_cfg)
		model_type = cfg.get("model_type", "random")
		model_params = cfg.get("model_params", {})

		if model_type == "random":
			agent = RandomAgent(seed=model_params.get("seed"))
		else:
			log_file = os.path.join(log_save_path, f"Player_{player_id}.jsonl")
			agent = AGENT_REGISTRY.build_agent(
				model_type=model_type,
				model_params=model_params,
				log_file=log_file,
			)
			if getattr(agent, "client", None) is None:
				raise RuntimeError(
					f"Agent '{model_type}' for player {player_id} has no initialized client. "
					"Install required SDKs and provide valid endpoint/auth settings."
				)

		agents[player_id] = agent
		player_meta.append(
			{
				"player_id": player_id,
				"model_name": model_type,
				"provider": model_params.get("provider", "local"),
				"temperature": model_params.get("temperature", 0.0),
			}
		)

	return agents, player_meta


def _make_trace_row(env: LiarsDeckTextEnvV0, obs: Dict[str, Any], player_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
	return {
		"game_id": env.game.game_id,
		"event_id": env.game.event_id + 1,
		"player_id": player_id,
		"phase": obs["phase"],
		"message": obs["phase"],
		"prompt": "runner_generated_prompt_placeholder",
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
		"valid_actions": [{"type": item[0], "payload": item[1]} for item in obs.get("valid_action", [])],
		"response": json.dumps(action, ensure_ascii=False),
		"selected_action": action,
		"action_parse_status": "ok",
		"gen_times": 1,
		"latency_ms": 0,
	}


def _safe_play_action(obs: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
	hand = list(obs.get("private_state", {}).get("self_hand", []))
	table_rank = obs.get("public_state", {}).get("table_rank", "K")

	if not hand:
		return {"type": "call_liar"}

	raw_cards = candidate.get("cards", []) if isinstance(candidate, dict) else []
	if not isinstance(raw_cards, list):
		raw_cards = []

	remaining = list(hand)
	cards: list = []
	for card in raw_cards:
		if card in remaining and len(cards) < 3:
			cards.append(card)
			remaining.remove(card)

	if len(cards) == 0:
		cards = [hand[0]]

	claimed_rank = candidate.get("claimed_rank", table_rank) if isinstance(candidate, dict) else table_rank
	if claimed_rank not in ["K", "Q", "A"]:
		claimed_rank = table_rank

	return {
		"type": "play",
		"cards": cards,
		"claimed_rank": claimed_rank,
		"claimed_count": len(cards),
	}


def _sanitize_action(obs: Dict[str, Any], action: Any) -> Dict[str, Any]:
	valid_types = {item[0] for item in obs.get("valid_action", []) if isinstance(item, (list, tuple)) and len(item) >= 1}

	if not isinstance(action, dict):
		action = {}

	action_type = action.get("type")
	if action_type == "call_liar" and "call_liar" in valid_types:
		return {"type": "call_liar"}

	if action_type == "play" and "play" in valid_types:
		return _safe_play_action(obs, action)

	if "play" in valid_types:
		return _safe_play_action(obs, action)

	if "call_liar" in valid_types:
		return {"type": "call_liar"}

	return {"type": "call_liar"}


def run_one_game(config: Dict[str, Any], log_save_path: str, seed_override=None, max_steps=4000):
	env_cfg = config.get("env_config", {})
	num_players = int(env_cfg.get("num_players", 4))
	ruleset = env_cfg.get("ruleset", "basic")
	seed = int(seed_override if seed_override is not None else env_cfg.get("seed", 42))
	game_id = env_cfg.get("game_id", "game_0001")

	os.makedirs(log_save_path, exist_ok=True)

	agents, player_meta = _build_agents(num_players=num_players, agent_config=config.get("agent_config", {}), log_save_path=log_save_path)

	env = LiarsDeckTextEnvV0(
		num_players=num_players,
		seed=seed,
		ruleset=ruleset,
		env_version=env_cfg.get("env_version", "v0.1"),
		log_save_path=log_save_path,
	)
	env.reset(game_id=game_id, player_meta=player_meta)

	step_count = 0
	done = False
	while not done and step_count < max_steps:
		obs = env.get_observation()
		player_id = obs["current_act_idx"]
		agent = agents[player_id]
		raw_action = agent.act(obs)
		action = _sanitize_action(obs, raw_action)
		env.record_player_trace(player_id, _make_trace_row(env, obs, player_id, action))
		_, _, done, _ = env.step(action)
		step_count += 1

	if not done:
		raise RuntimeError(f"Game did not finish in {max_steps} steps")

	with open(os.path.join(log_save_path, "config.yaml"), "w", encoding="utf-8") as file:
		yaml.safe_dump(config, file, sort_keys=False)

	return {
		"log_save_path": log_save_path,
		"steps": step_count,
	}


def main_cli():
	parser = argparse.ArgumentParser()
	parser.add_argument("--config", type=str, required=True)
	parser.add_argument("--log_save_path", type=str, required=True)
	parser.add_argument("--seed", type=int, default=None)
	parser.add_argument("--max_steps", type=int, default=4000)
	args = parser.parse_args()

	with open(args.config, "r", encoding="utf-8") as file:
		config = yaml.safe_load(file)

	result = run_one_game(
		config=config,
		log_save_path=args.log_save_path,
		seed_override=args.seed,
		max_steps=args.max_steps,
	)
	print(f"Single-game run completed: {result['log_save_path']} (steps={result['steps']})")


if __name__ == "__main__":
	main_cli()
