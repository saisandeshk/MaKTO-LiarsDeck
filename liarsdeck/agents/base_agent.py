import random
from typing import Any, Dict


class Agent:
	def reset(self):
		return None

	def act(self, observation: Dict[str, Any]):
		raise NotImplementedError


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
			cards = hand[:cards_count]
			return {"type": "play", "cards": cards}
		if action_type == "call_liar":
			return {"type": "call_liar"}
		return {"type": "speech", "text": ""}
