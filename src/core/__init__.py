"""
Core package for Qwen Code Python.
"""
from .tool_registry import ToolRegistry
from .tool_error import ToolError, ToolNotFoundError, ToolExecutionError, format_tool_error
from .system_prompt import get_core_system_prompt, get_compression_prompt, get_planning_prompt, get_validation_prompt, get_summary_prompt
from .agent import AgentConfig, WebGenAgent2V1
try:
    # Optional parallel variant; not present in all checkouts and not used by
    # the standard run_batch path. Guard so a missing module doesn't break import.
    from .agent_parallel import AgentConfig_parallel, WebGenAgent2V1_parallel
except ModuleNotFoundError:
    AgentConfig_parallel = None
    WebGenAgent2V1_parallel = None
from .compress_output import compress_output
from .templates import TEMPLATES

__all__ = [
    "ToolRegistry",
    "ToolError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "format_tool_error",
    "AgentConfig",
    "WebGenAgent2V1",
    "get_core_system_prompt", 
    "get_compression_prompt", 
    "get_planning_prompt", 
    "get_validation_prompt", 
    "get_summary_prompt"
]