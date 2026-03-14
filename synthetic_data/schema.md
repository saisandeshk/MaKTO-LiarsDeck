# Liar's Deck Logging Contract v0.1

This document defines the three files required to run simulation and build SFT/KTO data later.

## 1) game_log.json (global event timeline)

One file per game. Contains an array of event objects in strict chronological order.

### Required top-level shape

```json
{
	"game_id": "ld_20260314_000001",
	"env_version": "v0.1",
	"events": [
		{
			"event_id": 1,
			"round": 1,
			"turn_index": 0,
			"phase": "setup",
			"event": "game_setting",
			"source": -1,
			"target": -1,
			"visibility": "public",
			"time": "2026-03-14T10:00:00Z",
			"content": {
				"num_players": 4,
				"ruleset": "basic",
				"deck_spec": {
					"K": 6,
					"Q": 6,
					"A": 6,
					"Joker": 2
				}
			},
			"outcome": {}
		}
	]
}
```

### Required event names

- game_setting
- god_view
- round_start
- speech
- play_claim
- challenge_call
- challenge_resolve
- penalty_resolve
- turn_end
- round_end
- end_game

### Required event semantics

- game_setting: static rules and deck info.
- god_view: omniscient hidden truth for replay/labeling only.
- round_start: table rank, starter, alive players.
- speech: public chat utterance.
- play_claim: public claim + hidden actual cards.
- challenge_call: who challenged whom.
- challenge_resolve: truth/lie verdict.
- penalty_resolve: roulette/penalty result.
- turn_end: compact post-turn state snapshot.
- round_end: reason round ended.
- end_game: winner and terminal reason.

### Required field constraints

- event_id must be unique and strictly increasing.
- source and target use integer player ids in [1..N], or -1 for system.
- visibility must be one of: public, private, omniscient.
- play_claim.content must include:
	- claimed_rank
	- claimed_count
	- actual_cards (only meaningful for omniscient view)
- challenge_resolve.content must include:
	- challenger
	- challenged_player
	- verdict (truth|lie)
- penalty_resolve.content must include:
	- loser
	- chamber_result (click|bang)
	- eliminated (true|false)

## 2) Player_<id>.jsonl (per-player trace)

One file per player per game. Each line is one model decision step.

### Required line schema

```json
{
	"game_id": "ld_20260314_000001",
	"event_id": 17,
	"player_id": 2,
	"phase": "r2_turn5_challenge",
	"message": "r2_turn5_challenge",
	"prompt": "...full model prompt...",
	"observation_summary": {
		"table_rank": "Q",
		"pile_size": 4,
		"alive_players": [1, 2, 3, 4],
		"self_card_count": 2
	},
	"valid_actions": [
		{"type": "challenge", "target": 1},
		{"type": "pass"}
	],
	"response": "I challenge Player 1.",
	"selected_action": {"type": "challenge", "target": 1},
	"action_parse_status": "ok",
	"gen_times": 1,
	"latency_ms": 742
}
```

### Required constraints

- event_id must map to a real event in game_log.json.
- phase naming should be deterministic and stable.
- prompt and response must be non-empty for trainable rows.
- selected_action must be one of valid_actions.

## 3) game_meta.json (run metadata)

One file per game folder. Used for reproducibility and experiment filtering.

### Required shape

```json
{
	"game_id": "ld_20260314_000001",
	"env_version": "v0.1",
	"ruleset": "basic",
	"seed": 12345,
	"num_players": 4,
	"start_time": "2026-03-14T10:00:00Z",
	"end_time": "2026-03-14T10:03:22Z",
	"winner": 3,
	"termination_reason": "last_player_alive",
	"players": [
		{
			"player_id": 1,
			"model_name": "sft_agent",
			"provider": "local_vllm",
			"temperature": 0.7
		},
		{
			"player_id": 2,
			"model_name": "gpt4o-mini",
			"provider": "api",
			"temperature": 0.7
		}
	],
	"files": {
		"game_log": "game_log.json",
		"player_traces": [
			"Player_1.jsonl",
			"Player_2.jsonl",
			"Player_3.jsonl",
			"Player_4.jsonl"
		]
	}
}
```

## Recommended game folder layout

```
trial_logs/
	run_001/
		game_0001/
			game_meta.json
			game_log.json
			Player_1.jsonl
			Player_2.jsonl
			Player_3.jsonl
			Player_4.jsonl
```

## Minimal readiness checklist

- All 3 files exist for each simulated game.
- game_log has all required event types.
- Every Player_<id>.jsonl row points to valid event_id.
- seed in game_meta can reproduce the same timeline.
