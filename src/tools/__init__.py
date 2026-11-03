from .base_tool import BaseTool
from .file_tools import ReadFileTool, WriteFileTool, ListDirectoryTool, GlobTool
from .shell_tool import ShellTool
from .edit_tool import EditTool
from .grep_tool import GrepTool
from .read_many_files_tool import ReadManyFilesTool
from .backend_test_tool import BackendTestTool
from .frontend_test_tool import FrontendTestTool
from .tool_types import ToolKind, ToolConfirmationDetails


def get_all_tools(working_dir: str, log_dir: str = None, is_frontend: bool = None):
    """Get all available tools."""
    if log_dir is not None:
        if is_frontend is None:
            return [
                ReadFileTool(working_dir),
                WriteFileTool(working_dir),
                ListDirectoryTool(working_dir),
                GlobTool(working_dir),
                GrepTool(working_dir),
                ReadManyFilesTool(working_dir),
                ShellTool(working_dir),
                EditTool(working_dir),
                BackendTestTool(working_dir, log_dir),
                FrontendTestTool(working_dir, log_dir)
            ]
        elif is_frontend:
            return [
                ReadFileTool(working_dir),
                WriteFileTool(working_dir),
                ListDirectoryTool(working_dir),
                GlobTool(working_dir),
                GrepTool(working_dir),
                ReadManyFilesTool(working_dir),
                ShellTool(working_dir),
                EditTool(working_dir),
                FrontendTestTool(working_dir, log_dir)
            ]
        else:
            return [
                ReadFileTool(working_dir),
                WriteFileTool(working_dir),
                ListDirectoryTool(working_dir),
                GlobTool(working_dir),
                GrepTool(working_dir),
                ReadManyFilesTool(working_dir),
                ShellTool(working_dir),
                EditTool(working_dir),
                BackendTestTool(working_dir, log_dir)
            ]
    else:
        if is_frontend is None:
            return [
                ReadFileTool(working_dir),
                WriteFileTool(working_dir),
                ListDirectoryTool(working_dir),
                GlobTool(working_dir),
                GrepTool(working_dir),
                ReadManyFilesTool(working_dir),
                ShellTool(working_dir),
                EditTool(working_dir),
                BackendTestTool(working_dir, log_dir)
            ]
        elif is_frontend:
            return [
                ReadFileTool(working_dir),
                WriteFileTool(working_dir),
                ListDirectoryTool(working_dir),
                GlobTool(working_dir),
                GrepTool(working_dir),
                ReadManyFilesTool(working_dir),
                ShellTool(working_dir),
                EditTool(working_dir)
            ]
        else:
            return [
                ReadFileTool(working_dir),
                WriteFileTool(working_dir),
                ListDirectoryTool(working_dir),
                GlobTool(working_dir),
                GrepTool(working_dir),
                ReadManyFilesTool(working_dir),
                ShellTool(working_dir),
                EditTool(working_dir)
            ]

def get_all_tools_no_shell(working_dir: str):
    """Get all available tools."""
    return [
        ReadFileTool(working_dir),
        WriteFileTool(working_dir),
        ListDirectoryTool(working_dir),
        GlobTool(working_dir),
        GrepTool(working_dir),
        ReadManyFilesTool(working_dir),
        EditTool(working_dir),
    ]


def get_info_gathering_tools(working_dir: str, log_dir: str = None):
    """Get info gathering tools."""
    return [
        ReadFileTool(working_dir),
        ListDirectoryTool(working_dir),
        GlobTool(working_dir),
        GrepTool(working_dir),
        ReadManyFilesTool(working_dir),
    ]