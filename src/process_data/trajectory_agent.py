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

from utils import SessionLogger, llm_generation, dump_database
from tools import get_all_tools
from .system_prompt import (
    get_core_system_prompt, 
    get_compression_prompt, 
    get_validation_prompt, 
    get_summary_prompt,
    get_backtranslation_instruction,
)
from .get_color_theme import get_background_component_color
from .tool_registry import ToolRegistry
from .templates import TEMPLATES, safe_copy_template
from .compress_output import compress_output

RETRY_LIMIT = 5
DB_CONFIG = dict(
    db_host="localhost",
    db_port=5432,
    db_username="myappuser",
    db_password="myapppassword",
    db_name="myapp",
)

@dataclass
class TrajectoryAgentConfig:
    summary: dict    # "title", "description", "qualityScore", "frontendPlan", "backendPlan", "userInstruction"
    chosen_template_name: str
    orig_project_path: str
    model: str
    working_dir: str
    log_dir: str
    max_history_length: int = 20
    max_iterations: int = 50
    overwrite: bool = False
    max_tokens: int = 8192
    compression_ratio: float = 0.5
    max_validation_num: int = 5
    max_summary_retry: int = 5
    backend_ratio: float = 0.5
    index: int = None
    framework_type: str = "next.js"
    temperature: float = 0.5


class TrajectoryAgent:
    """The first version of WebGen-Agent2"""
    
    def __init__(self, config: TrajectoryAgentConfig):
        self.config = config
        self.llm_generation = llm_generation
        self.history: List[Dict[str, Any]] = []
        self.tool_call_history: List[Dict[str, Any]] = []  # New attribute to track all tool calls
        self.max_history_length = self.config.max_history_length

        self.project_summary = self.config.summary
        self.orig_project_name = os.path.basename(self.config.orig_project_path)
        self.background_color, self.component_color = get_background_component_color()

        self.max_backend_iterations = round(self.config.max_iterations * self.config.backend_ratio)
        # Create a new session logger for this agent instance
        self.session_logger = SessionLogger(self.config.log_dir)
        self.validation_num = 0
        self.backend_summary = ""

        self.is_frontend = False
        self.is_pure_frontend = False
        if self.config.summary["backendPlan"] is None or len(self.config.summary["backendPlan"].get("apiEndpoints", [])) == 0:
            self.is_pure_frontend = True
            self.is_frontend = True

        self.initialize_tool_registry()
        self.chosen_template = None
        self.user_instruction = self.config.summary['userInstruction'] + f" Make the background color {self.background_color} and the compoment color {self.component_color}."
        self.project_summary['userInstruction'] = self.user_instruction
        self.total_error_count = 0

    def initialize_tool_registry(self):
        self.tools = get_all_tools(self.config.working_dir, self.config.log_dir)
        self.registry = ToolRegistry()
        for tool in self.tools:
            self.registry.register_tool(tool)

    def import_template(self):
        """Import a template based on the instruction and copy it to the working directory."""
        chosen_template_name = self.config.chosen_template_name
        
        # Find the chosen template
        chosen_template = None
        for template in TEMPLATES["templates"]:
            if template["name"] == chosen_template_name:
                chosen_template = template
                break
                
        # If no exact match found, try to find a partial match
        if not chosen_template:
            for template in TEMPLATES["templates"]:
                if chosen_template_name.lower() in template["name"].lower() or template["name"].lower() in chosen_template_name.lower():
                    chosen_template = template
                    break
                    
        # If still no match, default to the first template
        if not chosen_template:
            chosen_template = TEMPLATES["templates"][0]
            self.session_logger.log_message(f"No matching template found, defaulting to {chosen_template['name']}")
        else:
            self.session_logger.log_message(f"Chosen template: {chosen_template['name']}")

        # Copy template contents to working directory
        template_source = os.path.join(TEMPLATES["root_dir"], chosen_template["name"])
        copy_success = safe_copy_template(template_source, os.path.join(self.config.working_dir, "new_project"))
        if not copy_success:
            raise RuntimeError(f"Failed to copy template {chosen_template['name']} to {self.config.working_dir}")

        return chosen_template

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
                                    self.session_logger.log_message(f"Restoring chosen template: {log_data.get('chosen_template_name', 'N/A')}")
                                    
                                    # Load tool_call_history if it exists
                                    if "tool_call_history" in log_data:
                                        self.tool_call_history = log_data["tool_call_history"]
                                        # Execute tool calls that would affect the environment state
                                        self._restore_environment_state()
                                    
                                    self.session_logger.log_message(f"Restarting from step {start_step}")
                                    self.validation_num = log_data["request"].get("validation_num", 0)
                                    self.is_frontend = log_data["request"].get("is_frontend", False)
                                    self.is_pure_frontend = log_data["request"].get("is_pure_frontend", False)
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
            system_prompt = get_core_system_prompt(self.config.working_dir) + f"\n\n--- Template Information ---\n\n{self.chosen_template['common_instruction']}"

            if not self.is_pure_frontend:
                user_instruction = get_backtranslation_instruction(is_frontend=False, summary=self.project_summary, orig_project_name=self.orig_project_name, background_color=self.background_color, component_color=self.component_color, framework_type=self.config.framework_type)
                user_prompt = f"--- User Instruction ---\n\n{user_instruction}\n\n--- Backend Plan ---\n\n{json.dumps(self.project_summary['backendPlan'], indent=2)}\n\n--- Backend Information ---\n\n{self.chosen_template['backend_instruction']}\n\nImplement the backend part of the new project in the directory `new_project` based on the User Instruction and the Backend Plan. You should **only** modify the backend part of the new project."
            else:
                user_instruction = get_backtranslation_instruction(is_frontend=True, summary=self.project_summary, orig_project_name=self.orig_project_name, background_color=self.background_color, component_color=self.component_color, is_pure_frontend=self.is_pure_frontend, framework_type=self.config.framework_type)
                user_prompt = f"--- User Instruction ---\n\n{user_instruction}\n\n--- Frontend Plan ---\n\n{json.dumps(self.project_summary['frontendPlan'], indent=2)}\n\n--- Frontend Information ---\n\n{self.chosen_template['frontend_instruction']}\n\nThis is a pure frontend project. Implement the frontend part of the project based on the User Instruction and the Frontend Plan. You should **only** modify the frontend part of the project. Do NOT create, modify, or reference the backend."
            
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
                    "is_pure_frontend": self.is_pure_frontend,
                    "background_color": self.background_color,
                    "component_color": self.component_color
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
            "is_pure_frontend": self.is_pure_frontend,
            "background_color": self.background_color,
            "component_color": self.component_color
        }
        tool_schemas = self.registry.get_tool_schemas()
        request_data["tool_schemas"] = tool_schemas
            
        try:
            # Send request to LLM
            response = self.llm_generation(self.history, model=self.config.model, index=self.config.index, tools=tool_schemas, max_tokens=self.config.max_tokens, temperature=self.config.temperature)
            self.session_logger.log_llm_request_response(step_idx, "llm_response", request_data, response, chosen_template_name=self.chosen_template["name"])
            self.history.append(response)

            # Execute the tool calls
            request_data = {
                "model": self.config.model,
                "validation_num": self.validation_num,
                "is_frontend": self.is_frontend,
                "messages": self.history.copy(),
                "is_pure_frontend": self.is_pure_frontend,
                "background_color": self.background_color,
                "component_color": self.component_color
            }
            tool_responses = []
            tool_calls = response.get("tool_calls", None)

            if tool_calls is None or len(tool_calls) == 0:
                content_text = response.get("content", "")
                if content_text.strip().startswith("Summary:"):
                    if self.history[-2].get("role", "") == "user":
                        # if the first message after continue prompt is summary, finish
                        return {"type": "finished", "summary": content_text}
                    else:
                        self.history = self.history[:-1]
                        return {"type": "to_be_continued"}
                else:
                    return {"type": "to_be_continued"}

            for tool_call in tool_calls:
                self.tool_call_history.append(tool_call)
                self.session_logger.log_message(f'executing {tool_call["id"]}: {tool_call["function"]["name"]}...', self.is_frontend)
                try:
                    tool_args = json.loads(tool_call["function"]["arguments"])
                    tool_result = self.registry.execute_tool(tool_call["function"]["name"], tool_args)
                except json.JSONDecodeError as e:
                    # Handle incomplete or invalid JSON in tool arguments
                    error_msg = f"Invalid JSON in tool arguments: {str(e)}"
                    self.session_logger.log_message(f'error in {tool_call["id"]}: {error_msg}', self.is_frontend)
                    tool_result = {
                        "llmContent": error_msg,
                        "returnDisplay": error_msg
                    }
                except Exception as e:
                    # Handle other errors in tool execution
                    error_msg = f"Error executing tool: {str(e)}"
                    self.session_logger.log_message(f'error in {tool_call["id"]}: {error_msg}', self.is_frontend)
                    tool_result = {
                        "llmContent": error_msg,
                        "returnDisplay": error_msg
                    }
                
                return_display = tool_result.get("returnDisplay", "")
                if return_display is None:
                    return_display = ""
                self.session_logger.log_message(f'returned {tool_call["id"]}: {str(return_display)[:500]}', self.is_frontend)
                content = compress_output(str(tool_result["llmContent"]), self.config.model, tool_call["function"]["name"], self.session_logger, step_idx)
                tool_response = {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": content
                }
                if "new_db_entries" in tool_result:
                    tool_response["new_db_entries"] = tool_result["new_db_entries"]
                self.history.append(tool_response)
                tool_responses.append(tool_response)
            self.session_logger.log_llm_request_response(step_idx, "tool_response", request_data, tool_responses, tool_call_history=self.tool_call_history, chosen_template_name=self.chosen_template["name"])
            
            return {"type": "success"}
                
        except Exception as e:
            # Log error
            self.session_logger.log_llm_request_response(step_idx, "error", request_data, error=str(e))
            self.session_logger.log_message(f"error: {str(e)}", self.is_frontend)
            if "Please reduce the length of the messages or completion." in str(e) or "'max_tokens' or 'max_completion_tokens' is too large" in str(e):
                self._compress_history(force=True, step_idx=step_idx)
            self.total_error_count += 1
            return {"type": "error", "value": str(e)}

    def run_agent(self) -> bool:
        start_step = self.initialize_agent()
        for step_idx in tqdm(range(start_step, self.config.max_iterations)):
            result = self.step(step_idx)
            if self.total_error_count > RETRY_LIMIT:
                self.session_logger.log_message(f"Exceeded maximum error limit of {RETRY_LIMIT}. Terminating the agent.", self.is_frontend)
                break
            if result["type"] == "to_be_continued":
                if self.validation_num < self.config.max_validation_num:
                    self.history.append({
                        "role": "user",
                        "content": get_validation_prompt(self.is_frontend, self.user_instruction)
                    })
                    self.validation_num += 1
                elif self.validation_num < self.config.max_validation_num + self.config.max_summary_retry:
                    self.history.append({
                        "role": "user",
                        "content": get_summary_prompt(self.is_frontend)
                    })
                    self.validation_num += 1
                elif not self.is_frontend:
                    user_instruction = get_backtranslation_instruction(is_frontend=True, summary=self.project_summary, orig_project_name=self.orig_project_name, background_color=self.background_color, component_color=self.component_color, framework_type=self.config.framework_type)
                    user_prompt = f"--- User Instruction ---\n\n{user_instruction}\n\nThe backend has already been implemented above.\n\n--- Frontend Plan ---\n\n{json.dumps(self.project_summary['frontendPlan'], indent=2)}\n\n--- Frontend Information ---\n\n{self.chosen_template['frontend_instruction']}\n\nImplement the frontend part of the `new_project` based on the old project, the User Instruction, and the Frontend Plan. The backend APIs have already been implemented. You should **only** modify the frontend part of the project if possible. Do NOT modify the backend unless **absolutely necessary** and change as little as possible if you have to modify it."
                    self.validation_num = 0
                    self.history.append({
                        "role": "user",
                        "content": user_prompt
                    })
                    self.is_frontend = True
            elif result["type"] == "finished":
                if self.is_frontend:
                    return True
                else:
                    user_instruction = get_backtranslation_instruction(is_frontend=True, summary=self.project_summary, orig_project_name=self.orig_project_name, background_color=self.background_color, component_color=self.component_color, framework_type=self.config.framework_type)
                    user_prompt = f"--- User Instruction ---\n\n{user_instruction}\n\nThe backend has already been implemented above.\n\n--- Frontend Plan ---\n\n{json.dumps(self.project_summary['frontendPlan'], indent=2)}\n\n--- Frontend Information ---\n\n{self.chosen_template['frontend_instruction']}\n\nImplement the frontend part of the `new_project` based on the old project, the User Instruction, and the Frontend Plan. The backend APIs have already been implemented. You should **only** modify the frontend part of the project if possible. Do NOT modify the backend unless **absolutely necessary** and change as little as possible if you have to modify it."
                    self.validation_num = 0
                    self.history.append({
                        "role": "user",
                        "content": user_prompt
                    })
                    self.is_frontend = True
            elif (not self.is_frontend) and step_idx >= self.max_backend_iterations:    # backend and over max_backend_iterations
                if self.validation_num < self.config.max_validation_num + self.config.max_summary_retry:
                    self.history.append({
                        "role": "user",
                        "content": get_summary_prompt(self.is_frontend)
                    })
                    if self.validation_num < self.config.max_validation_num: # if validation not done, then move to summary
                        self.validation_num = self.config.max_validation_num
                    else: # else increase summary retry number
                        self.validation_num += 1
                else: # if validation and summary quota all over, start frontend dev
                    user_instruction = get_backtranslation_instruction(is_frontend=True, summary=self.project_summary, orig_project_name=self.orig_project_name, background_color=self.background_color, component_color=self.component_color, framework_type=self.config.framework_type)
                    user_prompt = f"--- User Instruction ---\n\n{user_instruction}\n\nThe backend has already been implemented above.\n\n--- Frontend Plan ---\n\n{json.dumps(self.project_summary['frontendPlan'], indent=2)}\n\n--- Frontend Information ---\n\n{self.chosen_template['frontend_instruction']}\n\nImplement the frontend part of the `new_project` based on the old project, the User Instruction, and the Frontend Plan. The backend APIs have already been implemented. You should **only** modify the frontend part of the project if possible. Do NOT modify the backend unless **absolutely necessary** and change as little as possible if you have to modify it."
                    self.validation_num = 0
                    self.history.append({
                        "role": "user",
                        "content": user_prompt
                    })
                    self.is_frontend = True
        return False

    def run(self):
        self.chosen_template = self.import_template()

        # Run backend
        finished = self.run_agent()

        if finished:
            with open(os.path.join(self.config.log_dir, "finished.json"), "w", encoding="utf-8") as f:
                json.dump({"is_finished": True}, f, indent=4)

        try: 
            dump = dump_database(DB_CONFIG, limit=5, connect_timeout=60)
            with open(os.path.join(self.config.log_dir, "dump_db.json"), "w", encoding="utf-8") as f:
                    json.dump(dump, f, indent=4)
        except Exception as e:
            self.session_logger.log_message(f"Dump database failed with error: {str(e)}")

