import json
from tqdm import tqdm

from system_prompt import get_compression_prompt


def load_jsonl(in_file):
    datas = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in tqdm(f):
            datas.append(json.loads(line))
    return datas


def save_jsonl(datas, out_file):
    with open(out_file, "w", encoding="utf-8") as f:
        for data in tqdm(datas):
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


def get_function_appearance_scores(content: str) -> tuple[int, int]:
    # extract function and appearance scores from the content
    def first_digit_after(label: str) -> Optional[int]:
        """Return first digit (as int) that appears after `label` in `content`."""
        # Find the starting index of the label
        start = content.find(label)
        if start == -1:
            return None

        # Slice the string *after* the label
        tail = content[start + len(label):]

        # Look for the first digit in the tail
        m = re.search(r"\d", tail)
        return int(m.group()) if m else 0

    function_score   = first_digit_after("GUI Agent Testing Score")
    appearance_score = first_digit_after("Appearance Grade")

    return function_score, appearance_score


def get_backend_score(content: str):
    pass # to do/+

VALIDATION_PREFIX = "Validate whether all the required features have been implemented. You must make sure that all features have been fully implemented and tested."
IMPLEMENT_PREFIX = "--- User Instruction ---"
FRONTEND_SUB = "--- Frontend Information ---"
BACKEND_SUB = "--- Backend Information ---"
def get_scores(data):
    start_validation = False
    is_frontend = False
    backend_scores = [] # 0-1
    function_scores = [] # 0-5
    appearance_scores = [] # 0-5
    for idx, message in enumerate(data["messages"]):
        # adjust states
        if message["role"] == "assistant" and message["content"].startswith(VALIDATION_PREFIX):
            start_validation = True
        if message["role"] == "user" and message["content"].startswith(IMPLEMENT_PREFIX):
            start_validation = False
            if FRONTEND_SUB in message["content"]:
                is_frontend = True
            else:
                is_frontend = False

        # extract scores
        if start_validation and message["role"] == "tool":
            content = message["content"]
            tool_name = data["messages"][idx - 1]["tool_calls"][0]["function"]["name"]
            if is_frontend and tool_name == "frontend_test":
                function_score, appearance_score = get_function_appearance_scores(content)
                function_scores.append(function_score)
                appearance_scores.append(appearance_score)
            elif (not is_frontend) and tool_name == "backend_test":
                backend_score = get_backend_score(content)
                backend_scores.append(backend_score)


def filter_datas_with_scores(datas, backend_acc_thresh, function_thresh, appearance_thresh):
    filtered_datas = []
    curr_datas = []
    for data in datas:
        if data["kind"] == "uncompressed_messages":
            function_score, appearance_score = get_scores(data)
    return filtered_datas


def convert_to_llama_factory_openai_format(in_file, out_file):
    datas = load_jsonl(in_file)
    new_datas = []

    for data in tqdm(datas):
        if data["kind"] == "uncompressed_messages":
            continue
        messages = data["messages"]
        compressed_text = None
        prompt = []
        response = []
        for idx, message in enumerate(messages):
            if idx < 3 or message.get("is_old", False):
                prompt.append(message)
            else:
                response.append(message)
            if message["role"] == "system" and message["content"].startswith("<COMPRESSED_HISTORY>"):
                compressed_text = message["content"]

        new_data = {
            "prompt": prompt,
            "response": response,
            "tools": data["tools"],
        }
        new_datas.append(new_data)

        if compressed_text is not None and len(data["compressed_section"]) > 0:
            compression_prompt = get_compression_prompt()
            prompt = [
                {"role": "system", "content": compression_prompt},
                {"role": "user", "content": json.dumps(data["compressed_section"])},
            ]
            response = [
                {"role": "assistant", "content": compressed_text}
            ]
            new_datas.append({
                "prompt": prompt,
                "response": response,
                "tools": [],
            })

    save_jsonl(new_datas, out_file)
    save_jsonl(new_datas[:50], out_file.replace(".jsonl", "_50.jsonl"))


def count_websites(in_file):
    datas = load_jsonl(in_file)
    websites = 0

    for data in tqdm(datas):
        if data["kind"] == "uncompressed_messages":
            websites += 1
    print(f"Total number of websites: {websites}")


def convert_to_llama_factory_openai_format_multi_file(in_files, out_file):
    datas = []
    for in_file in in_files:
        datas.extend(load_jsonl(in_file))
    new_datas = []

    for data in tqdm(datas):
        if "kind" not in data:
            data["step"] = -1
            data["kind"] = "planning_messages"
            data["tools"] = []
        if data["kind"] == "uncompressed_messages":
            continue
        messages = data["messages"]
        compressed_text = None
        prompt = []
        response = []
        for idx, message in enumerate(messages):
            if idx < 2 or message.get("is_old", False):
                prompt.append(message)
            else:
                response.append(message)
            if message["role"] == "system" and message["content"].startswith("<COMPRESSED_HISTORY>"):
                compressed_text = message["content"]

        new_data = {
            "prompt": prompt,
            "response": response,
            "tools": data["tools"],
        }
        new_datas.append(new_data)

        if compressed_text is not None and len(data["compressed_section"]) > 0:
            compression_prompt = get_compression_prompt()
            prompt = [
                {"role": "system", "content": compression_prompt},
                {"role": "user", "content": json.dumps(data["compressed_section"])},
            ]
            response = [
                {"role": "assistant", "content": compressed_text}
            ]
            new_datas.append({
                "prompt": prompt,
                "response": response,
                "tools": [],
            })

    save_jsonl(new_datas, out_file)
    save_jsonl(new_datas[:2032], out_file.replace(".jsonl", "_2032.jsonl"))


def main1():
    in_file = "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_filtered-with-info_backtranslated1.jsonl"
    out_file = "/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/data/nextjs_github-repos_filtered-with-info_backtranslated_openai.jsonl"
    # convert_to_llama_factory_openai_format(in_file, out_file)
    count_websites(in_file)


def main2():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_filtered-with-info_backtranslated.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_filtered-with-info_backtranslated.jsonl"
    ]
    out_file = "/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/data/nextjs-nestjs_github-repos_filtered-with-info_backtranslated_openai.jsonl"
    convert_to_llama_factory_openai_format_multi_file(in_files, out_file)


def main3_30b_nestjs():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd7.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd8.jsonl",
    ]
    out_file = "/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/data/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_llama-factory-openai.jsonl"
    convert_to_llama_factory_openai_format_multi_file(in_files, out_file)


def main3_30b_nestjs_decontaminated():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_rnd7.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_rnd8.jsonl",
    ]
    out_file = "/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/data/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_llama-factory-openai.jsonl"
    convert_to_llama_factory_openai_format_multi_file(in_files, out_file)


def main3_30b_nestjs_nextjs_tighter_filter_v0():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd7.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd8.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd7.jsonl",
    ]
    out_file = "/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/data/nextjs_nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_tighter-filter_llama-factory-openai.jsonl"
    convert_to_llama_factory_openai_format_multi_file(in_files, out_file)


def main3_30b_nestjs_nextjs_tighter_filter():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd7.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd8.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd9.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd10.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd11.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd12.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd13.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd14.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd15.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd16.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd17.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd7.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd8.jsonl",
    ]
    out_file = "/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/data/nextjs_nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_tighter-filter_llama-factory-openai.jsonl"
    convert_to_llama_factory_openai_format_multi_file(in_files, out_file)


def main_augmented():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd7.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd8.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd7.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd3.jsonl",
    ]
    out_file = "/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/data/nextjs_nestjs_github-repos_orig_augmented_llama-factory-openai.jsonl"
    convert_to_llama_factory_openai_format_multi_file(in_files, out_file)


def main_augmented1():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd7.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_decontaminated_semantic_tighter-filter_rnd8.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd4.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd5.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd6.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd7.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd4.jsonl",
    ]
    out_file = "/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/data/nextjs_nestjs_github-repos_orig_augmented_llama-factory-openai_new.jsonl"
    convert_to_llama_factory_openai_format_multi_file(in_files, out_file)


def main_direct():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/webgen-instruct_direct-gen_Qwen3-Coder-30B-A3B-Instruct.jsonl"
    ]
    out_file = "/mnt/cache/luzimu/code_agent/LLaMA-Factory-WebGen-Agent2/data/webgen-instruct_direct-gen_Qwen3-Coder-30B-A3B-Instruct_llama-factory-openai.jsonl"
    convert_to_llama_factory_openai_format_multi_file(in_files, out_file)


if __name__ == "__main__":
    main_direct()
