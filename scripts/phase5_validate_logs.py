import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


REQUIRED_META_KEYS = {"seed", "ruleset", "env_version", "players", "num_players"}
REQUIRED_TRACE_KEYS = {
	"game_id",
	"event_id",
	"player_id",
	"phase",
	"message",
	"prompt",
	"observation_summary",
	"valid_actions",
	"response",
	"selected_action",
	"action_parse_status",
	"gen_times",
	"latency_ms",
}
REQUIRED_EVENTS = {
	"game_setting",
	"god_view",
	"round_start",
	"play_claim",
	"challenge_call",
	"challenge_resolve",
	"penalty_resolve",
	"turn_end",
	"round_end",
	"end_game",
}
ALLOWED_VISIBILITY = {"public", "private", "omniscient"}


def _load_json(path: Path) -> Any:
	with path.open("r", encoding="utf-8") as file:
		return json.load(file)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
	rows: List[Dict[str, Any]] = []
	with path.open("r", encoding="utf-8") as file:
		for raw_line in file:
			line = raw_line.strip()
			if not line:
				continue
			rows.append(json.loads(line))
	return rows


def _add_error(errors: List[str], game_dir: Path, message: str) -> None:
	errors.append(f"[{game_dir.name}] {message}")


def _add_warning(warnings: List[str], game_dir: Path, message: str) -> None:
	warnings.append(f"[{game_dir.name}] {message}")


def _check_trace_selected_action(
	row: Dict[str, Any],
	game_dir: Path,
	errors: List[str],
) -> None:
	valid_actions = row.get("valid_actions", [])
	selected = row.get("selected_action", {})

	if not isinstance(selected, dict) or "type" not in selected:
		_add_error(errors, game_dir, f"trace row selected_action invalid: {selected}")
		return

	valid_types: Set[str] = set()
	for item in valid_actions:
		if isinstance(item, dict) and isinstance(item.get("type"), str):
			valid_types.add(item["type"])

	if valid_types and selected["type"] not in valid_types:
		_add_error(
			errors,
			game_dir,
			f"trace selected_action.type={selected['type']} not in valid action types={sorted(valid_types)}",
		)


def validate_game(game_dir: Path, strict: bool = False) -> Tuple[List[str], List[str], Dict[str, Any]]:
	errors: List[str] = []
	warnings: List[str] = []
	stats: Dict[str, Any] = {"events": 0, "trace_rows": 0, "winner": None}

	game_log_path = game_dir / "game_log.json"
	meta_path = game_dir / "game_meta.json"
	config_path = game_dir / "config.yaml"

	if not game_log_path.exists():
		_add_error(errors, game_dir, "missing file game_log.json")
	if not meta_path.exists():
		_add_error(errors, game_dir, "missing file game_meta.json")
	if not config_path.exists():
		_add_warning(warnings, game_dir, "missing file config.yaml")

	if errors:
		return errors, warnings, stats

	game_log = _load_json(game_log_path)
	meta = _load_json(meta_path)

	for key in REQUIRED_META_KEYS:
		if key not in meta:
			_add_error(errors, game_dir, f"game_meta missing key: {key}")

	num_players = int(meta.get("num_players", 0))
	if num_players <= 0:
		_add_error(errors, game_dir, "game_meta.num_players must be > 0")
		return errors, warnings, stats

	required_files = [f"Player_{player_id}.jsonl" for player_id in range(1, num_players + 1)]
	missing_trace_files = [name for name in required_files if not (game_dir / name).exists()]
	if missing_trace_files:
		_add_error(errors, game_dir, f"missing player trace files: {missing_trace_files}")

	events = game_log.get("events", [])
	if not isinstance(events, list) or not events:
		_add_error(errors, game_dir, "game_log.events must be a non-empty list")
		return errors, warnings, stats

	stats["events"] = len(events)
	stats["winner"] = meta.get("winner")

	event_ids: List[int] = []
	event_types: List[str] = []
	public_event_types: List[str] = []
	for idx, event in enumerate(events):
		eid = event.get("event_id")
		event_name = event.get("event")
		visibility = event.get("visibility")

		if not isinstance(eid, int):
			_add_error(errors, game_dir, f"event index {idx} has non-integer event_id: {eid}")
			continue
		event_ids.append(eid)

		if not isinstance(event_name, str):
			_add_error(errors, game_dir, f"event_id={eid} missing valid event name")
		else:
			event_types.append(event_name)
			if visibility == "public":
				public_event_types.append(event_name)

		if visibility not in ALLOWED_VISIBILITY:
			_add_error(errors, game_dir, f"event_id={eid} has invalid visibility: {visibility}")

		for field in ("phase", "source", "target", "content", "outcome"):
			if field not in event:
				_add_error(errors, game_dir, f"event_id={eid} missing field: {field}")

		if event_name == "play_claim":
			content = event.get("content", {})
			for field in ("claimed_rank", "claimed_count"):
				if field not in content:
					_add_error(errors, game_dir, f"event_id={eid} play_claim missing {field}")

		if event_name == "challenge_resolve":
			content = event.get("content", {})
			for field in ("challenger", "challenged_player", "verdict"):
				if field not in content:
					_add_error(errors, game_dir, f"event_id={eid} challenge_resolve missing {field}")

		if event_name == "penalty_resolve":
			content = event.get("content", {})
			for field in ("loser", "chamber_result", "eliminated"):
				if field not in content:
					_add_error(errors, game_dir, f"event_id={eid} penalty_resolve missing {field}")

	if event_ids:
		if event_ids != sorted(event_ids) or len(event_ids) != len(set(event_ids)):
			_add_error(errors, game_dir, "event_id must be unique and strictly increasing")
		if event_ids[0] != 1:
			_add_warning(warnings, game_dir, f"first event_id is {event_ids[0]} (expected 1)")

	seen_required = REQUIRED_EVENTS.intersection(set(event_types))
	missing_required = sorted(REQUIRED_EVENTS - seen_required)
	if missing_required:
		_add_error(errors, game_dir, f"missing required event types: {missing_required}")

	if "speech" not in set(event_types):
		_add_warning(warnings, game_dir, "no speech events found (acceptable for non-chat random policy runs)")

	if event_types:
		if event_types[0] != "game_setting":
			_add_error(errors, game_dir, f"first event should be game_setting, got {event_types[0]}")
		if event_types[-1] != "end_game":
			_add_error(errors, game_dir, f"last event should be end_game, got {event_types[-1]}")

	# temporal consistency checks
	round_start_cnt = public_event_types.count("round_start")
	round_end_cnt = public_event_types.count("round_end")
	challenge_call_cnt = public_event_types.count("challenge_call")
	challenge_resolve_cnt = public_event_types.count("challenge_resolve")
	penalty_resolve_cnt = public_event_types.count("penalty_resolve")

	if challenge_call_cnt != challenge_resolve_cnt:
		_add_error(
			errors,
			game_dir,
			f"challenge_call ({challenge_call_cnt}) != challenge_resolve ({challenge_resolve_cnt})",
		)
	if challenge_call_cnt != penalty_resolve_cnt:
		_add_error(
			errors,
			game_dir,
			f"challenge_call ({challenge_call_cnt}) != penalty_resolve ({penalty_resolve_cnt})",
		)

	if round_end_cnt != challenge_call_cnt:
		_add_warning(
			warnings,
			game_dir,
			f"round_end ({round_end_cnt}) differs from challenge_call ({challenge_call_cnt})",
		)

	if round_start_cnt < round_end_cnt:
		_add_error(errors, game_dir, f"round_start ({round_start_cnt}) < round_end ({round_end_cnt})")

	event_id_set = set(event_ids)
	all_trace_rows = 0
	for player_id in range(1, num_players + 1):
		trace_path = game_dir / f"Player_{player_id}.jsonl"
		if not trace_path.exists():
			continue

		rows = _load_jsonl(trace_path)
		all_trace_rows += len(rows)
		if len(rows) == 0:
			_add_warning(warnings, game_dir, f"Player_{player_id}.jsonl has 0 rows")

		last_event_id = -1
		for row in rows:
			missing_keys = REQUIRED_TRACE_KEYS - set(row.keys())
			if missing_keys:
				_add_error(
					errors,
					game_dir,
					f"Player_{player_id}.jsonl row missing keys: {sorted(missing_keys)}",
				)
				continue

			eid = row.get("event_id")
			if not isinstance(eid, int):
				_add_error(errors, game_dir, f"Player_{player_id}.jsonl row has non-int event_id: {eid}")
				continue
			if eid not in event_id_set:
				_add_error(errors, game_dir, f"Player_{player_id}.jsonl event_id {eid} not in game_log")
			if eid < last_event_id:
				_add_error(errors, game_dir, f"Player_{player_id}.jsonl event_id not monotonic: {last_event_id}->{eid}")
			last_event_id = eid

			if strict:
				if not str(row.get("prompt", "")).strip():
					_add_error(errors, game_dir, f"Player_{player_id}.jsonl contains empty prompt in strict mode")
				if not str(row.get("response", "")).strip():
					_add_error(errors, game_dir, f"Player_{player_id}.jsonl contains empty response in strict mode")

			_check_trace_selected_action(row=row, game_dir=game_dir, errors=errors)

	stats["trace_rows"] = all_trace_rows
	if all_trace_rows == 0:
		_add_error(errors, game_dir, "all player trace files are empty")

	return errors, warnings, stats


def _collect_game_dirs(run_dir: Path) -> List[Path]:
	if not run_dir.exists() or not run_dir.is_dir():
		raise ValueError(f"Invalid run directory: {run_dir}")

	game_dirs = [
		path for path in sorted(run_dir.iterdir())
		if path.is_dir() and path.name.startswith("game_")
	]
	if not game_dirs:
		raise ValueError(f"No game_* directories found under: {run_dir}")
	return game_dirs


def main() -> int:
	parser = argparse.ArgumentParser(description="Phase-5 validator for Liar's Deck simulation logs")
	parser.add_argument("--run_dir", type=str, required=True, help="Path to run folder (e.g., trial_logs/run_001)")
	parser.add_argument(
		"--strict",
		action="store_true",
		help="Strict mode for trainability checks (non-empty prompt/response rows)",
	)
	args = parser.parse_args()

	run_dir = Path(args.run_dir)
	game_dirs = _collect_game_dirs(run_dir)

	all_errors: List[str] = []
	all_warnings: List[str] = []
	all_stats: List[Dict[str, Any]] = []

	for game_dir in game_dirs:
		errors, warnings, stats = validate_game(game_dir=game_dir, strict=args.strict)
		all_errors.extend(errors)
		all_warnings.extend(warnings)
		all_stats.append({"game": game_dir.name, **stats})

	print("=== Phase-5 Validation Summary ===")
	print(f"run_dir: {run_dir}")
	print(f"games_checked: {len(game_dirs)}")
	print(f"errors: {len(all_errors)}")
	print(f"warnings: {len(all_warnings)}")
	print(f"strict_mode: {args.strict}")

	for item in all_stats:
		print(
			f"- {item['game']}: events={item.get('events', 0)} trace_rows={item.get('trace_rows', 0)} winner={item.get('winner')}"
		)

	if all_warnings:
		print("\nWarnings:")
		for warning in all_warnings:
			print(f"  - {warning}")

	if all_errors:
		print("\nErrors:")
		for error in all_errors:
			print(f"  - {error}")
		print("\nVALIDATION_RESULT=FAIL")
		return 1

	print("\nVALIDATION_RESULT=PASS")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
