"""
Core module for Qwen Code Python implementation.
"""
import os
import json
import sys
import glob
from typing import List, Dict, Any
from tqdm import tqdm
from dataclasses import dataclass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import SessionLogger, llm_generation, parse_json_response_with_codeblock
from tools import get_all_tools
from .augmentation_prompt import (
    get_augmentation_creating_prompt,
    get_augmentation_verification_prompt
)
from .system_prompt import get_core_system_prompt
from .tool_registry import ToolRegistry
from .templates import TEMPLATES, safe_copy_template
from .compress_output import compress_output

RETRY_LIMIT = 5

@dataclass
class AugmentationCreatingAgentConfig:
    augmentation_plan: dict    # "name", "goal", "type", "keyChanges", "estimatedEffort", "expectedBenefits": "Cleaner codebase and clearer ownership"
    original_info_summary: dict
    orig_project_path: str
    model: str
    working_dir: str
    log_dir: str
    max_history_length: int = 20
    max_iterations: int = 50
    overwrite: bool = False
    max_tokens: int = 8192
    compression_ratio: float = 0.5
    backend_ratio: float = 0.5
    index: int = None
    framework_type: str = "next.js"
    temperature: float = 0.5


class AugmentationCreatingAgent:
    """The first version of WebGen-Agent2"""
    
    def __init__(self, config: AugmentationCreatingAgentConfig):
        self.config = config
        self.llm_generation = llm_generation
        self.history: List[Dict[str, Any]] = []
        self.tool_call_history: List[Dict[str, Any]] = []  # New attribute to track all tool calls
        self.max_history_length = self.config.max_history_length

        self.orig_project_name = os.path.basename(self.config.orig_project_path)
        self.augmentation_finished = False

        # Create a new session logger for this agent instance
        self.session_logger = SessionLogger(self.config.log_dir)

        self.initialize_tool_registry()

    def initialize_tool_registry(self):
        self.tools = get_all_tools(self.config.working_dir, self.config.log_dir)
        self.registry = ToolRegistry()
        for tool in self.tools:
            self.registry.register_tool(tool)

    def initialize_agent(self) -> int:
        """Initialize the client with system context. If previous logs exist, restart from the last step."""
        # Check if we should restart from a previous run
        log_dir = self.config.log_dir
        start_step = 0
        if not self.config.overwrite and os.path.exists(log_dir):
            # Look for existing tool response files to determine the last completed step
            tool_response_files = glob.glob(os.path.join(log_dir, "*_tool_response.json"))
            if tool_response_files:
                # Extract step numbers and sort them in descending order
                step_numbers = []
                for file_path in tool_response_files:
                    filename = os.path.basename(file_path)
                    try:
                        step_num = int(filename.split("_")[0])
                        step_numbers.append(step_num)
                    except ValueError:
                        continue
                
                if step_numbers:
                    step_numbers.sort(reverse=True)  # Sort in descending order
                    
                    # Try to load history from the most recent logs, going backwards until one succeeds
                    for step_num in step_numbers:
                        self.session_logger.log_message(f"Attempting to restart from step {step_num}")
                        log_file = os.path.join(log_dir, f"{step_num}_tool_response.json")
                        try:
                            with open(log_file, "r", encoding="utf-8") as f:
                                log_data = json.load(f)
                                # Restore history from the logged messages
                                if "request" in log_data and "messages" in log_data["request"]:
                                    # Start with the base messages from the request
                                    self.history = log_data["request"]["messages"] + log_data.get("response", [])
                                    start_step = step_num + 1  # Next step should be one more than the loaded step
                                    self.session_logger.log_message(f"Loaded history with {len(self.history)} messages from step {step_num}")
                                    
                                    # Load tool_call_history if it exists
                                    if "tool_call_history" in log_data:
                                        self.tool_call_history = log_data["tool_call_history"]
                                        # Execute tool calls that would affect the environment state
                                        self._restore_environment_state()
                                    
                                    self.session_logger.log_message(f"Restarting from step {start_step}")
                                    break  # Successfully loaded, exit the loop
                        except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
                            # Log the error and continue to the next log file
                            self.session_logger.log_message(f"Failed to load log file {log_file}: {str(e)}")
                            continue
                    else:
                        # If we get here, all log loading attempts failed
                        self.session_logger.log_message("Failed to load any previous logs, starting from scratch")
        
        # If we're not restarting, initialize with system context
        if not self.history:
            # Initialize backend first
            system_prompt = get_core_system_prompt(self.config.working_dir)

            user_prompt = get_augmentation_creating_prompt(self.config.augmentation_plan, self.config.original_info_summary)

            self.history = [
                {"role": "system", "content": system_prompt},
                {"role": "assistant", "content": "Got it. Thanks for the context!"},
                {"role": "user", "content": user_prompt}
            ]
        
        return start_step
        
    def _restore_environment_state(self):
        """Execute tool calls that would affect the environment state to restore it."""
        # List of tools that affect the environment state
        state_affecting_tools = {"write_file", "replace", "run_shell_command"}
        
        self.session_logger.log_message(f"Restoring environment state with {len(self.tool_call_history)} tool calls")
        
        for i, tool_call in enumerate(self.tool_call_history):
            tool_name = tool_call.get("function", {}).get("name")
            if tool_name in state_affecting_tools:
                try:
                    tool_args = json.loads(tool_call["function"]["arguments"])
                    self.session_logger.log_message(f"Executing state-restoring tool call {i}: {tool_name}")
                    # Execute the tool call to restore the environment state
                    self.registry.execute_tool(tool_name, tool_args)
                except Exception as e:
                    self.session_logger.log_message(f"Failed to execute state-restoring tool call {i}: {str(e)}")
                    # Continue with the next tool call even if one fails
                    continue
        
        self.session_logger.log_message("Environment state restoration completed")
        
    def _compress_history(self, force=False, compression_ratio=None, step_idx=0):
        if compression_ratio is None:
            compression_ratio = self.config.compression_ratio
        """Compress history using the compression prompt when it exceeds maximum length."""
        if len(self.history) > self.max_history_length or force:
            # Group messages to ensure assistant messages with tool calls and their responses stay together
            grouped_history = []
            i = 3  # Start from index 3 to skip the initial context
            while i < len(self.history):
                # If current message is an assistant message with tool calls
                if (self.history[i].get("role") == "assistant" and 
                    "tool_calls" in self.history[i] and 
                    self.history[i]["tool_calls"]):
                    # Group this assistant message with its tool responses
                    group = [self.history[i]]
                    i += 1
                    # Add all subsequent tool responses
                    while i < len(self.history) and self.history[i].get("role") == "tool":
                        group.append(self.history[i])
                        i += 1
                    grouped_history.append(group)
                else:
                    # Single message group
                    grouped_history.append([self.history[i]])
                    i += 1

            if len(grouped_history) <= self.max_history_length and not force:
                return
            # Split into compressed_history and remaining_history
            compression_threshold = int(len(grouped_history) * compression_ratio)
            if compression_threshold > 0:
                compressed_groups = grouped_history[:-compression_threshold]
                remaining_groups = grouped_history[-compression_threshold:]
            else:
                compressed_groups = grouped_history
                remaining_groups = []

            # Flatten the groups
            compressed_history = []
            for group in compressed_groups:
                compressed_history.extend(group)
                
            remaining_history = []
            for group in remaining_groups:
                remaining_history.extend(group)
            
            # If there's nothing to compress, just trim the history
            if not compressed_history:
                # Keep the initial context and the remaining history
                self.history = self.history[:3] + remaining_history
                return

            try:
                # Prepare the compression prompt with the compressible history
                compression_prompt = get_compression_prompt()
                
                # Create a message to send to the LLM for compression
                compression_messages = [
                    {"role": "system", "content": compression_prompt},
                    {"role": "user", "content": json.dumps(compressed_history)}
                ]
                
                # Send request to LLM to compress the history
                compressed_response = llm_generation(
                    compression_messages, 
                    model=self.config.model,
                    index=self.config.index,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature
                )

                request_data = {
                    "model": self.config.model,
                    "messages": compression_messages.copy(),
                }
                self.session_logger.log_llm_request_response(step_idx, "compress_history", request_data, compressed_response)
                
                # Extract the compressed content
                compressed_content = compressed_response.get("content", "")
                
                # Create a compressed history message
                compressed_history_message = {
                    "role": "system",
                    "content": f"<COMPRESSED_HISTORY>{compressed_content}</COMPRESSED_HISTORY>"
                }
                
                # Form the new history: initial context + compressed result + remaining history
                self.history = self.history[:3] + [compressed_history_message] + remaining_history
                
            except Exception as e:
                # If compression fails, fall back to simple trimming
                # Keep initial context and the last N-3 messages
                remaining_groups = grouped_history[- compression_threshold:]
                remaining_history = []
                for group in remaining_groups:
                    remaining_history.extend(group)
                self.history = self.history[:3] + remaining_history
            
    def step(self, step_idx: int) -> Dict[str, Any]:
        """Send a message to the LLM, process the response, update history, and log response."""
        self._compress_history(step_idx=step_idx)

        # Prepare request for logging
        request_data = {
            "model": self.config.model,
            "messages": self.history.copy(),
        }
        tool_schemas = self.registry.get_tool_schemas()
        request_data["tool_schemas"] = tool_schemas
            
        try:
            # Send request to LLM
            response = self.llm_generation(self.history, model=self.config.model, index=self.config.index, tools=tool_schemas, max_tokens=self.config.max_tokens, temperature=self.config.temperature)
            self.session_logger.log_llm_request_response(step_idx, "llm_response", request_data, response)
            self.history.append(response)

            # Execute the tool calls
            request_data = {
                "model": self.config.model,
                "messages": self.history.copy(),
            }
            tool_responses = []
            tool_calls = response.get("tool_calls", None)

            if tool_calls is None or len(tool_calls) == 0:
                content_text = response.get("content", "")
                if self.augmentation_finished:
                    return {"type": "finished", "content": content_text}
                else:
                    return {"type": "to_be_continued"}

            for tool_call in tool_calls:
                self.tool_call_history.append(tool_call)
                self.session_logger.log_message(f'executing {tool_call["id"]}: {tool_call["function"]["name"]}...')
                try:
                    tool_args = json.loads(tool_call["function"]["arguments"])
                    tool_result = self.registry.execute_tool(tool_call["function"]["name"], tool_args)
                except json.JSONDecodeError as e:
                    # Handle incomplete or invalid JSON in tool arguments
                    error_msg = f"Invalid JSON in tool arguments: {str(e)}"
                    self.session_logger.log_message(f'error in {tool_call["id"]}: {error_msg}')
                    tool_result = {
                        "llmContent": error_msg,
                        "returnDisplay": error_msg
                    }
                except Exception as e:
                    # Handle other errors in tool execution
                    error_msg = f"Error executing tool: {str(e)}"
                    self.session_logger.log_message(f'error in {tool_call["id"]}: {error_msg}')
                    tool_result = {
                        "llmContent": error_msg,
                        "returnDisplay": error_msg
                    }
                
                return_display = tool_result.get("returnDisplay", "")
                if return_display is None:
                    return_display = ""
                self.session_logger.log_message(f'returned {tool_call["id"]}: {str(return_display)[:500]}')
                content = compress_output(str(tool_result["llmContent"]), self.config.model, tool_call["function"]["name"], self.session_logger, step_idx)
                tool_response = {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": content
                }
                self.history.append(tool_response)
                tool_responses.append(tool_response)
            self.session_logger.log_llm_request_response(step_idx, "tool_response", request_data, tool_responses, tool_call_history=self.tool_call_history)
            
            return {"type": "success"}
                
        except Exception as e:
            # Log error
            self.session_logger.log_llm_request_response(step_idx, "error", request_data, error=str(e))
            self.session_logger.log_message(f"error: {str(e)}")
            if "Please reduce the length of the messages or completion." in str(e) or "'max_tokens' or 'max_completion_tokens' is too large" in str(e):
                self._compress_history(force=True, step_idx=step_idx)
            return {"type": "error", "value": str(e)}

    def run_agent(self) -> bool:
        start_step = self.initialize_agent()
        for step_idx in tqdm(range(start_step, self.config.max_iterations)):
            result = self.step(step_idx)
            if result["type"] == "finished":
                verification = parse_json_response_with_codeblock(result["content"])
                return verification.get("is_success", False)
            elif result["type"] == "to_be_continued":
                self.history.append({
                    "role": "user",
                    "content": get_augmentation_verification_prompt(self.config.augmentation_plan)
                })
                self.augmentation_finished = True
        return False

    def run(self):
        # Run backend
        finished = self.run_agent()

        with open(os.path.join(self.config.log_dir, "finished.json"), "w", encoding="utf-8") as f:
            json.dump({"is_finished": finished}, f, indent=4)
        

