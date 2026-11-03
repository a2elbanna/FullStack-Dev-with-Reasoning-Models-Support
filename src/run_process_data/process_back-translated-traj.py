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
import re

from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial

from wrap_color_theme import wrap_color_theme
from safe_shell_execute import safe_shell_execute
import traceback

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import get_validation_prompt, get_core_system_prompt, TEMPLATES, ToolRegistry, get_planning_prompt
from tools import (
    ReadFileTool, 
    WriteFileTool,
    ListDirectoryTool, 
    GlobTool,
    ShellTool,
    EditTool,
    GrepTool,
    ReadManyFilesTool,
    BackendTestTool,
    FrontendTestTool,
    get_all_tools
)

from convert_messages_replace_working_dir import convert_messages_replace_working_dir

# -----------------------------------------------------------------------------
# config
# -----------------------------------------------------------------------------
MODEL_NAME = "/mnt/cache/agent/Zimu/models/Qwen3-Coder-30B-A3B-Instruct"
SCORE_WEIGHT = 0.9
BACKEND_TEST_THRESHOLD = 4
FRONTEND_TEST_THRESHOLD = 4
RESPONSE_NONEMPTY_LENGTH = 10

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


# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------
def ensure_mapping(value: Any) -> Dict[str, Any]:
    "Return a mapping (empty if value is None); crash if value is a list."
    return value if isinstance(value, dict) else {}


def clean_tool_schema(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strip possible OpenAI wrapper and make sure the inner dict has
    parameters.properties as a mapping so Jinja's |items filter succeeds.
    """
    tool = raw.get("function", raw)  # unwrap "type":"function" wrapper if any

    # guarantee required keys
    tool.setdefault("description", "")
    tool.setdefault("parameters", {"type": "object", "properties": {}})
    params = tool["parameters"]
    params.setdefault("type", "object")
    params["properties"] = ensure_mapping(params.get("properties"))
    params.setdefault("required", [])

    # For every property, make sure it is a mapping
    for key, spec in list(params["properties"].items()):
        if not isinstance(spec, dict):
            params["properties"][key] = {"type": "string"}

    return tool


def clean_messages(raw_msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalise message structure so the template expectations are met.
    """
    cleaned: List[Dict[str, Any]] = []
    for m in raw_msgs:
        role = m.get("role")
        if role == "assistant" and "tool_calls" in m:
            # enforce list
            tc_list = m["tool_calls"]
            if isinstance(tc_list, dict):
                tc_list = [tc_list]
            new_tc_list = []
            for tc in tc_list:
                func = tc.get("function", tc)  # may already be at root
                # arguments must be mapping
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if not isinstance(args, dict):
                    args = {}
                func["arguments"] = args
                new_tc_list.append({"function": func})
            m["tool_calls"] = new_tc_list
            # content may be null – template wants string
            m["content"] = m.get("content") or ""
        cleaned.append(m)
    return cleaned


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------
def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)
    

def get_messages_tools(log_dir, step_idx):
    log_dir = Path(log_dir)
    llm_response = log_dir / f"{step_idx}_llm_response.json"
    tool_response = log_dir / f"{step_idx}_tool_response.json"

    if tool_response.is_file():
        llm = load_json(llm_response)
        tool = load_json(tool_response)

        raw_tools = llm["request"]["tool_schemas"]
        tools = [clean_tool_schema(t) for t in raw_tools]

        raw_messages = tool["request"]["messages"] + tool["response"]
        messages = clean_messages(raw_messages)
        is_tool = True
    else:
        llm = load_json(llm_response)

        raw_tools = llm["request"]["tool_schemas"]
        tools = [clean_tool_schema(t) for t in raw_tools]

        raw_messages = llm["request"]["messages"] + [llm["response"]]
        messages = clean_messages(raw_messages)
        is_tool = False

    background_color = llm["request"].get("background_color", None)
    component_color = llm["request"].get("component_color", None)

    return messages, tools, background_color, component_color, is_tool


def get_compress_history(log_dir, step_idx):
    log_dir = Path(log_dir)
    compress_history_log = log_dir / f"{step_idx}_compress_history.json"

    compress_history = load_json(compress_history_log)

    raw_messages = compress_history["request"]["messages"] + [compress_history["response"]]
    messages = clean_messages(raw_messages)

    return messages, compress_history["request"].get("background_color", None), compress_history["request"].get("component_color", None)


def initialize_tool_registry(working_dir, log_dir):
    tools = get_all_tools(working_dir, log_dir)
    registry = ToolRegistry()
    for tool in tools:
        registry.register_tool(tool)
    return registry


def replace_tool_outputs(messages, replacement_dict):
    for idx, message in enumerate(messages):
        if message["role"] == "system":
            if message["content"].startswith(SYSTEM_PREFIX):
                message["content"] = replacement_dict["system_prompt"]
        elif message["role"] == "assistant":
            msg_id = str(message.get("msg_id", -1))
            if msg_id in replacement_dict:
                tool_content = replacement_dict[msg_id]
                for j in range(idx, len(messages), 1):
                    if messages[j]["role"] == "tool":
                        messages[j]["content"] = tool_content
                        break
    return messages


CMD_FAILED_SUB = "Stdout: ERROR: Previous command still running – send `is_input=true` or interrupt (C-c) first."

def adjust_tool_output(trajectories, adjusted_project_path, log_dir, template):
    template_path = os.path.join(TEMPLATE_ROOT, template["name"])

    if os.path.isdir(adjusted_project_path):
        shutil.rmtree(adjusted_project_path)
    shutil.copytree(template_path, adjusted_project_path)

    registry = initialize_tool_registry(adjusted_project_path, log_dir)

    tools_to_adjust = [
        WriteFileTool.Name, # ensure files are created for listdirtool, ensure file content for grep tool
        ListDirectoryTool.Name, 
        GlobTool.Name,
        ShellTool.Name,
        EditTool.Name,
        GrepTool.Name,
    ]
    commands_to_execute = ["rm", "mkdir"]

    full_messages = trajectories[-1]["messages"]
    replacement_dict = {}
    for idx, message in enumerate(full_messages):
        if message["role"] == "system":
            if message["content"].startswith(SYSTEM_PREFIX):
                replacement_dict["system_prompt"] = get_core_system_prompt(adjusted_project_path)
        if message["role"] == "assistant":
            for tool_call in message.get("tool_calls", []):
                # print(tool_call["function"])
                if tool_call["function"]["name"] in tools_to_adjust:
                    if tool_call["function"]["name"] == ShellTool.Name:
                        tool_content = ""
                        for j in range(idx + 1, len(full_messages), 1):
                            if full_messages[j]["role"] == "tool":
                                tool_content = full_messages[j]["content"]
                                break
                        # find out if the command had failed in the original command, if not, execute it
                        if CMD_FAILED_SUB not in tool_content:
                            try:
                                output = safe_shell_execute(tool_call["function"]["arguments"].get("command", ""), adjusted_project_path)
                                # print(output)
                            except Exception as e:
                                print(str(e))
                    elif tool_call["function"]["name"] in [ListDirectoryTool.Name, GlobTool.Name, GrepTool.Name] and tool_call["function"]["arguments"].get("path", "") == adjusted_project_path:
                        tool_response = registry.execute_tool(tool_call["function"]["name"], tool_call["function"]["arguments"])
                        replacement_dict[str(message["msg_id"])] = str(tool_response["llmContent"])
                        # print(tool_response["llmContent"])
                    else:
                        tool_response = registry.execute_tool(tool_call["function"]["name"], tool_call["function"]["arguments"])
                        # print(tool_response["llmContent"])
    
    trajectories[-1]["replacement_dict"] = replacement_dict
    for traj in trajectories:
        traj["messages"] = replace_tool_outputs(traj["messages"], replacement_dict)
        traj["compressed_section"] = replace_tool_outputs(traj["compressed_section"], replacement_dict)
    
    return trajectories


def convert_compressed_message(content):
    lines = content.split("\n")
    filtered_lines = [line.replace("new project", "project") for line in lines if "old project" not in line]
    return "\n".join(filtered_lines)


TEMPLATE_ROOT = "/mnt/cache/agent/Zimu/WebGen-Agent2/templates"
FRONTEND_PREFIX = "--- User Instruction ---\n\nYou are tasked with implementing the frontend"
BACKEND_PREFIX = "--- User Instruction ---\n\nYou are tasked with implementing the backend"
VALIDATION_PREFIX = "Validate whether all the required features have been implemented. You must make sure that all features have been fully implemented and tested."
FRONTEND_VALIDATION_SUB = "- If the frontend plan has not been fully implemented, comtinue implementing it and make sure everything has been properly implemented."
SYSTEM_PREFIX = "Environment Context:"
COMPRESSED_PREFIX = "<COMPRESSED_HISTORY>"

def convert_messages(messages, working_dir, log_dir, frontend_plan, backend_plan, template, user_instruction, is_pure_frontend, adjusted_working_dir_root):
    i = 0
    old_project_path = os.path.join(working_dir, os.path.basename(working_dir).split("___")[-1])
    new_project_path = os.path.join(working_dir, "new_project")
    adjusted_project_path = os.path.join(adjusted_working_dir_root, os.path.basename(working_dir))
    replace_pairs = [("new project", "project"), ("old project", "project")]

    while i < len(messages):
        message = messages[i]
        if message["role"] == "user":
            if message["content"].startswith(BACKEND_PREFIX):
                message["content"] = f"--- User Instruction ---\n\n{user_instruction}\n\n--- Backend Plan ---\n\n{json.dumps(backend_plan, indent=2)}\n\n--- Backend Information ---\n\n{template['backend_instruction']}\n\nImplement the backend part of the project based on the User Instruction and the Backend Plan. You should **only** modify the backend part of the project."
            elif message["content"].startswith(FRONTEND_PREFIX):
                if is_pure_frontend:
                    message["content"] = f"--- User Instruction ---\n\n{user_instruction}\n\n--- Frontend Plan ---\n\n{json.dumps(frontend_plan, indent=2)}\n\n--- Frontend Information ---\n\n{template['frontend_instruction']}\n\nThis is a pure frontend project. Implement the frontend part of the project based on the User Instruction and the Frontend Plan. You should **only** modify the frontend part of the project. Do NOT create, modify, or reference the backend."
                else:
                    message["content"] = f"--- User Instruction ---\n\n{user_instruction}\n\nThe backend has already been implemented above.\n\n--- Frontend Plan ---\n\n{json.dumps(frontend_plan, indent=2)}\n\n--- Frontend Information ---\n\n{template['frontend_instruction']}\n\nImplement the frontend part of the project based on the User Instruction and the Frontend Plan. The backend APIs have already been implemented. You should **only** modify the frontend part of the project if possible. Do NOT modify the backend unless **absolutely necessary** and change as little as possible if you have to modify it."
            elif message["content"].startswith(VALIDATION_PREFIX):
                if FRONTEND_VALIDATION_SUB in message["content"]:
                    message["content"] = get_validation_prompt(is_frontend=True, user_instruction=user_instruction)
                else:
                    message["content"] = get_validation_prompt(is_frontend=False, user_instruction=user_instruction)
            message["content"] = message["content"].replace(new_project_path, adjusted_project_path)
            message["content"] = message["content"].replace(working_dir, adjusted_project_path)

        elif message["role"] == "assistant":
            should_pop = False
            for tool_call in message.get("tool_calls", []):
                if old_project_path in tool_call["function"]["arguments"].get("path", "") or old_project_path in tool_call["function"]["arguments"].get("command", "") or (tool_call["function"]["name"] == "list_directory" and tool_call["function"]["arguments"].get("path", "") == working_dir):
                    should_pop = True
                    break
                for k, v in tool_call["function"]["arguments"].items():
                    if isinstance(v, str):
                        tool_call["function"]["arguments"][k] = v.replace(new_project_path, adjusted_project_path)
                        tool_call["function"]["arguments"][k] = tool_call["function"]["arguments"][k].replace(working_dir, adjusted_project_path)
                
            if should_pop:
                popped_msg = messages.pop(i)
                while i < len(messages) and messages[i]["role"] == "tool":
                    messages.pop(i)
                continue
            else:
                if "content" in message.keys():
                    message["content"] = message["content"].replace(new_project_path, adjusted_project_path)
                    message["content"] = message["content"].replace(working_dir, adjusted_project_path)

                    for old, new in replace_pairs:
                        message["content"] = message["content"].replace(old, new)
        
        elif message["role"] == "system":
            if "content" in message.keys():
                message["content"] = message["content"].replace(new_project_path, adjusted_project_path)
                message["content"] = message["content"].replace(working_dir, adjusted_project_path)
                if message["content"].startswith(COMPRESSED_PREFIX):
                    message["content"] = convert_compressed_message(message["content"])

        elif message["role"] == "tool":
            if "content" in message.keys():
                message["content"] = message["content"].replace(new_project_path, adjusted_project_path)
                message["content"] = message["content"].replace(working_dir, adjusted_project_path)
                message["content"] = message["content"].replace("new_project/", "")
        i += 1

    return messages


Trajectory = Dict[str, Optional[object]]   # {"step": int, "kind": str, "messages": list, "tools": list|None}


def get_compressed(log_dir, n):
    data = load_json(Path(os.path.join(log_dir, f"{n}_compress_history.json")))
    compressed_messages = clean_messages(json.loads(data["request"]["messages"][1]["content"]))
    return compressed_messages


def get_trajectories(log_dir: str | Path) -> List[Trajectory]:
    log_dir = Path(log_dir)
    if not log_dir.is_dir():
        raise FileNotFoundError(log_dir)

    traj: List[Trajectory] = []

    comp_re = re.compile(r"^(\d+)_compress_history\.json$")
    compress_steps: List[int] = sorted(
        int(m.group(1)) for p in log_dir.iterdir()
        if (m := comp_re.match(p.name))
    )

    curr_background_color = None
    curr_component_color = None
    tools = None

    compressed_section = []
    new_messages_start = 0
    idx = 0
    full_messages = []
    for n in compress_steps:
        prev = n - 1

        messages, tools, background_color, component_color, is_tool = get_messages_tools(log_dir, prev)
        if background_color is not None and component_color is not None:
            curr_background_color, curr_component_color = background_color, component_color

        compressed_messages = get_compressed(log_dir, n)
        compress_length = len(compressed_messages)

        k = 0
        if new_messages_start > 0:
            for i in range(new_messages_start - 1, -1, -1):
                # mark as old message
                messages[i]["is_old"] = True

                # mark old assistant messages with consistant indexes
                if messages[i]["role"] == "assistant" and i >= 4:
                    messages[i]["msg_id"] = idx - k
                    k += 1
        
        for i in range(new_messages_start, len(messages), 1):
            # add new indexes for new messages
            if messages[i]["role"] == "assistant" and i >= 3:
                idx += 1
                messages[i]["msg_id"] = idx

        full_messages.extend(messages[new_messages_start:])

        traj.append(
            dict(
                step=prev,
                kind="compress_before",
                messages=messages,
                tools=tools,
                compressed_section=compressed_section,
            )
        )

        compressed_section = compressed_messages
        new_messages_start = len(messages) - compress_length + 1
        

    llm_re = re.compile(r"^(\d+)_llm_response\.json$")
    llm_steps = sorted(
        int(m.group(1)) for p in log_dir.iterdir()
        if (m := llm_re.match(p.name))
    )
    if llm_steps:                       # the directory *should* have at least one
        last_llm = llm_steps[-1]
        messages, tools, background_color, component_color, is_tool = get_messages_tools(log_dir, last_llm)
        if background_color is not None and component_color is not None:
            curr_background_color, curr_component_color = background_color, component_color

        k = 0
        if new_messages_start > 0:
            for i in range(new_messages_start - 1, -1, -1):
                # mark as old message
                messages[i]["is_old"] = True

                # mark old assistant messages with consistant indexes
                if messages[i]["role"] == "assistant" and i >= 4:
                    messages[i]["msg_id"] = idx - k
                    k += 1
        
        for i in range(new_messages_start, len(messages), 1):
            # add new indexes for new messages
             if messages[i]["role"] == "assistant" and i >= 3:
                idx += 1
                messages[i]["msg_id"] = idx

        full_messages.extend(copy.deepcopy(messages[new_messages_start:]))

        traj.append(
            dict(
                step=last_llm,
                kind="llm_final",
                messages=messages,
                tools=tools,
                compressed_section=compressed_section,
            )
        )

    traj.append(
        dict(
            step=-1,
            kind="uncompressed_messages",
            messages=full_messages,
            tools=tools,
            compressed_section=[],
        )
    )

    return traj, curr_background_color, curr_component_color


def process_trajectories(trajectories, working_dir, log_dir, frontend_plan, backend_plan, template, user_instruction, is_pure_frontend, adjusted_working_dir_root):
    adjusted_project_path = os.path.join(adjusted_working_dir_root, os.path.basename(working_dir))
    for traj in trajectories:
        traj["log_dir"] = log_dir
        traj["orig_working_dir"] = working_dir
        traj["working_dir"] = adjusted_project_path
        traj["messages"] = convert_messages(traj["messages"], working_dir, log_dir, frontend_plan, backend_plan, template, user_instruction, is_pure_frontend, adjusted_working_dir_root)
        traj["compressed_section"] = convert_messages(traj["compressed_section"], working_dir, log_dir, frontend_plan, backend_plan, template, user_instruction, is_pure_frontend, adjusted_working_dir_root)

    trajectories = adjust_tool_output(trajectories, adjusted_project_path, log_dir, template)
    return trajectories


def extract_colors(text: str) -> Optional[Tuple[str, str]]:
    pattern = re.compile(
        r"""
        Make\ the\ background\ color\s+
        (?P<bg>.+?)                        # capture background colour (lazy)
        \s+and\ the\ compoment\ color\s+
        (?P<comp>.+?)                      # capture component colour (lazy)
        (?=[.?!]|$)                        # stop just before ., ?, ! or EOS
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    m = pattern.search(text)
    if m:
        bg_color   = m.group("bg").strip()
        comp_color = m.group("comp").strip()
        return bg_color, comp_color

    return None, None


def find_colors(trajectories):
    background_color, component_color = None, None
    for traj in trajectories:
        for message in traj["messages"]:
            if message["role"] == "user":
                bg_color, cp_color = extract_colors(message["content"])
                if bg_color is not None:
                    background_color, component_color = bg_color, cp_color
                    break
    return background_color, component_color


def get_planning_trajectory(info_data, user_instruction, is_pure_frontend, log_dir, working_dir, adjusted_working_dir_root):
    prompt = get_planning_prompt(user_instruction, is_pure_frontend)

    frontend_plan_str = json.dumps(info_data["summary"]["frontendPlan"], indent=2)
    backend_plan_str = json.dumps(info_data["summary"]["backendPlan"], indent=2)
    response = "```json\n{\n  \"backendPlan\": " + backend_plan_str + ",\n  \"frontendPlan\": " + frontend_plan_str + "\n}\n```"

    messages = [
        {"role": "system", "content": "You are a senior full-stack software architect."},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": response}
    ]

    adjusted_project_path = os.path.join(adjusted_working_dir_root, os.path.basename(working_dir))
    return {
        "step": -1,
        "kind": "planning_messages",
        "tools": [],
        "log_dir": log_dir,
        "orig_working_dir": working_dir,
        "working_dir": adjusted_project_path,
        "messages": messages,
        "compressed_section": []
    }


# ── “obvious” SQL verbs we want to forbid ──────────────────────────────────────
_SQL_KEYWORDS = (
    "SELECT", "INSERT", "UPDATE", "DELETE", "DROP",
    "CREATE", "ALTER", "TRUNCATE", "MERGE", "REPLACE",
    "EXEC", "EXECUTE", "CALL",
    "UNION", "INTERSECT", "EXCEPT",
    "GRANT", "REVOKE"
)


def check_db_interaction(message) -> bool:
    if "new_db_entries" not in message:
        return False

    entry: str = message["new_db_entries"]
    if not isinstance(entry, str):
        return False

    entry_upper = entry.upper()
    for sql_phrase in _SQL_KEYWORDS:
        if sql_phrase in entry_upper:
            return True

    return False


def get_function_appearance_scores(message) -> tuple[int, int]:
    content = message["content"]
    # extract function and appearance scores from the content
    def first_digit_after(label: str) -> Optional[int]:
        """Return first digit (as int) that appears after `label` in `content`."""
        # Find the starting index of the label
        start = content.find(label)
        if start == -1:
            return 0

        # Slice the string *after* the label
        tail = content[start + len(label):]

        # Look for the first digit in the tail
        m = re.search(r"\d", tail)
        return int(m.group()) if m else 0

    function_score   = first_digit_after("GUI Agent Testing Score")
    appearance_score = first_digit_after("Appearance Grade")

    if not check_db_interaction(message):
        function_score -= 0.3

    return function_score, appearance_score


def get_trajectory_grade(trajectory, weight=SCORE_WEIGHT, backend_test_threshold=BACKEND_TEST_THRESHOLD, frontend_test_threshold=FRONTEND_TEST_THRESHOLD):
    backend_score = 0
    backend_test_num = 0
    frontend_function_score = 0
    frontend_appearance_score = 0
    frontend_test_num = 0
    for i in range(len(trajectory["messages"]) - 1):
        message = trajectory["messages"][i]
        if message["role"] == "assistant" and len(message.get("tool_calls", [])) == 1:
            if message["tool_calls"][0]["function"]["name"] == "backend_test":
                backend_test_num += 1
                # check if the response status code is 200 and db interaction is correct
                if "Response Status Code: 200" in trajectory["messages"][i + 1]["content"] and check_db_interaction(trajectory["messages"][i + 1]):
                    # only consider non-empty response as success
                    is_empty_response = True
                    for line in trajectory["messages"][i + 1]["content"].split("\n"):
                        if line.startswith("- Response:"):
                            if len(line.replace("- Response:", "").strip(" \n\t[]")) > RESPONSE_NONEMPTY_LENGTH:
                                backend_score = backend_score * weight + 1
                                is_empty_response = False
                                break
                    if is_empty_response:
                        backend_score = backend_score * weight
                else:
                    backend_score = backend_score * weight - 1
            elif message["tool_calls"][0]["function"]["name"] == "frontend_test":
                frontend_test_num += 1
                function_score, appearance_score = get_function_appearance_scores(trajectory["messages"][i + 1])
                frontend_function_score = frontend_function_score * weight + (function_score - 3.5)
                frontend_appearance_score = frontend_appearance_score * weight + (appearance_score - 3.5)
    if backend_test_num < BACKEND_TEST_THRESHOLD or frontend_test_num < FRONTEND_TEST_THRESHOLD:
        backend_score = -1
        frontend_function_score = -1
        frontend_appearance_score = -1
    return backend_score, frontend_function_score, frontend_appearance_score


def db_check(db_path):
    if not os.path.isfile(db_path):
        return False
    # try:
    db_data = load_json(Path(db_path))
    if len(db_data) <= 0 or len(json.dumps(db_data, ensure_ascii=False)) < 150:
        return False
    else:
        return True
    # except:
    #     return False

def _process_one_sample(
    info_data: Dict[str, Any],
    *,
    log_root_dir: str,
    adjusted_working_dir_root: str,
    template: Dict[str, Any],
) -> List[Trajectory] | None:
    """
    Execute the original per-sample pipeline.
    In case of *any* exception we convert it into a picklable form so the parent
    process never sees un-picklable objects such as os.DirEntry.
    """
    try:
        # ---------------------------------------------------------------------
        # original code (unchanged)
        # ---------------------------------------------------------------------
        log_dir = os.path.join(log_root_dir, info_data["id"])
        if not os.path.isfile(os.path.join(log_dir, "finished.json")):
            return info_data

        if not db_check(os.path.join(log_dir, "dump_db.json")):
            return info_data

        trajectories, background_color, component_color = get_trajectories(log_dir)

        if len(trajectories) == 0:
            return info_data
        backend_score, frontend_function_score, frontend_appearance_score = get_trajectory_grade(trajectories[-1])
        if backend_score <= 0 or frontend_function_score <= 0 or frontend_appearance_score <= 0:
            return info_data

        if background_color is None or component_color is None:
            background_color, component_color = find_colors(trajectories)
            if background_color is None or component_color is None:
                return info_data

        working_dir = log_dir.replace("logs_root", "workspaces_root")
        frontend_plan   = info_data["summary"]["frontendPlan"]
        backend_plan    = info_data["summary"]["backendPlan"]
        user_instruction = (
            info_data["summary"]["userInstruction"]
            + " "
            + wrap_color_theme(background_color, component_color)
        )

        is_pure_frontend = (
            backend_plan is None or len(backend_plan.get("apiEndpoints", [])) == 0
        )

        trajectories = process_trajectories(
            trajectories,
            working_dir,
            log_dir,
            frontend_plan,
            backend_plan,
            template,
            user_instruction,
            is_pure_frontend,
            adjusted_working_dir_root,
        )

        trajectories.append(get_planning_trajectory(info_data, user_instruction, is_pure_frontend, log_dir, working_dir, adjusted_working_dir_root))
        return trajectories

    # -------------------------------------------------------------------------
    # catch *everything*, make it picklable
    # -------------------------------------------------------------------------
    except Exception as exc:
        tb = traceback.format_exc()
        sys.stderr.write(
            f"[worker] sample {info_data.get('id', '<unknown>')} failed:\n{tb}\n"
        )
        sys.stderr.flush()
        return info_data


def get_train(
    log_root_dir: str,
    info_path: str,
    out_path: str,
    unfinished_path: str,
    adjusted_working_dir_root: str,
    *,
    template_name: str = "nextjs-nestjs-postresql",
    max_workers: int | None = None,         # let the caller tune the pool size
) -> None:
    # -------------------------------------------------------------------------
    # locate the template once; we will broadcast it to the workers
    # -------------------------------------------------------------------------
    template = next(
        temp for temp in TEMPLATES["templates"] if temp["name"] == template_name
    )

    info_datas = load_jsonl(info_path)

    datas: List[Trajectory] = []
    unfinished_datas = []
    finished_samples = 0

    process_one = partial(
        _process_one_sample,
        log_root_dir=log_root_dir,
        adjusted_working_dir_root=adjusted_working_dir_root,
        template=template,
    )

    # -------------------------------------------------------------------------
    # fire up the worker pool
    # -------------------------------------------------------------------------
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_one, info): info for info in info_datas}

        with tqdm(total=len(futures), desc="processing samples") as pbar:
            for fut in as_completed(futures):
                result = fut.result()
                if isinstance(result, list):
                    # each successful result is a list[Trajectory]
                    datas.extend(result)
                    finished_samples += 1
                elif isinstance(result, dict):
                    unfinished_datas.append(result)
                pbar.update(1)

    print(f"\n\nfinished samples: {finished_samples}")
    for i in range(len(datas)):
        new_working_dir = convert_messages_replace_working_dir(datas[i]["messages"], datas[i]["working_dir"], i)
        new_working_dir = convert_messages_replace_working_dir(datas[i]["compressed_section"], datas[i]["working_dir"], i)
    save_jsonl(datas, out_path)

    print(f"\n\nunfinished samples: {len(unfinished_datas)}")
    save_jsonl(unfinished_datas, unfinished_path)


def main() -> None:
    rnd_idx = 2
    log_root_dir = f"/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-qwen3_coder_30b_full_fullstack-agent_nextjs_nestjs_30B_backtranslated_tighter-filter_305_77_2032_checkpoint-254_hist-100_iter-500_compress-0.5_val-1_sum-5_aug-nestjs_backtrans_new_rnd{rnd_idx}"
    info_path = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_gathered_rnd{rnd_idx}.jsonl"
    out_path = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_backtranslated_rnd{rnd_idx}.jsonl"
    unfinished_path = f"/mnt/cache/agent/Zimu/WebGen-Agent2/src/run_process_data/jsonl_files/nestjs_github-repos_aug-gathered_info_Qwen3-Coder-30B-A3B-Instruct_gathered_rnd{rnd_idx + 1}.jsonl"
    adjusted_working_dir_root = f"/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-qwen3_coder_30b_full_fullstack-agent_nextjs_nestjs_30B_backtranslated_tighter-filter_305_77_2032_checkpoint-254_hist-100_iter-500_compress-0.5_val-1_sum-5_aug-nestjs_new_backtrans_adjusted1_rnd{rnd_idx}"
    max_workers = 16
    get_train(log_root_dir, info_path, out_path, unfinished_path, adjusted_working_dir_root, template_name="nextjs-nestjs-postresql", max_workers=max_workers, )


if __name__ == "__main__":
    main()