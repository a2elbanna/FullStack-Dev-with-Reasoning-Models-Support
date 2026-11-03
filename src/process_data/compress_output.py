import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import (
    ReadFileTool, 
    WriteFileTool,
    ListDirectoryTool, 
    GlobTool,
    ShellTool,
    EditTool,
    GrepTool,
    ReadManyFilesTool,
)
from utils import llm_generation


def get_shell_compression_prompt() -> str:
    return """You are a technical log compressor. Your task is to process the output from a shell tool by performing a lossy compression that **strictly preserves factual data** while removing redundant noise.

**Your directive is to TRANSFORM the text, not SUMMARIZE it.**

### **CRITICAL RULES:**
1.  **Preserve:** All error codes, status messages, unique identifiers, file paths, URLs, key css styles, and any non-repetitive text.
2.  **Remove:** repetitive errors or warnings, and large blocks of minified code.
3.  **Condense:** Replace long, repetitive internal state objects (e.g., `self.__next_f.push([1, ...]`) with a clear placeholder like `<!-- [NEXT INTERNAL STATE...] -->` or `[Turbopack dev scripts truncated]`.
4.  **Do NOT** add external analysis, "Actionable" items, or guesses. Only reflect the content that is present in the output.
5.  The final output should be a shortened, yet still technical, version of the original text.

**Now, compress the following output:**

Command: {command}
Output to compress:
{output_text}"""


def compress_shell_output(output: str, model: str, logger, step_idx) -> str:
    stdout_index = output.find("Stdout:")
    exit_code_index = output.rfind("Exit Code:")
    command = output[:stdout_index].strip()
    output_text = output[stdout_index + len("Stdout:"): exit_code_index].strip()
    exit_code = output[exit_code_index + len("Exit Code:"):].strip()

    prompt = get_shell_compression_prompt().format(command=command, output_text=output_text)
    messages = [{"role": "system", "content": "You are an expert at compressing text."}, {"role": "user", "content": prompt}]
    response = llm_generation(messages, model=model)

    request_data = {
        "model": model,
        "messages": messages.copy(),
    }
    logger.log_llm_request_response(step_idx, "compress_shell_output", request_data, response)
    compressed_output_text = response.get("content", "")
    compressed_output = f"{command}\nStdout (compressed): {compressed_output_text}\nExit Code: {exit_code}"

    return compressed_output.strip()


def compress_output(output: str, model: str, tool_name: str, logger, step_idx) -> str:
    if tool_name == ShellTool.Name and len(output) > 10000:
            return compress_shell_output(output, model, logger, step_idx)
    return output
