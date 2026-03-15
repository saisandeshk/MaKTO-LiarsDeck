import json
from typing import Any, Dict, Iterable, List, Optional


def ensure_player_id(value: Any) -> int:
	if isinstance(value, int):
		return value
	if isinstance(value, str) and value.isdigit():
		return int(value)
	raise ValueError(f"Invalid player id: {value}")


def to_jsonable(data: Any) -> Any:
	if isinstance(data, (str, int, float, bool)) or data is None:
		return data
	if isinstance(data, dict):
		return {str(k): to_jsonable(v) for k, v in data.items()}
	if isinstance(data, (list, tuple, set)):
		return [to_jsonable(v) for v in data]
	return str(data)


def dumps_json(data: Any, indent: int = 2) -> str:
	return json.dumps(to_jsonable(data), ensure_ascii=False, indent=indent)


def normalize_action(raw_action: Any) -> Dict[str, Any]:
	"""
	Normalize multiple action formats into dict form.
	Supported forms:
	- {"type": "play", "cards": [...]}
	- ("call_liar", None)
	- ("speech", "...")
	"""
	if isinstance(raw_action, dict):
		if "type" not in raw_action:
			raise ValueError("Action dict must include key `type`")
		return raw_action

	if isinstance(raw_action, tuple) and len(raw_action) == 2:
		action_type, payload = raw_action
		if action_type == "speech":
			return {"type": "speech", "text": payload or ""}
		if action_type == "call_liar":
			return {"type": "call_liar"}
		if action_type == "play":
			if payload is None:
				raise ValueError("play action requires cards payload")
			return {"type": "play", "cards": payload if isinstance(payload, list) else [payload]}
		raise ValueError(f"Unsupported tuple action type: {action_type}")

	raise ValueError(f"Unsupported action format: {type(raw_action)}")


def compact_events(events: Iterable[Dict[str, Any]], max_items: int = 50) -> List[Dict[str, Any]]:
	events_list = list(events)
	if len(events_list) <= max_items:
		return events_list
	return events_list[-max_items:]
