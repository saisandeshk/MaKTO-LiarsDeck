#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 3 ]]; then
	echo "Usage: bash run_batch.sh <config_path> <output_root> <num_games> [base_seed] [run_name] [max_steps]"
	echo "Example: bash run_batch.sh configs/sft_vs_makto.yaml trial_logs 10 100 run_001 4000"
	exit 1
fi

CONFIG_PATH="$1"
OUTPUT_ROOT="$2"
NUM_GAMES="$3"
BASE_SEED="${4:-42}"
RUN_NAME="${5:-run_001}"
MAX_STEPS="${6:-4000}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"

if [[ ! -f "$CONFIG_PATH" ]]; then
	if [[ -f "$ROOT_DIR/$CONFIG_PATH" ]]; then
		CONFIG_PATH="$ROOT_DIR/$CONFIG_PATH"
	else
		echo "Config not found: $CONFIG_PATH"
		exit 1
	fi
fi

mkdir -p "$OUTPUT_ROOT/$RUN_NAME"

echo "Starting batch run"
echo "config: $CONFIG_PATH"
echo "output: $OUTPUT_ROOT/$RUN_NAME"
echo "num_games: $NUM_GAMES"
echo "base_seed: $BASE_SEED"
echo "max_steps: $MAX_STEPS"

for ((i=1; i<=NUM_GAMES; i++)); do
	GAME_ID=$(printf "game_%04d" "$i")
	GAME_DIR="$OUTPUT_ROOT/$RUN_NAME/$GAME_ID"
	SEED=$((BASE_SEED + i - 1))

	echo "[${i}/${NUM_GAMES}] running ${GAME_ID} seed=${SEED}"
	PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}" python "$ROOT_DIR/run_battle.py" \
		--config "$CONFIG_PATH" \
		--log_save_path "$GAME_DIR" \
		--seed "$SEED" \
		--max_steps "$MAX_STEPS"
done

echo "Batch run complete: $OUTPUT_ROOT/$RUN_NAME"
