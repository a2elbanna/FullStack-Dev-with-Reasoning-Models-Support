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

# tmux new-session -s augcreate_
# bash /mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/run_website_augmentation_creating.sh 

RND_IDX=2
TEST_FILE="/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan-gathered_rnd${RND_IDX}.jsonl"
# MODEL="deepseek-chat"
# MODEL="/mnt/cache/sharemath/models/Qwen/Qwen3-Coder-30B-A3B-Instruct"
# MODEL="/mnt/cache/code/models/Qwen3-Coder-480B-A35B-Instruct-FP8"
MODEL="Qwen3-Coder-30B-A3B-Instruct"
WORKING_ROOT="/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root"
LOG_ROOT="/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root"
MAX_HISTORY_LENGTH=100
MAX_ITERATIONS=400
# OVERWRITE="--overwrite"
OVERWRITE=""
COMPRESSION_RATIO=0.5
MAX_WORKERS=8
TAG="nextjs_augmentation_created_rnd${RND_IDX}"
FRAMEWORK_TYPE="next.js"

START=$1
INTERVAL=7

python src/run_process_data/run_website_augmentation_creating.py "$TEST_FILE" \
    --model "$MODEL" \
    --working_root "$WORKING_ROOT" \
    --log_root "$LOG_ROOT" \
    --max_history_length "$MAX_HISTORY_LENGTH" \
    --max_iterations "$MAX_ITERATIONS" \
    --compression_ratio "$COMPRESSION_RATIO" \
    --max_workers "$MAX_WORKERS" \
    --tag "$TAG" \
    --framework_type "$FRAMEWORK_TYPE" \
    --start "$START" \
    --interval "$INTERVAL" \
    $OVERWRITE \
    