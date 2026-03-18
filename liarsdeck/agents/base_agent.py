import random
from typing import Any, Dict


class Agent:
	def reset(self):
		return None

	def act(self, observation: Dict[str, Any]):
		raise NotImplementedError

	def generate_speech(self, observation: Dict[str, Any], planned_action: Dict[str, Any], reasoning_trace: str = "", max_chars: int = 180):
		return "I am making my move."


class RandomAgent(Agent):
	def __init__(self, seed=None):
		self.rng = random.Random(seed)

	def act(self, observation: Dict[str, Any]):
		valid_action = observation.get("valid_action", [])
		if not valid_action:
			return {"type": "speech", "text": ""}

		action_type, payload = valid_action[self.rng.randint(0, len(valid_action) - 1)]
		if action_type == "play":
			hand = observation.get("private_state", {}).get("self_hand", [])
			if not hand:
				return {"type": "call_liar"}
			cards_count = min(len(hand), self.rng.randint(1, 3))
			cards = self.rng.sample(hand, cards_count)
			return {"type": "play", "cards": cards}
		if action_type == "call_liar":
			return {"type": "call_liar"}
		return {"type": "speech", "text": ""}

	def generate_speech(self, observation: Dict[str, Any], planned_action: Dict[str, Any], reasoning_trace: str = "", max_chars: int = 180):
		action_type = planned_action.get("type", "play") if isinstance(planned_action, dict) else "play"
		if action_type == "call_liar":
			text = "I challenge the previous claim."
		else:
			text = "I place my cards and keep pressure."
		return text[:max_chars]
