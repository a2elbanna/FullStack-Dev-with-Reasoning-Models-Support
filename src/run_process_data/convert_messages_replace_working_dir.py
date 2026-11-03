import os
import random

ignored_dirs = [
    "model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-450_compress-0.5_val-1_sum-5_nestjs_backtrans4",
    "model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-500_compress-0.5_val-1_sum-5_nestjs_backtrans4",
    "model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-500_compress-0.5_val-1_sum-5_nestjs_backtrans4_adjusted",
    "model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-500_compress-0.5_val-1_sum-5_nextjs_backtrans",
    "model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-500_compress-0.5_val-1_sum-5_nextjs_backtrans1",
    "model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-500_compress-0.5_val-1_sum-5_nextjs_backtrans2",
    "model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-500_compress-0.5_val-1_sum-5_nextjs_backtrans3",
    "model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-500_compress-0.5_val-1_sum-5_nextjs_backtrans4",
    "model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-500_compress-0.5_val-1_sum-5_nextjs_backtrans4_adjusted",
    "WebGenAgentV3_WebGen-Instruct_1_deepseek-v3-250324_iter20_debug_dev",
    "WebGenAgentV3_WebGen-Instruct_1_deepseek-v3-250324_iter20_select_best",
    "WebGenAgentV3_WebGen-Instruct_1_new_deepseek-v3-250324_iter20_select_best",
    "WebGenAgentV3_WebGen-Instruct_1_new_deepseek-v3-250324_iter20_select_best_auto-limit-watch",
]

def get_second_level_dirs(root):
    first_level_dirs = [os.path.join(root, d) for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)) and d not in ignored_dirs]
    second_level_dirs = []
    for first_level_dir in first_level_dirs:
        second_level_dirs.extend([os.path.join(first_level_dir, d) for d in os.listdir(first_level_dir) if os.path.isdir(os.path.join(first_level_dir, d))])
    return second_level_dirs

def get_new_working_dir_list():
    root1 = "/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root"
    root2 = "/mnt/cache/agent/Zimu/WebGen-Agent/workspaces_root"

    working_dirs1 = get_second_level_dirs(root1)

    working_dirs2 = get_second_level_dirs(root2)
    for i in range(len(working_dirs2)):
        working_dirs2[i] = working_dirs2[i].replace("WebGen-Agent", "WebGen-Agent2").replace("WebGenAgentV3_WebGen-Bench_", "model-").replace("WebGenAgentV3_WebGen-Instruct_1_", "model-").replace("WebGen-Bench_", "model-").replace("WebGenAgentV1_WebGen-Bench_", "model-")

    working_dir_list = working_dirs1 + working_dirs2
    random.shuffle(working_dir_list)
    for i in range(len(working_dir_list)):
        if i % 4 == 2:
            working_dir_list[i] = working_dir_list[i].lower()
    random.shuffle(working_dir_list)
    return working_dir_list

NEW_WORKING_DIRS = get_new_working_dir_list()

def convert_messages_replace_working_dir(messages, orig_working_dir, idx):
    new_working_dir = NEW_WORKING_DIRS[idx % len(NEW_WORKING_DIRS)]
    for message in messages:
        if message["role"] in ["user", "system", "tool"]:
            if "content" in message.keys():
                message["content"] = message["content"].replace(orig_working_dir, new_working_dir)

        elif message["role"] == "assistant":
            for tool_call in message.get("tool_calls", []):
                for k, v in tool_call["function"]["arguments"].items():
                    if isinstance(v, str):
                        tool_call["function"]["arguments"][k] = tool_call["function"]["arguments"][k].replace(orig_working_dir, new_working_dir)

            if "content" in message.keys():
                message["content"] = message["content"].replace(orig_working_dir, new_working_dir)
    return new_working_dir