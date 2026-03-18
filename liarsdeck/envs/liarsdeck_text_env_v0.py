from copy import deepcopy
import os
from typing import Any, Dict, List, Optional

try:
	import gym
except Exception:  # pragma: no cover - fallback for environments without gym installed
	class _DummyEnv:
		pass

	class _DummyGym:
		Env = _DummyEnv

	gym = _DummyGym()

from liarsdeck.game import LiarsDeckGame
from liarsdeck.helper.log_utils import append_jsonl, write_json
from liarsdeck.helper.utils import compact_events, normalize_action


class LiarsDeckTextEnvV0(gym.Env):
	def __init__(self, **kwargs):
		self.num_players = kwargs.get("num_players", 4)
		self.ruleset = kwargs.get("ruleset", "basic")
		self.seed = kwargs.get("seed", None)
		self.env_version = kwargs.get("env_version", "v0.1")
		self.log_save_path = kwargs.get("log_save_path", os.path.join(os.getcwd(), "tmp_logs"))
		self.max_visible_events = kwargs.get("max_visible_events", 80)

		self.game = LiarsDeckGame(
			num_players=self.num_players,
			seed=self.seed,
			ruleset=self.ruleset,
			env_version=self.env_version,
		)

		self.current_act_idx = 1
		self.phase = "setup"
		self.player_trace_buffer: Dict[int, List[Dict[str, Any]]] = {player_id: [] for player_id in range(1, self.num_players + 1)}
		self.player_meta: List[Dict[str, Any]] = []

	def reset(self, **kwargs):
		game_id = kwargs.get("game_id", None)
		public_state = self.game.reset(game_id=game_id)
		self.current_act_idx = public_state["current_turn"]
		self.phase = self._make_phase_name()
		self.player_trace_buffer = {player_id: [] for player_id in range(1, self.num_players + 1)}
		self.player_meta = kwargs.get("player_meta", [])
		return self.get_observation()

	def step(self, action):
		normalized_action = normalize_action(action)
		self.game.step(self.current_act_idx, normalized_action)
		self.current_act_idx = self.game.current_turn
		self.phase = self._make_phase_name()

		done = self.game.game_over
		reward = [0 for _ in range(self.num_players)]
		info: Dict[str, Any] = {}

		if done:
			winner = self.game.winner
			info = {"winner": winner}
			for player_id in range(1, self.num_players + 1):
				reward[player_id - 1] = 1 if player_id == winner else -1
			self._flush_logs()

		return self.get_observation(), reward, done, info

	def get_observation(self) -> Dict[str, Any]:
		player_id = self.current_act_idx
		private_state = self.game.get_private_state(player_id)
		visible_events = compact_events(self.game.get_visible_events(player_id), max_items=self.max_visible_events)
		valid_actions = self._valid_actions_as_tuples(self.game.get_valid_actions(player_id))

		return {
			"current_act_idx": player_id,
			"identity": "player",
			"phase": self.phase,
			"valid_action": valid_actions,
			"game_log": deepcopy(visible_events),
			"public_state": {
				"table_rank": private_state["table_rank"],
				"pile_size": private_state["pile_size"],
				"current_turn": private_state["current_turn"],
				"last_play": private_state["last_play"],
				"players_status": private_state["players_status"],
			},
			"private_state": {
				"self_hand": private_state["self_hand"],
			},
			"roles": ["player" for _ in range(self.num_players)],
		}

	def add_speech(self, player_id: int, text: str) -> None:
		self.game.add_speech(player_id, text)

	def record_player_trace(self, player_id: int, trace_row: Dict[str, Any]) -> None:
		if player_id not in self.player_trace_buffer:
			self.player_trace_buffer[player_id] = []
		self.player_trace_buffer[player_id].append(trace_row)

	def _valid_actions_as_tuples(self, valid_actions: List[Dict[str, Any]]) -> List[Any]:
		tuples = []
		for action in valid_actions:
			action_type = action.get("type")
			if action_type == "play":
				tuples.append(("play", "cards_from_hand"))
			elif action_type == "call_liar":
				tuples.append(("call_liar", None))
			elif action_type == "speech":
				tuples.append(("speech", "text"))
		return tuples

	def _make_phase_name(self) -> str:
		if self.game.game_over:
			return "terminal"
		if self.game.last_play is None:
			return f"r{self.game.round}_turn{self.game.turn_index}_play"
		return f"r{self.game.round}_turn{self.game.turn_index}_play_or_challenge"

	def _flush_logs(self) -> None:
		os.makedirs(self.log_save_path, exist_ok=True)

		game_log_path = os.path.join(self.log_save_path, "game_log.json")
		write_json(game_log_path, self.game.dump_game_log())

		meta_path = os.path.join(self.log_save_path, "game_meta.json")
		write_json(meta_path, self.game.dump_game_meta(player_meta=self.player_meta))

		for player_id in range(1, self.num_players + 1):
			trace_path = os.path.join(self.log_save_path, f"Player_{player_id}.jsonl")
			# Always create the file to satisfy schema contract, even if no rows were produced.
			with open(trace_path, "a", encoding="utf-8"):
				pass
			for row in self.player_trace_buffer.get(player_id, []):
				append_jsonl(trace_path, row)

