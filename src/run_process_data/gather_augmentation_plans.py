#!/usr/bin/env python3
"""
Render a Qwen chat-template from the trace files produced by WebGen-Agent.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import re
from tqdm import tqdm
# from transformers import AutoTokenizer
import random
import shutil
import time
import copy
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import generate_repo_id

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


def load_json(in_file):
    with open(in_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def validate_result(result):
    if "info_summary" not in result or not isinstance(result["info_summary"], dict):
        return False
    if "augmentation_options" not in result or not isinstance(result["augmentation_options"], dict) or "augmentationPlans" not in result["augmentation_options"] or not isinstance(result["augmentation_options"]["augmentationPlans"], list):
        return False
    return True


def gather_augmentation_plans(
    log_root_dir: str,
    input_path: str,
    output_path: str,
    unfinished_path: str,
) -> None:
    datas = load_jsonl(input_path)
    new_datas = []
    unfinished_datas = []
    for data in tqdm(datas):
        sample_id = generate_repo_id(data["url"])
        log_dir = os.path.join(log_root_dir, sample_id)
        result_file = os.path.join(log_dir, "finished.json")
        if not os.path.isfile(result_file):
            unfinished_datas.append(data)
            continue
        info_data = load_json(result_file)
        if info_data["result"] is None or not validate_result(info_data["result"]):
            print("Result is None or does not pass validation, skipping ...")
            unfinished_datas.append(data)
            continue
        original_info_summary = info_data["result"]["info_summary"]
        success = False
        for idx, plan in enumerate(info_data["result"]["augmentation_options"]["augmentationPlans"]):
            new_data = {
                "sample_id": f"{sample_id}_{idx}",
                "plan": plan,
                "original_info_summary": original_info_summary,
                "repo": data,
            }
            new_datas.append(new_data)
            success = True
        if not success:
            unfinished_datas.append(data)
    print("new_datas:", len(new_datas))
    print("unfinished_datas:", len(unfinished_datas))
    save_jsonl(unfinished_datas, unfinished_path)
    save_jsonl(new_datas, output_path)


def combine(in_files, out_file):
    datas = []
    for in_file in tqdm(in_files):
        datas.extend(load_jsonl(in_file))
    save_jsonl(datas, out_file)

def main():
    log_root_dir = "/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-200_compress-0.5_nextjs_augmentation_plan"
    input_path = "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos.jsonl"
    output_path = "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan.jsonl"
    unfinished_path = "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-remain-rnd2.jsonl"
    gather_augmentation_plans(log_root_dir, input_path, output_path, unfinished_path)

def main1():
    rnd_idx = 4
    log_root_dir = f"/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-200_compress-0.5_nextjs_augmentation_plan_rnd{rnd_idx}"
    input_path = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-remain-rnd{rnd_idx}.jsonl"
    output_path = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan_rnd{rnd_idx}.jsonl"
    unfinished_path = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_aug-remain-rnd{rnd_idx + 1}.jsonl"
    gather_augmentation_plans(log_root_dir, input_path, output_path, unfinished_path)

def main2():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan_rnd4.jsonl",
    ]
    out_file = "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan-gathered_rnd1.jsonl"
    combine(in_files, out_file)

def main3():
    rnd_idx = 4
    log_root_dir = f"/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-200_compress-0.5_nestjs_augmentation_plan_rnd{rnd_idx}"
    input_path = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_aug-remain-rnd{rnd_idx}.jsonl"
    output_path = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-plan_rnd{rnd_idx}.jsonl"
    unfinished_path = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_aug-remain-rnd{rnd_idx + 1}.jsonl"
    gather_augmentation_plans(log_root_dir, input_path, output_path, unfinished_path)


def main4():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-plan_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-plan_rnd2.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-plan_rnd3.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-plan_rnd4.jsonl",
    ]
    out_file = "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-plan-gathered_rnd1.jsonl"
    combine(in_files, out_file)
    
if __name__ == "__main__":
    main4()