__conda_setup="$('/root/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/root/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/root/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/root/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup

conda activate /mnt/cache/agent/Zimu/WebGen-Agent2/env/webgen2

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../..

TEST_FILE="data/FullStack-Bench.jsonl"
MODEL="Qwen3-Coder-480B-A35B-Instruct-FP8"

WORKING_ROOT="/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root"
LOG_ROOT="/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root"
MAX_HISTORY_LENGTH=100
MAX_ITERATIONS=400
COMPRESSION_RATIO=0.5
MAX_WORKERS=8
MAX_VALIDATION_NUM=1
MAX_SUMMARY_RETRY=5
TAG="v9_2"
CLEAR_BACKEND=""

python src/run/run_batch_decoupled.py "$TEST_FILE" \
    --model "$MODEL" \
    --working_root "$WORKING_ROOT" \
    --log_root "$LOG_ROOT" \
    --max_history_length "$MAX_HISTORY_LENGTH" \
    --max_iterations "$MAX_ITERATIONS" \
    --compression_ratio "$COMPRESSION_RATIO" \
    --max_workers "$MAX_WORKERS" \
    --max_validation_num "$MAX_VALIDATION_NUM" \
    --max_summary_retry "$MAX_SUMMARY_RETRY" \
    --tag "$TAG" \
    $CLEAR_BACKEND
    