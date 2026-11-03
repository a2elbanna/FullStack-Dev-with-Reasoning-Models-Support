DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $DIR/../..

# Use the project's conda env interpreter explicitly so the orchestrator
# (and its host-side imports like bashlex/libtmux) resolve correctly,
# regardless of which env is currently activated.
PYTHON="$DIR/../../env/webgen2/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "ERROR: expected env interpreter not found at $PYTHON" >&2
    echo "Create it per the README, or edit PYTHON in this script." >&2
    exit 1
fi

TEST_FILE="data/new-site.jsonl"
MODEL="${MODEL:-gpt-6-astra}"
#MODEL="Qwen3-Coder-480B-A35B-Instruct-FP8"

#WORKING_ROOT="/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root"
#LOG_ROOT="/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root"
WORKING_ROOT="/Users/ahmedelbana/Documents/fullstack-agents-project/result/workspaces"
LOG_ROOT="/Users/ahmedelbana/Documents/fullstack-agents-project/result/logs"

MAX_HISTORY_LENGTH=600
MAX_ITERATIONS=400
COMPRESSION_RATIO=0.5
MAX_WORKERS=4
MAX_VALIDATION_NUM=5
MAX_SUMMARY_RETRY=5
TAG="${TAG:-voucher-v2-responses}"
TEMPLATE_NAMES="nextjs-nestjs-postresql"

"$PYTHON" src/run/run_batch.py "$TEST_FILE" \
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
    --template_names "$TEMPLATE_NAMES"    