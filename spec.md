# MaKTO-LiarsDeck Spec (Simulation Stage)

Last updated: 2026-03-16

## 1) Purpose and Current Scope

This repo currently covers **simulation + logging + validation** for Liar's Deck, with a MaKTO-like structure adapted from Werewolf.

Primary objective completed so far:
- Generate valid game trajectories (`game_log.json`, `game_meta.json`, `Player_<id>.jsonl`)
- Support single-run + batch-run simulation
- Validate outputs via strict Phase-5 checks
- Support local LLM simulation (vLLM/OpenAI-compatible endpoint)

Out of scope (not fully completed yet):
- Full SFT/KTO dataset extraction pipeline and training loops
- Multi-model tournament scheduler / distributed orchestration beyond basic configs

---

## 2) Codebase Functionality Map (What each key file does)

### Top-level runners

- `run_battle.py`
  - Single-game simulation runner.
  - Loads YAML config, builds agents, runs env loop until terminal.
  - Injects speech per turn (configurable), sanitizes action legality, records traces.
  - Writes `config.yaml` snapshot inside game folder.

- `run_batch.sh`
  - Deterministic batch runner wrapper over `run_battle.py`.
  - Creates `run_xxx/game_0001..game_00NN` layout.
  - Uses seed schedule: `base_seed + (i-1)`.

- `run_random.py`
  - Auxiliary runner path for random-policy testing (legacy/utility).

### Environment and game engine

- `liarsdeck/game.py`
  - Core game state machine.
  - Emits structured events (`game_setting`, `god_view`, `round_start`, `speech`, `play_claim`, `challenge_*`, `penalty_resolve`, `turn_end`, `round_end`, `end_game`).

- `liarsdeck/envs/liarsdeck_text_env_v0.py`
  - Gym-like wrapper around engine.
  - Provides observations, valid actions, step/reset, and flushes logs to files.

### Agents and prompts

- `liarsdeck/agents/llm_agent.py`
  - LLM action generation and parsing fallback.
  - Adds speech-rewrite generation method for table-talk output.

- `liarsdeck/agents/base_agent.py`
  - Base agent interface and random baseline.

- `liarsdeck/agents/prompt_template_v0.py`
  - Prompt templates for action and speech rewrite.

- `liarsdeck/registry.py`
  - Agent factory + model-client construction (OpenAI-compatible endpoints, etc.).

### Helpers

- `liarsdeck/helper/log_utils.py`
  - JSON / JSONL writing and logging helpers.

- `liarsdeck/helper/utils.py`
  - Utility transforms / normalization for env runner.

### Validation and docs

- `scripts/phase5_validate_logs.py`
  - Strict schema + temporal consistency validator for run folders.
  - Main quality gate before accepting generated data.

- `synthetic_data/schema.md`
  - Contract for required log fields and semantics.

- `docs/liars_deck_rules_spec_v0_1.md`
  - Frozen gameplay rules used by simulation.

- `docs/env_simulation_plan_locked.md`
  - Locked execution plan and milestone framing.

### Configs

- `configs/local_qwen_sft.yaml`
  - Main local LLM config (Qwen/vLLM) with speech injection settings.

- `configs/sft_vs_makto.yaml`, `configs/random_models.yaml`, etc.
  - Alternative agent setups and placeholders for comparisons.

---

## 3) Quick Experiment Cheatsheet

## 3.1 Start local vLLM server (long-running)

Use an environment which has atleast one gpu + vllm installed for server:

```bash
conda activate GT 
CUDA_VISIBLE_DEVICES=0 vllm serve Qwen/Qwen3.5-9B \
  --host 127.0.0.1 --port 8000 \
  --dtype bfloat16 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.75 \
  --max-model-len 4096 \
  --max-num-seqs 8 \
```

Health check:

```bash
curl -s http://127.0.0.1:8000/v1/models | python -m json.tool
```

## 3.2 Single game run

Use the same project venv `GT` for runner:

```bash
cd /home/project/MaKTO-LiarsDeck
source /home/project/GT/bin/activate
PYTHONUNBUFFERED=1 python run_battle.py \
  --config configs/local_qwen_sft.yaml \
  --log_save_path trial_logs/run_local_qwen/game_0001 \
  --seed 318 \
  --max_steps 300
```

## 3.3 Batch run

```bash
cd /home/project/MaKTO-LiarsDeck
source /home/project/GT/bin/activate
bash run_batch.sh configs/local_qwen_sft.yaml trial_logs 20 1000 run_local_qwen_batch 300
```

## 3.4 Validation gate (must pass)

```bash
python scripts/phase5_validate_logs.py --run_dir trial_logs/run_local_qwen --strict
python scripts/phase5_validate_logs.py --run_dir trial_logs/run_local_qwen_batch --strict
```

Success criterion: `VALIDATION_RESULT=PASS`

---

## 4) Current Status

## Done ✅

- Rules spec frozen and documented.
- Log schema contract documented.
- Engine emits structured event timeline with visibility (`public`/`omniscient`).
- Single-game runner implemented.
- Batch runner implemented with deterministic seed schedule.
- Local LLM simulation path operational (vLLM + OpenAI-compatible endpoint).
- Strict validator implemented and tested on local-model runs.
- Speech injection integrated into simulation loop.
- Speech cleanup pass added (removes reasoning markers/JSON/code fences, keeps concise table-talk).
- Action sanitization added (invalid model actions no longer crash game).

## In progress / Partially done ⚠️

- Data quality tuning for speech style (policy quality can still vary by model and prompt).
- Cost/performance tuning across model context lengths and speech richness settings.

## Not yet done ❌

- Full Phase-6 extraction handoff (produce finalized SFT/KTO training files from logs).
- KTO preference construction policy (good/bad response pairing or reward sign policy) finalized end-to-end.
- Automated experiment orchestration for mixed local+API models at scale (queueing/retries/reporting).

---

## 5) What “Working” Means (Acceptance Criteria)

A run is considered valid only if all are true:

1. Folder exists: `trial_logs/<run_name>/game_XXXX/`
2. Required files exist in each game dir:
   - `game_log.json`
   - `game_meta.json`
   - `Player_1.jsonl ... Player_N.jsonl`
3. Event IDs strictly increase and are unique.
4. Required event types exist (including `end_game`).
5. Temporal consistency checks pass:
   - `challenge_call == challenge_resolve == penalty_resolve` (public events)
6. Every trace row has required keys and references a valid `event_id`.
7. Strict validator reports `VALIDATION_RESULT=PASS`.

---

## 6) Known Operational Notes / Pitfalls

- If vLLM is started with small context length (e.g., 1024), occasional request overflow can return HTTP 400.
  - Current runner has fallbacks and continues simulation.
  - Recommended: run vLLM with larger `--max-model-len` (e.g., 4096).

- Use `scripts/phase5_validate_logs.py` (not `script/...`).

---

## 7) Suggested Handoff Plan for Partner

1. Start vLLM with stable settings (Section 3.1).
2. Run 1 sanity game and strict validate.
3. Run small batch (e.g., 10 games) and strict validate.
4. Scale batch size only when validator stays green.
5. Keep failed runs isolated in separate run folders; never mix partial runs.
6. Before extraction/training, freeze config version used for each run.

---

## 8) Minimal To-Do List (Next Milestones)

- [ ] Implement Phase-6 extraction scripts from `trial_logs` to SFT/KTO-ready tables.
- [ ] Define KTO preference/reward labeling policy and validate on sample runs.
- [ ] Add summary report script (win rates, challenge accuracy, speech quality metrics).
- [ ] Add retry/error-handling wrapper for long multi-model batch jobs.

---

## 9) One-line Team Guidance

Current repo is **handoff-ready for simulation generation and validation**; next critical step is **data extraction and KTO labeling standardization**.
