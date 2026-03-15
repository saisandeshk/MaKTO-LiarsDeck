# Locked Execution Plan (Pre-Training)

Status: Locked on 2026-03-15

## Step A — Phase 3 Hardening (Single-model smoke)

Objective:
- Run one full simulated game and emit one valid game directory.

Scope:
- Single model policy path is sufficient (initially random/fallback policy).
- No multi-model orchestration yet.

Acceptance:
1. One folder `trial_logs/run_001/game_0001/` exists.
2. Files exist:
   - `game_log.json`
   - `game_meta.json`
   - `Player_1.jsonl ... Player_N.jsonl`
3. `game_log.json` has increasing `event_id` values.
4. `game_meta.json` fields: `seed`, `ruleset`, `env_version`, `players`.
5. Every trace line has required keys from `synthetic_data/schema.md`.

## Step B — Phase 4 Initial Runner

Objective:
- Implement `run_battle.py` for single-game execution with YAML config.

Acceptance:
1. CLI runs one game from config.
2. Writes one valid game directory using same schema as Step A.
3. Supports explicit seed.

## Step C — Phase 4 Batch Runner

Objective:
- Implement `run_batch.sh` for many seeds / repeated games.

Acceptance:
1. Can generate N game directories in deterministic layout.
2. Logs remain schema-compatible.

## Deferred (after A/B/C green)

- Multi-model support (local + API mix)
- Random competition scheduler
- Full log validator (Phase 5)
- Synthetic extraction handoff (Phase 6)

## Model Decision

Primary local model target for early simulation:
- `Qwen/Qwen3.5-9B`

Note:
- Early Step A can use fallback/random policy to verify environment and logging mechanics first.
- Then switch runner to Qwen once Step B is in place.
