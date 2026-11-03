import os
import json
from tqdm import tqdm
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import generate_repo_id


def load_json(in_file):
    with open(in_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def load_jsonl(in_file):
    datas = []
    idx = 1
    with open(in_file, "r", encoding="utf-8") as f:
        for line in tqdm(f):
            try:
                datas.append(json.loads(line))
            except:
                print(f"\n\nError Line Number: {idx}\n\n")
            idx += 1
    return datas


def save_jsonl(datas, out_file):
    with open(out_file, "w", encoding="utf-8") as f:
        for data in tqdm(datas):
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


def has_duplicate_api_endpoints(api_endpoints):
    seen = []
    for endpoint in api_endpoints:
        path = endpoint.get("path", "")
        method = endpoint.get("method", "GET").upper()
        identifier = f"{method} {path}"
        if identifier in seen:
            return True
        seen.append(identifier)
    return False


def filter_nestjs_github_repos(orig_jsonl_file, out_jsonl_file, unfinished_jsonl_file, log_root_dir, quality_thresh, page_thresh, api_thresh):
    print(orig_jsonl_file)
    orig_datas = load_jsonl(orig_jsonl_file)
    unfinished_samples = []
    filtered_samples = []
    exist_num = 0
    for orig_data in tqdm(orig_datas):
        sample_id = orig_data["sample_id"]
        log_dir = os.path.join(log_root_dir, sample_id)
        if os.path.isdir(log_dir):
            exist_num += 1
        result_file = os.path.join(log_dir, "finished.json")
        if not os.path.isfile(result_file):
            unfinished_samples.append(orig_data)
            continue
        data = load_json(result_file)
        data["id"] = os.path.basename(log_dir)
        data.pop("content", None)
        summary = data["summary"]
        quality_score = summary["qualityScore"]
        if summary.get("frontendPlan", None) is None:
            unfinished_samples.append(orig_data)
            continue
        page_num = len(summary.get("frontendPlan", {}).get("pages", []))
        api_endpoints = summary.get("backendPlan", {}).get("apiEndpoints", [])
        api_num = len(api_endpoints)
        has_duplicate = has_duplicate_api_endpoints(api_endpoints)
        # print(f"{data['id']}: quality score {quality_score}; page num {page_num}; api num {api_num}; duplicate api: {has_duplicate}")
        if quality_score >= quality_thresh and page_num >= page_thresh and api_num >= api_thresh and not has_duplicate:
            orig_data.update(data)
            filtered_samples.append(orig_data)
        else:
            unfinished_samples.append(orig_data)
    print(f"Filtered samples: {len(filtered_samples)}")
    print(f"Unfinished samples: {len(unfinished_samples)}")
    print(f"Exist samples: {exist_num}")
    save_jsonl(filtered_samples, out_jsonl_file)
    save_jsonl(unfinished_samples, unfinished_jsonl_file)


def combine(in_files, out_file):
    datas = []
    for in_file in in_files:
        datas.extend(load_jsonl(in_file))
    save_jsonl(datas, out_file)


def main():
    rnd_idx = 2
    orig_jsonl_file = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-created_gathered_rnd{rnd_idx}.jsonl"
    out_jsonl_file = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_rnd{rnd_idx}.jsonl"
    log_root_dir = f"/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-200_compress-0.5_sum-5_aug-nextjs_info_rnd{rnd_idx}"
    unfinished_jsonl_file = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-created_gathered_rnd{rnd_idx + 1}.jsonl"
    quality_thresh = 3
    page_thresh = 1
    api_thresh = 2
    filter_nestjs_github_repos(orig_jsonl_file, out_jsonl_file, unfinished_jsonl_file, log_root_dir, quality_thresh, page_thresh, api_thresh)


def main_gather():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_rnd2.jsonl",
    ]
    out_file = "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_gathered_rnd1.jsonl"
    combine(in_files, out_file)


if __name__ == "__main__":
    main_gather()