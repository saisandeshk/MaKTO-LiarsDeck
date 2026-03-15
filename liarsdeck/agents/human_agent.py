import json

from liarsdeck.agents.base_agent import Agent


class HumanAgent(Agent):
	def act(self, observation):
		phase = observation.get("phase")
		valid_actions = observation.get("valid_action", [])
		print("\n[HumanAgent]")
		print("phase:", phase)
		print("valid_actions:", valid_actions)
		print("private hand:", observation.get("private_state", {}).get("self_hand", []))
		print("Enter JSON action, e.g. {'type':'play','cards':['K']} or {'type':'call_liar'}")
		raw = input("action> ").strip()
		try:
			return json.loads(raw.replace("'", '"'))
		except Exception:
			return {"type": "call_liar"}
