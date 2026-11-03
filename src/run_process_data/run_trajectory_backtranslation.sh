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

# tmux new-session -s trans_
# bash /mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/run_trajectory_backtranslation.sh 

RND_IDX=4

# TEST_FILE="/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_filtered-with-info_Qwen3-Coder-30B-A3B-Instruct_rnd${RND_IDX}.jsonl"
TEST_FILE="/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_gathered_rnd${RND_IDX}.jsonl"
# MODEL="/mnt/cache/code/models/Qwen3-Coder-480B-A35B-Instruct-FP8"
# MODEL="Qwen3-Coder-30B-A3B-Instruct"
MODEL="/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/outs/mca/qwen3_coder_30b_full_fullstack-agent_nextjs_nestjs_30B_backtranslated_tighter-filter_305_77_2032/qwen3_coder_30b_full_fullstack-agent_nextjs_nestjs_30B_backtranslated_tighter-filter_305_77_2032_checkpoint-254"
WORKING_ROOT="/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root"
LOG_ROOT="/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root"
MAX_HISTORY_LENGTH=100
MAX_ITERATIONS=500
OVERWRITE=""
COMPRESSION_RATIO=0.5
MAX_WORKERS=8
MAX_SUMMARY_RETRY=5
MAX_VALIDATION_NUM=1
BACKEND_RATIO=0.55
TAG="aug-nextjs_backtrans_rnd${RND_IDX}"
FRAMEWORK_TYPE="next.js"
CHOSEN_TEMPLATE_NAME="nextjs-nestjs-postresql"

START=$1
INTERVAL=7

python src/run_process_data/run_trajectory_backtranslation.py "$TEST_FILE" \
    --model "$MODEL" \
    --working_root "$WORKING_ROOT" \
    --log_root "$LOG_ROOT" \
    --max_history_length "$MAX_HISTORY_LENGTH" \
    --max_iterations "$MAX_ITERATIONS" \
    --compression_ratio "$COMPRESSION_RATIO" \
    --max_workers "$MAX_WORKERS" \
    --max_summary_retry "$MAX_SUMMARY_RETRY" \
    --max_validation_num "$MAX_VALIDATION_NUM" \
    --backend_ratio "$BACKEND_RATIO" \
    --tag "$TAG" \
    --chosen_template_name "$CHOSEN_TEMPLATE_NAME" \
    --start "$START" \
    --interval "$INTERVAL" \
    $OVERWRITE \
