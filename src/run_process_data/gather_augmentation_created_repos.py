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


def gather_augmentation_created_repos(in_file, out_file, unfinished_file, log_dir_root, working_dir_root):
    datas = load_jsonl(in_file)
    new_datas = []
    unfinished_datas = []

    for data in tqdm(datas):
        working_dir = os.path.join(working_dir_root, data["sample_id"])
        log_dir = os.path.join(log_dir_root, data["sample_id"])
        result_file = os.path.join(log_dir, "finished.json")
        is_finished = False
        if os.path.isfile(result_file):
            result = load_json(result_file)
            is_finished = result.get("is_finished", False)
        
        if is_finished:
            data["path"] = working_dir
            new_datas.append(data)
        else:
            unfinished_datas.append(data)

    print(f"new_datas: {len(new_datas)}")
    print(f"unfinished_datas: {len(unfinished_datas)}")
    save_jsonl(new_datas, out_file)
    save_jsonl(unfinished_datas, unfinished_file)


def combine(in_files, out_file):
    datas = []
    for in_file in in_files:
        datas.extend(load_jsonl(in_file))
    save_jsonl(datas, out_file)


def main():
    rnd_idx = 2
    in_file = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan-gathered_rnd{rnd_idx}.jsonl"
    out_file = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-created_rnd{rnd_idx}.jsonl"
    unfinished_file = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-plan-gathered_rnd{rnd_idx + 1}.jsonl"
    log_dir_root = f"/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-400_compress-0.5_nextjs_augmentation_created_rnd{rnd_idx}"
    working_dir_root = f"/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-400_compress-0.5_nextjs_augmentation_created_rnd{rnd_idx}"
    gather_augmentation_created_repos(in_file, out_file, unfinished_file, log_dir_root, working_dir_root)


def main_gather():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-created_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-created_rnd2.jsonl"
    ]
    out_file = "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nextjs_github-repos_augmentation-created_gathered_rnd1.jsonl"
    combine(in_files, out_file)


def main1():
    rnd_idx = 2
    in_file = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-plan-gathered_rnd{rnd_idx}.jsonl"
    out_file = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-created_rnd{rnd_idx}.jsonl"
    unfinished_file = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-plan-gathered_rnd{rnd_idx + 1}.jsonl"
    log_dir_root = f"/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-400_compress-0.5_nestjs_augmentation_created_rnd{rnd_idx}"
    working_dir_root = f"/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-400_compress-0.5_nestjs_augmentation_created_rnd{rnd_idx}"
    gather_augmentation_created_repos(in_file, out_file, unfinished_file, log_dir_root, working_dir_root)


def main_gather1():
    in_files = [
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-created_rnd1.jsonl",
        "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-created_rnd2.jsonl"
    ]
    out_file = "/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_augmentation-created_gathered_rnd1.jsonl"
    combine(in_files, out_file)

if __name__ == "__main__":
    main_gather1()