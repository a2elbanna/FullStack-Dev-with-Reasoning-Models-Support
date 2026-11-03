#!/usr/bin/env python3
"""
Script to automatically start multiple Docker containers and run agent sessions in parallel for batch processing.
This script also initializes the Clash proxy before starting the agent sessions.
"""

import os
import sys
import argparse
import json
import subprocess
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import shutil

# Add the parent directory to sys.path to enable imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the agent modules
from process_data import AugmentationPlanningAgentConfig, AugmentationPlanningAgent

from utils import (
    create_docker_compose_file, 
    start_docker_containers, 
    stop_docker_containers, 
    convert_windows_path_to_linux, 
    generate_repo_id,
)


def run_agent(sample_id: str, orig_project_path: str, model: str, working_dir: str, log_dir: str, 
                          max_history_length: int, max_iterations: int, overwrite: bool, compression_ratio: float, 
                          backend_ratio: float, index: int, framework_type: str):
    """Run a single agent session inside a Docker container"""

    if os.path.isfile(os.path.join(log_dir, "info_result.json")):
        return sample_id

    # Create and run the agent
    config = AugmentationPlanningAgentConfig(
        orig_project_path=orig_project_path,
        model=model,
        working_dir=working_dir,
        log_dir=log_dir,
        max_history_length=max_history_length,
        max_iterations=max_iterations,
        overwrite=overwrite,
        compression_ratio=compression_ratio,
        backend_ratio=backend_ratio,
        index=index,
        framework_type=framework_type,
    )

    agent = AugmentationPlanningAgent(config)
    result = agent.run()
    return sample_id


def process_sample(sample, args, working_root, log_root, index):
    """Process a single sample from the test file"""
    sample_id = sample.get("id", "unknown")
    orig_project_path = sample.get("path", "")
    
    # Create working and log directories for this sample
    working_dir_path = os.path.join(working_root, sample_id)
    shutil.copytree(sample["path"], working_dir_path, dirs_exist_ok=True)
    log_dir_path = os.path.join(log_root, sample_id)
    
    # Run the agent
    sample_id = run_agent(
        sample_id=sample_id,
        orig_project_path=orig_project_path,
        model=args.model,
        working_dir=working_dir_path,
        log_dir=log_dir_path,
        max_history_length=args.max_history_length,
        max_iterations=args.max_iterations,
        overwrite=args.overwrite,
        compression_ratio=args.compression_ratio,
        backend_ratio=args.backend_ratio,
        index=index,
        framework_type=args.framework_type,
    )
    
    return sample_id


def create_run_name(args):
    """Create a run name based on the parameters"""
    # Create a concise representation of the parameters
    model_name = args.model.split('/')[-1] if '/' in args.model else args.model
    if model_name == "deepseek-v3-250324":
        model_name = "deepseek-chat"
    run_name = f"model-{model_name}_hist-{args.max_history_length}_iter-{args.max_iterations}_compress-{args.compression_ratio}"
    
    if args.limit:
        run_name += f"_limit-{args.limit}"
    
    # Append tag if provided
    if args.tag:
        run_name += f"_{args.tag}"
    
    # Replace any characters that might be problematic in directory names
    run_name = run_name.replace("/", "-").replace(":", "-")
    return run_name


def main():
    parser = argparse.ArgumentParser(description="Run batch agent sessions in Docker containers")
    parser.add_argument("test_file", help="Path to the test JSONL file")
    parser.add_argument("--model", default="deepseek-chat", help="Model to use for the agent")
    parser.add_argument("--working_root", default="/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root", 
                        help="Root working directory for all samples")
    parser.add_argument("--log_root", default="/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root", 
                        help="Root log directory for all samples")
    parser.add_argument("--max_history_length", type=int, default=20, help="Maximum history length for the agent")
    parser.add_argument("--max_iterations", type=int, default=50, help="Maximum iterations for the agent")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    parser.add_argument("--compression_ratio", type=float, default=0.5, help="Compression ratio for history compression")
    parser.add_argument("--max_workers", type=int, default=2, help="Maximum number of parallel workers (reduced to avoid Docker network conflicts)")
    parser.add_argument("--backend_ratio", type=float, default=0.5, help="Ratio of backend iteration limit")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of samples to process")
    parser.add_argument("--tag", default=None, help="Tag to append to the auto-generated run name")
    parser.add_argument("--start", type=int, default=0, help="Start index of each group.")
    parser.add_argument("--interval", type=int, default=1, help="Interval of each group")
    parser.add_argument("--framework_type", default="next.js", help="Type of framework used.")
    args = parser.parse_args()
    
    # Create run name based on parameters
    run_name = create_run_name(args)
    
    # Construct full paths with run name
    working_root = os.path.join(args.working_root, run_name)
    log_root = os.path.join(args.log_root, run_name)
    
    print(f"Run name: {run_name}")
    print(f"Working root: {working_root}")
    print(f"Log root: {log_root}")
    
    # Ensure root directories exist
    os.makedirs(working_root, exist_ok=True)
    os.makedirs(log_root, exist_ok=True)

    args_dict = vars(args).copy()          # 1) Namespace  -> dict
    args_dict["run_name"] = run_name       # 2) (optional) keep run_name too
    args_file = os.path.join(log_root, "args.json")
    with open(args_file, "w", encoding="utf-8") as f:
        json.dump(
            args_dict,
            f,
            indent=4,              # pretty printing
            sort_keys=True         # deterministic key order
        )
    print(f"Saved CLI args to {args_file}")
    
    # Read the test file
    samples = []
    with open(args.test_file, 'r') as f:
        for i, line in enumerate(f):
            if args.limit and i >= args.limit:
                break
            try:
                sample = json.loads(line.strip())
                sample["id"] = generate_repo_id(sample["url"])  # generate "{username}__{reponame}" as repo id
                samples.append(sample)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON line {i+1}: {e}")
    
    print(f"Loaded {len(samples)} samples from {args.test_file}")
    
    if not samples:
        print("No valid samples found in the test file.")
        return 1

    samples = samples[args.start::args.interval]

    filtered_samples = []
    for sample in samples:
        finish_file = os.path.join(log_root, sample["id"], "finished.json")
        if not os.path.exists(finish_file):
            filtered_samples.append(sample)
    samples = filtered_samples
    
    # Process samples in parallel
    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit all tasks
        future_to_sample = {
            executor.submit(process_sample, sample, args, working_root, log_root, args.start): sample 
            for sample in samples
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_sample):
            try:
                sample_id = future.result()
                results.append((success, sample_id, message))
                print(f"[{sample_id}] {status}: {message}")
            except Exception as e:
                sample = future_to_sample[future]
                sample_id = sample.get("id", "unknown")
                error_msg = f"Exception occurred: {e}"
                results.append((False, sample_id, error_msg))
                print(f"[{sample_id}] ERROR: {error_msg}")


if __name__ == "__main__":
    main()