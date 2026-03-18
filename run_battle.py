import argparse
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

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
			# Keep Player_<id>.jsonl reserved for runner-level unified trace schema.
			# Do not pass raw model log file here to avoid mixing incompatible row formats.
			agent = AGENT_REGISTRY.build_agent(
				model_type=model_type,
				model_params=model_params,
				log_file=None,
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


_logger = logging.getLogger(__name__)


def _make_trace_row(env: LiarsDeckTextEnvV0, obs: Dict[str, Any], player_id: int, action: Dict[str, Any], agent: Optional[Any] = None) -> Dict[str, Any]:
	prompt = getattr(agent, "last_prompt", "") if agent is not None else ""
	return {
		"game_id": env.game.game_id,
		"event_id": env.game.event_id + 1,
		"player_id": player_id,
		"phase": obs["phase"],
		"message": obs["phase"],
		"prompt": prompt or "runner_generated_prompt_placeholder",
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


def _make_speech_trace_row(
	env: LiarsDeckTextEnvV0,
	obs: Dict[str, Any],
	player_id: int,
	speech_text: str,
	speech_prompt: str,
	reasoning_trace: str,
) -> Dict[str, Any]:
	return {
		"game_id": env.game.game_id,
		"event_id": env.game.event_id,
		"player_id": player_id,
		"phase": f"{obs['phase']}_speech",
		"message": f"{obs['phase']}_speech",
		"prompt": speech_prompt,
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
		"valid_actions": [{"type": "speech", "payload": "public_text"}],
		"response": speech_text,
		"selected_action": {"type": "speech", "text": speech_text},
		"reasoning_trace": reasoning_trace,
		"action_parse_status": "ok",
		"gen_times": 1,
		"latency_ms": 0,
	}


def _extract_reasoning_trace(agent: Any, raw_action: Any) -> str:
	if isinstance(raw_action, dict):
		for key in ["reason", "reasoning", "analysis", "thought", "rationale", "explanation"]:
			value = raw_action.get(key)
			if isinstance(value, str) and value.strip():
				return value.strip()

	response_text = getattr(agent, "last_response_text", "")
	if isinstance(response_text, str) and response_text.strip():
		clean_text = response_text.strip()
		clean_text = re.sub(r"```(?:json)?", "", clean_text)
		clean_text = clean_text.replace("```", "").strip()
		return clean_text

	return ""


def _shorten_reasoning_trace(reasoning_trace: str, max_chars: int = 420) -> str:
	text = (reasoning_trace or "").strip()
	if len(text) <= max_chars:
		return text
	return text[:max_chars].rstrip() + " ..."


def _fallback_speech_text(action: Dict[str, Any], obs: Dict[str, Any], max_chars: int) -> str:
	action_type = action.get("type", "play")
	if action_type == "call_liar":
		text = "I challenge that last claim."
	else:
		claimed_rank = action.get("claimed_rank", obs.get("public_state", {}).get("table_rank", "K"))
		claimed_count = action.get("claimed_count", len(action.get("cards", [])) if isinstance(action.get("cards", []), list) else 1)
		text = f"I play {claimed_count} card(s) as {claimed_rank}."
	return text[:max_chars]


def _clean_public_speech(
	raw_text: str,
	planned_action: Dict[str, Any],
	obs: Dict[str, Any],
	max_chars: int,
	max_sentences: int = 2,
) -> str:
	text = (raw_text or "").strip()
	if not text:
		return _fallback_speech_text(planned_action, obs, max_chars)

	text = re.sub(r"```(?:json|text|markdown)?", "", text, flags=re.I)
	text = text.replace("```", "")
	text = re.sub(r"\{\s*\"type\"\s*:\s*\"(play|call_liar|speech)\".*?\}", "", text, flags=re.I | re.S)

	lines = [line.strip() for line in text.splitlines() if line.strip()]
	filtered: List[str] = []
	blocked_markers = [
		"thinking process",
		"analyze the request",
		"analysis:",
		"current state:",
		"final check",
		"decision:",
		"let me analyze",
		"reasoning_trace",
		"output format",
	]
	for line in lines:
		line_lower = line.lower()
		if any(marker in line_lower for marker in blocked_markers):
			continue
		if re.match(r"^\d+[\).:\-]\s*", line):
			continue
		if line.startswith(("-", "*", "#", "**")):
			continue
		if len(line) < 3:
			continue
		filtered.append(line)

	text = " ".join(filtered).strip()
	text = re.sub(r"\s+", " ", text)
	text = re.sub(r"[*_`#]", "", text)

	# Keep only the first few natural sentences.
	sentences = re.split(r"(?<=[.!?])\s+", text)
	sentences = [s.strip() for s in sentences if s.strip()]
	if len(sentences) >= max_sentences:
		text = " ".join(sentences[:max_sentences])
	elif len(sentences) == 1:
		text = sentences[0]

	# Reject residual meta/internal-style outputs.
	if not text or any(token in text.lower() for token in ["thinking process", "analyze", "output json", "reasoning"]):
		text = _fallback_speech_text(planned_action, obs, max_chars)

	if len(text) > max_chars:
		text = text[:max_chars].rstrip()
		if text and text[-1].isalnum():
			text += "."

	return text


def _build_speech(
	agent: Any,
	obs: Dict[str, Any],
	raw_action: Any,
	planned_action: Dict[str, Any],
	max_chars: int,
	mode: str,
	reasoning_trace_max_chars: int,
	max_sentences: int,
) -> Dict[str, str]:
	reasoning_trace = _extract_reasoning_trace(agent=agent, raw_action=raw_action)
	reasoning_for_prompt = _shorten_reasoning_trace(reasoning_trace, max_chars=reasoning_trace_max_chars)
	speech_prompt = (
		"Public speech rewrite request:\n"
		f"phase={obs.get('phase')}\n"
		f"table_rank={obs.get('public_state', {}).get('table_rank')}\n"
		f"pile_size={obs.get('public_state', {}).get('pile_size')}\n"
		f"last_play={obs.get('public_state', {}).get('last_play')}\n"
		f"planned_action={planned_action}\n"
		f"reasoning_trace={reasoning_for_prompt}\n"
		f"max_chars={max_chars}"
	)

	speech_text = ""
	if mode == "llm_rewrite" and hasattr(agent, "generate_speech"):
		try:
			speech_text = agent.generate_speech(
				observation=obs,
				planned_action=planned_action,
				reasoning_trace=reasoning_for_prompt,
				max_chars=max_chars,
			)
		except Exception as exc:
			_logger.warning("speech generation failed, using fallback: %s", exc)
			speech_text = ""

	if not speech_text:
		if reasoning_trace:
			speech_text = reasoning_trace[:max_chars]
		else:
			speech_text = _fallback_speech_text(planned_action, obs, max_chars=max_chars)

	speech_text = _clean_public_speech(
		raw_text=speech_text,
		planned_action=planned_action,
		obs=obs,
		max_chars=max_chars,
		max_sentences=max_sentences,
	)

	return {
		"speech_text": speech_text.strip(),
		"speech_prompt": speech_prompt,
		"reasoning_trace": reasoning_for_prompt,
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
	speech_cfg = env_cfg.get("speech_injection", {})
	speech_enabled = bool(speech_cfg.get("enabled", True))
	speech_mode = speech_cfg.get("mode", "llm_rewrite")
	speech_max_chars = int(speech_cfg.get("max_chars", 180))
	speech_max_sentences = int(speech_cfg.get("max_sentences", 2))
	reasoning_trace_max_chars = int(speech_cfg.get("reasoning_trace_max_chars", 420))

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

		if speech_enabled:
			speech_bundle = _build_speech(
				agent=agent,
				obs=obs,
				raw_action=raw_action,
				planned_action=action,
				max_chars=speech_max_chars,
				mode=speech_mode,
				reasoning_trace_max_chars=reasoning_trace_max_chars,
				max_sentences=speech_max_sentences,
			)
			speech_text = speech_bundle["speech_text"]
			if speech_text:
				env.add_speech(player_id, speech_text)
				env.record_player_trace(
					player_id,
					_make_speech_trace_row(
						env=env,
						obs=obs,
						player_id=player_id,
						speech_text=speech_text,
						speech_prompt=speech_bundle["speech_prompt"],
						reasoning_trace=speech_bundle["reasoning_trace"],
					),
				)

		env.record_player_trace(player_id, _make_trace_row(env, obs, player_id, action, agent))
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
