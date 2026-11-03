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

# Add the parent directory to sys.path to enable imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import AgentConfig, WebGenAgent2V1
from utils import create_docker_compose_file, start_docker_containers, stop_docker_containers, convert_windows_path_to_linux
from generation_input import build_generation_instruction


def run_agent_in_container(sample_id: str, instruction: str, model: str, working_dir: str, log_dir: str, 
                          max_history_length: int, max_iterations: int, overwrite: bool, compression_ratio: float, max_validation_num: int, max_summary_retry: int, clear_backend: bool, template_names: str | None=None):
    """Run a single agent session inside a Docker container"""
    
    # Ensure directories exist
    os.makedirs(working_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    
    # Check if Docker is available
    try:
        subprocess.run(["docker", "version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False, sample_id, "Docker is not available or not installed"
    
    # Create Docker Compose file path
    run_name = os.path.basename(os.path.dirname(log_dir))
    container_name = f"{sample_id}_{run_name}"
    compose_path = os.path.join(log_dir, container_name, "docker-compose.yml")
    if not os.path.exists(os.path.dirname(compose_path)):
        os.makedirs(os.path.dirname(compose_path))
    
    linux_log_dir = convert_windows_path_to_linux(log_dir)
    linux_working_dir = convert_windows_path_to_linux(working_dir)

    # Create Docker Compose file
    create_docker_compose_file(working_dir, log_dir, compose_path)
    stop_docker_containers(compose_path)  # Ensure no existing containers are running
    
    # Start Docker containers
    if not start_docker_containers(compose_path):
        return False, sample_id, "Failed to start Docker containers"
    
    # Wait a bit for containers to be fully ready
    time.sleep(15)  # Increased wait time for Postgres to be ready
    
    # Run agent inside the container using docker exec
    print(f"[{sample_id}] Running agent inside Docker container...")
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        linux_project_root = convert_windows_path_to_linux(project_root)
        # Create a temporary Python script file in the log directory (which is writable)
        script_content = f"""import sys
import os
import subprocess
import time

# Add the project root to sys.path
sys.path.insert(0, {repr(linux_project_root)})

# Import the agent modules
from core_decoupled import AgentConfig, WebGenAgent2V1

# Create and run the agent
config = AgentConfig(
    instruction={repr(instruction)},
    model={repr(model)},
    working_dir={repr(linux_working_dir)},
    log_dir={repr(linux_log_dir)},
    max_history_length={max_history_length},
    max_iterations={max_iterations},
    overwrite={overwrite},
    compression_ratio={compression_ratio},
    max_validation_num={max_validation_num},
    max_summary_retry={max_summary_retry},
    clear_backend={clear_backend},
    template_names={repr(template_names)}
)

agent = WebGenAgent2V1(config)
result = agent.run()

# Return the result
sys.exit(0 if result else 1)
"""

        # Write the script to a temporary file inside the log directory
        script_path = os.path.join(log_dir, "run_agent.py")
        with open(script_path, "w") as f:
            f.write(script_content)
            
        # Define the log file path
        agent_log_path = os.path.join(log_dir, "run_agent.log")
            
        agent_cmd = [
            "docker", "compose", "-f", compose_path,
            "exec", "-T", "-w", linux_project_root, "workspace",
            "python", f"{linux_log_dir}/run_agent.py"
        ]
        
        # Execute the command with real-time output streaming and logging
        cmd_str = " ".join(agent_cmd)
        print(f"[{sample_id}] Executing command: {cmd_str}")
        
        # Open log file for writing
        with open(agent_log_path, "w") as log_file:
            process = subprocess.Popen(
                cmd_str,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Stream output in real-time with timeout
            output_lines = []
            start_time = time.time()
            timeout = 86400  # 24h timeout
            
            while True:
                # Check for timeout
                if time.time() - start_time > timeout:
                    process.terminate()
                    try:
                        process.wait(timeout=10)  # Wait up to 10 seconds for graceful termination
                    except subprocess.TimeoutExpired:
                        process.kill()  # Force kill if still running
                    raise subprocess.TimeoutExpired(cmd_str, timeout)
                
                # Check if process has finished
                if process.poll() is not None:
                    break
                
                # Read output with a short timeout
                try:
                    output = process.stdout.readline()
                    if output:
                        # Print to console
                        print(f"[{sample_id}] {output.strip()}")
                        # Write to log file
                        log_file.write(output)
                        log_file.flush()
                        # Store for potential error reporting
                        output_lines.append(output)
                except:
                    # Continue loop if read fails
                    time.sleep(0.1)
            
            # Get the return code
            return_code = process.poll()
        
        if return_code == 0:
            print(f"[{sample_id}] Agent session completed successfully")
            return True, sample_id, "Success"
        else:
            error_output = ''.join(output_lines[-50:]) if output_lines else "No output captured"
            error_msg = f"Agent session failed with exit code {return_code}. Last 50 lines of output: {error_output}"
            print(f"[{sample_id}] {error_msg}")
            return False, sample_id, error_msg
        
    except subprocess.TimeoutExpired:
        error_msg = f"Agent session timed out after 5 minutes. Check {agent_log_path} for partial output."
        print(f"[{sample_id}] {error_msg}")
        return False, sample_id, error_msg
    except Exception as e:
        error_msg = f"Agent session failed: {e}"
        print(f"[{sample_id}] {error_msg}")
        return False, sample_id, error_msg
    finally:
        # Stop Docker containers
        stop_docker_containers(compose_path)


def process_sample(sample, args, working_root, log_root):
    """Process a single sample from the test file"""
    sample_id = sample.get("id", "unknown")
    instruction = build_generation_instruction(sample)
    
    # Create working and log directories for this sample
    working_dir_path = os.path.join(working_root, sample_id)
    log_dir_path = os.path.join(log_root, sample_id)
    
    # Add a small delay to reduce network conflicts when starting many containers in parallel
    import random
    time.sleep(random.uniform(0.5, 2.0))
    
    # Run the agent
    success, sid, message = run_agent_in_container(
        sample_id=sample_id,
        instruction=instruction,
        model=args.model,
        working_dir=working_dir_path,
        log_dir=log_dir_path,
        max_history_length=args.max_history_length,
        max_iterations=args.max_iterations,
        overwrite=args.overwrite,
        compression_ratio=args.compression_ratio,
        max_validation_num=args.max_validation_num,
        max_summary_retry=args.max_summary_retry,
        clear_backend=args.clear_backend,
        template_names=args.template_names
    )
    
    return success, sample_id, message


def create_run_name(args):
    """Create a run name based on the parameters"""
    # Create a concise representation of the parameters
    model_name = args.model.split('/')[-1] if '/' in args.model else args.model
    if model_name == "deepseek-v3-250324":
        model_name = "deepseek-chat"
    run_name = f"model-{model_name}_hist-{args.max_history_length}_iter-{args.max_iterations}_compress-{args.compression_ratio}_val-{args.max_validation_num}_sum-{args.max_summary_retry}"
    
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
    parser.add_argument("--max_validation_num", type=int, default=5, help="Max validation num")
    parser.add_argument("--max_summary_retry", type=int, default=5, help="Max summary retry")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of samples to process")
    parser.add_argument("--tag", default=None, help="Tag to append to the auto-generated run name")
    parser.add_argument("--clear_backend", action="store_true", help="Clear backend histroy when implementing frontend")
    parser.add_argument("--template_names", default=None, help="Template names")
    
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
                samples.append(sample)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON line {i+1}: {e}")
    
    print(f"Loaded {len(samples)} samples from {args.test_file}")
    
    if not samples:
        print("No valid samples found in the test file.")
        return 1

    filtered_samples = []
    for sample in samples:
        finish_file = os.path.join(log_root, sample["id"], "finished.json")
        final_step_file1 = os.path.join(log_root, sample["id"], f"{args.max_iterations - 1}_llm_response.json")
        final_step_file2 = os.path.join(log_root, sample["id"], f"{args.max_iterations - 1}_tool_response.json")
        if not os.path.exists(finish_file) and not os.path.exists(final_step_file1) and not os.path.exists(final_step_file2):
            filtered_samples.append(sample)
    samples = filtered_samples

    print(f"{len(samples)} samples to process after filtering completed ones.")
    for sample in samples:
        print(f"  - {sample['id']}")
    # exit(0) # for debugging, to be removed later
    
    # Process samples in parallel
    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit all tasks
        future_to_sample = {
            executor.submit(process_sample, sample, args, working_root, log_root): sample 
            for sample in samples
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_sample):
            try:
                success, sample_id, message = future.result()
                results.append((success, sample_id, message))
                status = "SUCCESS" if success else "FAILED"
                print(f"[{sample_id}] {status}: {message}")
            except Exception as e:
                sample = future_to_sample[future]
                sample_id = sample.get("id", "unknown")
                error_msg = f"Exception occurred: {e}"
                results.append((False, sample_id, error_msg))
                print(f"[{sample_id}] ERROR: {error_msg}")
    
    # Print summary
    successful = sum(1 for r in results if r[0])
    failed = len(results) - successful
    print(f"\nBatch processing completed. Successful: {successful}, Failed: {failed}")
    
    # Print failed samples
    if failed > 0:
        print("\nFailed samples:")
        for success, sample_id, message in results:
            if not success:
                print(f"  {sample_id}: {message}")
    
    return 0 if successful > 0 else 1


if __name__ == "__main__":
    main()