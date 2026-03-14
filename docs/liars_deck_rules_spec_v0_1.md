# Liar’s Deck Environment Rules Specification (Phase‑1)

Version: v0.1  
Status: Frozen for Env + Logs implementation (no model-training assumptions)

## 1) Scope and Objective

This document defines the exact game rules to implement for simulation and logging.  
It is intentionally aligned with:
- current prototype behavior in `liar_deck.py`
- logging contract in `synthetic_data/schema.md`

Goal: remove ambiguity before coding the production environment.

## 2) Players, Deck, and Win Condition

- Number of players: default `4` (configurable later; v0.1 assumes 4-player testing).
- Player IDs for logs: integer `1..N`.
- Deck composition per round:
  - `K`: 6
  - `Q`: 6
  - `A`: 6
  - `Joker`: 2
- Each alive player receives exactly `5` cards at round start.
- A player is **eliminated** when roulette chamber result is `bang`.
- Game ends immediately when only one player remains alive.
- Winner = the last alive player.

## 3) Round Lifecycle

Each round is independent for cards but not for survival state.

### 3.1 Round Start

At round start:
1. Create and shuffle a fresh deck.
2. Deal 5 cards to each alive player.
3. Set `table_rank` by random choice from `{K, Q, A}`.
4. Reset pile state:
   - `pile_size = 0`
   - `last_play = null`
5. Set `current_turn` to designated starter (see 3.4).

### 3.2 Turn Actions

On a turn, current player may do exactly one of:
- `play`
- `call_liar`

No other gameplay action is valid in v0.1.

### 3.3 Action Rules

#### A) `play`

- Player selects `1..3` cards from their own current hand.
- Cards must exist in hand.
- Cards are removed from hand and added to hidden pile.
- `last_play` is updated with:
  - `player_id`
  - `cards_played` (true cards, omniscient)
  - `claimed_count`
- In v0.1, claim semantics are fixed to table-rank claim model:
  - public meaning = “I played `claimed_count` cards of current table rank (Joker acceptable as wildcard truth)”
- Turn passes to next alive player.

#### B) `call_liar`

- Only valid if `last_play != null` (cannot be first gameplay action of round).
- Caller challenges `last_play.player_id`.
- Truth test:
  - `truthful` iff every card in `last_play.cards_played` is either `table_rank` or `Joker`.
  - If any card is not `table_rank` and not `Joker`, challenged player is lying.
- Loser assignment:
  - if liar detected: loser = challenged player
  - else: loser = caller

### 3.4 Post-Challenge and Next Round Starter

After loser is determined:
1. Apply roulette (Section 4).
2. If one alive player remains: game ends.
3. Else start a new round.
4. Next round starter rule (frozen to current prototype):
   - If loser survived (`click`): loser starts next round.
   - If loser eliminated (`bang`): caller of `call_liar` starts next round.

## 4) Roulette Behavior

Each player has a persistent 6-chamber queue initialized at game reset:
- 5 `click` (blank)
- 1 `bang` (bullet)
- order shuffled once per player at game reset.

On each loss event:
- pop next chamber from front of player queue.
- `bang` => player eliminated.
- `click` => player survives.

v0.1 edge policy:
- If a player’s chamber queue becomes empty in future losses, environment must fail fast with explicit error (`invalid roulette state`) unless reset policy is explicitly introduced in v0.2.

## 5) Visibility Model (for Logging + Agent Observations)

- Public information:
  - table rank
  - turn owner
  - alive/dead status
  - player hand counts
  - challenge calls and outcomes
  - penalty outcomes
- Private information:
  - player’s own hand
  - player’s own remaining chamber sequence is private to environment logic (publicly only chambers_left count)
- Omniscient information:
  - all true cards played in each `play`
  - full hidden states used for labeling (`god_view` event)

## 6) Event and Phase Mapping (must match schema)

Required event sequence pieces in `game_log.json`:
- `game_setting` (once per game)
- `god_view` (once per game; includes hidden initial assignments/states)
- Per round:
  - `round_start`
  - optional `speech` events (if external chat emitted)
  - repeated `play_claim` and/or `challenge_call`
  - on challenge: `challenge_resolve`, `penalty_resolve`
  - `turn_end` after each turn
  - `round_end` when round transitions
- `end_game` once terminal condition met

Phase naming guideline (deterministic):
- `r{round}_turn{turn}_play`
- `r{round}_turn{turn}_challenge`
- `r{round}_resolve`

## 7) Valid Action Contract (v0.1)

For current turn player:
- if `last_play == null`: valid actions = `{play}`
- else: valid actions = `{play, call_liar}`

`play` payload constraints:
- cards list length in `[1,3]`
- all cards must be present in player hand.

`call_liar` payload constraints:
- no target override in v0.1 (always challenges `last_play.player_id`).

## 8) Tie / Draw / Edge Cases

- No vote tie system in v0.1.
- No simultaneous elimination.
- Calling liar on first action of round is invalid.
- Acting out of turn is invalid.
- Invalid card declaration (card not in hand) is invalid.
- If current-turn player is dead (should not happen), env must auto-advance to next alive and log correction event in v0.2; for v0.1 this state is treated as implementation error.

## 9) Determinism and Reproducibility

For simulation runs, log in `game_meta.json`:
- seed
- env_version
- ruleset
- model assignments

Given same seed + same model outputs + same ruleset, event timeline must be reproducible.

## 10) Non-Goals for Phase‑1

- No balancing changes to game mechanics.
- No additional strategic actions (peek, forced reveal, multi-target challenges).
- No training logic here; only environment and logs.

---

Acceptance:
1. Two independent readers implement the same transitions from this spec.
2. All events required by `synthetic_data/schema.md` can be emitted unambiguously.
3. 100 simulated games can run without rule-interpretation disputes.
