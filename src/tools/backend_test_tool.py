"""
ServiceTestTool – start a local service, probe its HTTP API, capture console
output, and return a concise summary (optionally compressed by an LLM).

Dependencies:
  * requests         – pip install requests
  * psutil (optional)– pip install psutil  (falls back to `lsof` if missing)
  * openai (optional)– pip install openai  (only needed when `openai_api_key`
                      is provided so the tool can shrink very long logs)
"""
from __future__ import annotations

import os
import shlex
import json
import time
import subprocess
import textwrap
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import requests
import re
import uuid
import libtmux

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import llm_generation, DBWatcher
from .base_tool import BaseTool
from .tool_types import ToolKind
from .tool_utils import kill_service_on_port

# --------------------------------------------------------------------------- #
# Utilities                                                                   #
# --------------------------------------------------------------------------- #

MAX_LOG_CHARS_BEFORE_SUMMARISE = 10000            # tweak as needed
SERVICE_STARTUP_TIMEOUT        = 180               # seconds
LOG_POLL_INTERVAL              = 0.4              # seconds


def get_backend_message_compression_prompt(long_text: str) -> str:
    return f"""You are a technical log compressor. Your task is to process the output by performing a lossy compression that **strictly preserves factual data** while removing redundant noise.

**Your directive is to TRANSFORM the text, not SUMMARIZE it.**

### **CRITICAL RULES:**
1.  **Preserve:** All error codes, status messages, unique identifiers, file paths, URLs, key css styles, and any non-repetitive text.
2.  **Remove:** repetitive errors or warnings, and large blocks of minified code. Also remove any useless noises.
3.  **Condense:** Replace long, repetitive internal state objects (e.g., `self.__next_f.push([1, ...]`) with a clear placeholder like `<!-- [NEXT INTERNAL STATE...] -->` or `[Turbopack dev scripts truncated]`.
4.  **Do NOT** add external analysis, "Actionable" items, or guesses. Only reflect the content that is present in the output.
5.  The final output should be a shortened, yet still technical, version of the original text.

**Now, compress the following output:**

Output to compress:
{long_text}"""


def _invoke_llm_summariser(long_text: str) -> str:
    """
    Shrinks `long_text` with the OpenAI ChatCompletion API, returning
    a concise summary that highlights errors / stack-traces.
    """
    if len(long_text) > MAX_LOG_CHARS_BEFORE_SUMMARISE:
        try:
            prompt = get_backend_message_compression_prompt(long_text)
            messages = [{"role": "system", "content": "You are an expert at compressing text."}, {"role": "user", "content": prompt}]
            response = llm_generation(messages, model=model)
            compressed_text = response.get("content", "")
        except Exception as e:
            print(f"Error during LLM compression: {str(e)}\n\nFalling to naive compression...")
            compressed_text = long_text[-MAX_LOG_CHARS_BEFORE_SUMMARISE:]
        is_compressed = True
    else:
        compressed_text = long_text
        is_compressed = False

    return compressed_text, is_compressed


def _host_variants(url: str) -> List[str]:
    """
    Return host:port variants that normalise `localhost` and `127.0.0.1`.

    Example
    -------
    >>> _host_variants('http://localhost:3001/api/stocks/AAPL')
    ['localhost:3001', '127.0.0.1:3001']
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port

    # If the hostname is neither localhost nor 127.0.0.1, just return it
    if host not in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return [f"{host}:{port}"]

    return [f"127.0.0.1:{port}", f"localhost:{port}", f"0.0.0.0:{port}"]


# CSI / SGR / cursor-movement / colour sequences (same as before, very fast).
_CSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

# OSC sequences: ESC ] … BEL or ESC ] … ESC \
_OSC_RE = re.compile(r"\x1B](?:[^\x07\x1b]*?)(?:\x07|\x1B\\)")

# ST / PM / APC, Device-control, etc.  (rare but easy to strip)
_MISC_RE = re.compile(r"\x1B[][PX^_].*?\x1B\\", re.DOTALL)

# ──────────────────────────────────────────────────────────────────────────────
def clean_console(data: Union[str, bytes]) -> str:
    """
    Strip NUL bytes, ANSI/VT-100 control sequences, and excessive blank lines
    from captured terminal output.  Works whether *data* comes straight from a
    log file (contains real ESC bytes) or from a JSON blob (contains literal
    ``\\u001b`` sequences).

    Parameters
    ----------
    data : str | bytes
        Raw console output.

    Returns
    -------
    str
        Readable, plain-text log.
    """
    # 0. Normalise to *str*.
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")

    # 1. Drop NUL / NULL padding (both literal and JSON-escaped forms).
    data = data.replace("\x00", "").replace("\\u0000", "")

    # 2. If we only have JSON-escaped ESC codes (\\u001b) but no real ones,
    #    convert them into real ESC so that the regexes can match.
    if "\\u001b" in data and "\x1b" not in data:
        data = bytes(data, "utf-8").decode("unicode_escape")

    # 3. Strip all kinds of ANSI escape sequences.
    data = _CSI_RE.sub("", data)
    data = _OSC_RE.sub("", data)
    data = _MISC_RE.sub("", data)

    # 4. Tidy up line endings and whitespace noise.
    data = data.replace("\r", "")
    data = re.sub(r"\n{3,}", "\n\n", data)   # collapse 3+ blank lines → 2
    data = data.lstrip("\n")                 # no leading blank lines

    return data


def _prepare_payload(raw, headers):
    """
    Decide whether to pass `json=` or `data=` to requests.request.

    Returns
    -------
    dict
        { "json": obj }          if raw is a dict/list
        { "json": obj }          if raw is a JSON string that parses cleanly
        { "data": raw }          otherwise
    dict
        merged headers (may add Content-Type)
    """
    if raw is None:
        return {}, headers

    # 1. Native JSON object → send with json=
    if isinstance(raw, (dict, list)):
        return {"json": raw}, headers

    # 2. String → try to parse
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
            # parsed! treat it as JSON
            return {"json": obj}, headers
        except json.JSONDecodeError:
            # not JSON → fall through to send as-is
            pass

    # 3. Anything else → send as data=
    # ensure we don't double-encode; set content-type if missing
    if "content-type" not in {k.lower() for k in headers.keys()}:
        headers["Content-Type"] = "application/json"  # or text/plain – pick what fits

    return {"data": raw}, headers


# --------------------------------------------------------------------------- #
# The Tool                                                                    #
# --------------------------------------------------------------------------- #


class BackendTestTool(BaseTool):
    """
    Tool that:
      1. Frees requested ports.
      2. Starts a service (`start_command`) in `directory_path`.
      3. Waits until `url` appears in log.
      4. Sends an HTTP request to `url` (relative, assumed `http://127.0.0.1:<first-port>`).
      5. Captures stdout/stderr into a log file.
      6. Generates a summary of parameters, HTTP response, and relevant log
         output (optionally compressed by an LLM).
    """

    Name = "backend_test"

    def __init__(self, working_dir: str, log_dir: str):
        super().__init__(
            self.Name,
            """Specialized backend testing tool. Launches a backend development service, waits for it to start, sends a single HTTP request to the supplied URL, then shuts the service down and returns the response to the request and the service's console log. Use this tool for tests after editing the backend code.

Expectation for required parameters  
1. `directory_path` MUST be an absolute path that exists; the service will be started here.  
2. `start_command` MUST be the exact shell command that starts the service (e.g. `npm run start`, `npm run dev`).  
3. `required_ports` MUST list every TCP port the service will bind to; any existing listeners on these ports will be killed before start.  
4. `url` MUST be a full URL (`http(s)://host:port/path`). This URL is invoked for the HTTP request.  
5. `method` MUST be a standard HTTP verb: `"GET"`, `"POST"`, `"PUT"`, `"PATCH"` or `"DELETE"`.

Optional parameters  
- `data` – JSON-serialisable body (ignored for `GET`).  
- `headers` – additional HTTP headers.  

**Important:**  
- If the `host:port` token never appears in the log, the tool fails.
- After the request, the service is terminated automatically.""",
            {
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Absolute path where start_command is executed.",
                    },
                    "start_command": {
                        "type": "string",
                        "description": "Shell command to start the service.",
                    },
                    "required_ports": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Ports that are used by the service.",
                    },
                    "url": {
                        "type": "string",
                        "description": (
                            "Full URL to call – must include protocol, host, port and path, "
                            "e.g. 'http://localhost:8080/health'."
                        ),
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    },
                    "data": {
                        "description": "JSON-serialisable body to send (optional).",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers.",
                    },
                },
                "required": [
                    "directory_path",
                    "start_command",
                    "required_ports",
                    "url",
                    "method",
                ],
            },
            ToolKind.EXECUTE,
        )
        self.working_dir = working_dir
        self.base_log_dir = log_dir

    # --------------------------------------------------------------------- #
    # Validation                                                             #
    # --------------------------------------------------------------------- #

    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        err = super().validate_params(params)
        if err:
            return err

        if not os.path.isabs(params["directory_path"]):
            return "directory_path must be absolute"

        if not os.path.exists(params["directory_path"]):
            return f"directory_path does not exist: {params['directory_path']}"

        if not isinstance(params["required_ports"], list) or not all(
            isinstance(p, (int, float)) for p in params["required_ports"]
        ):
            return "`required_ports` must be an array of numbers"

        return None

    @staticmethod
    def wait_for_url_in_log(log_file: str, full_url: str, timeout: int = SERVICE_STARTUP_TIMEOUT) -> bool:
        """
        Tail `log_file` until `full_url` (or its localhost/127.0.0.1 swap)
        is detected or `timeout` seconds elapse.
        """
        variants = _host_variants(full_url)
        print(variants)
        start = time.time()
        while time.time() - start < timeout:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    chunk = f.read()
                chunk = clean_console(chunk)
                # print(chunk)
            except FileNotFoundError:
                chunk = ""

            text = chunk.lower()
            # print(text)
            if any(v.lower() in text for v in variants):
                return True
            time.sleep(LOG_POLL_INTERVAL)
        return False

    # --------------------------------------------------------------------- #
    # Execution                                                              #
    # --------------------------------------------------------------------- #

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        validation_error = self.validate_params(params)
        if validation_error:
            return {
                "llmContent": f"Error: {validation_error}",
                "returnDisplay": f"Error: {validation_error}",
                "error": {"type": "invalid_tool_params", "message": validation_error},
            }

        db_dir = os.path.join(self.base_log_dir, "db")
        db_watcher = DBWatcher(db_dir)
        db_watcher.set_ckpt()

        # Extract
        dir_path: str = params["directory_path"]
        start_cmd: str = params["start_command"]
        ports: List[int] = [int(p) for p in params["required_ports"]]   # still freed
        full_url: str = params["url"]
        method: str = params["method"].upper()
        data = params.get("data")
        headers = params.get("headers") or {}
        oai_key = params.get("openai_api_key")

        # 1. Free ports
        for p in ports:
            kill_service_on_port(p)

        # 2. Launch service
        # --------------------------- tmux setup -------------------------- #
        log_file   = os.path.join(dir_path, "backend_service_test.log")
        # ensure the log file is truncated for a fresh run
        open(log_file, "w", encoding="utf-8").close()

        server = libtmux.Server()
        session_name = f"backend-test-{uuid.uuid4().hex[:8]}"
        session = server.new_session(
            session_name=session_name,
            start_directory=dir_path,
            kill_session=False
        )
        pane = session.attached_window.attached_pane

        # Compose a shell that mirrors `subprocess` behaviour:
        #   1. run the user command
        #   2. redirect both stdout & stderr to our log file
        #   3. keep the pane alive so we can later kill the session cleanly
        quoted_log = shlex.quote(log_file)
        pane.send_keys(
            f"bash -lc 'export PYTHONUNBUFFERED=1; {start_cmd} 2>&1 | tee -a {quoted_log}'",
            enter=True,
            suppress_history=True,
        )

        # 3. Wait for ports
        if not self.wait_for_url_in_log(log_file, full_url):
            session.kill_session()
            with open(log_file, encoding="utf-8") as fh:
                log_text = clean_console(fh.read())
            summary, is_comp = _invoke_llm_summariser(log_text)
            return {
                "llmContent": (
                    "Service did not log the expected URL within the timeout.\n\n"
                    f"Console log{' (compressed)' if is_comp else ''}:\n```\n{summary}\n```"
                ),
                "returnDisplay": {
                    "status": "startup_failed",
                    "log": summary,
                },
                "error": {
                    "type": "service_startup_timeout",
                    "message": "URL not found in log.",
                },
            }

        try:
            payload, headers = _prepare_payload(data, headers)

            resp = requests.request(
                method,
                full_url,
                headers=headers,
                timeout=30,
                **payload           # json=…  or  data=… chosen automatically
            )
            resp_text = resp.text
            status = resp.status_code
        except Exception as exc:  # noqa: BLE001
            resp_text = f"Request failed: {exc}"
            status = None

        # 5. Shutdown service
        session.kill_session()

        # 6. Read logs
        with open(log_file, "r", encoding="utf-8") as f:
            console_log = f.read()

        console_log = clean_console(console_log)
        console_summary, console_compressed = _invoke_llm_summariser(console_log)
        resp_summary, resp_compressed = _invoke_llm_summariser(resp_text)

        # 7. Build summary
        summary_dict = {
            "directory_path": dir_path,
            "start_command": start_cmd,
            "required_ports": ports,
            "url": full_url,
            "method": method,
            "data": data,
            "status_code": status,
            "console_compressed": console_compressed,
            "console_log": console_summary[:500],
            "resp_compressed": resp_compressed,
            "resp_log": resp_summary[:500],
        }

        llm_readable = f"""Service test completed
- Directory Path: `{dir_path}`
- Start Command: `{start_cmd}`
- Required Ports: {ports}
- Request: {method} {full_url}
- Data: {data}
- Response Status Code: {status}
- Response{' (compressed)' if resp_compressed else ''}: {resp_summary}

--- Console log{' (compressed)' if console_compressed else ''} ---
{console_summary}""".strip()

        if "Validation failed (numeric string is expected)" in resp_text:
            llm_readable += "\n\nThe \"Validation failed (numeric string is expected)\" is often due to incorrect api route order. Parameterised routes might have been defined before fixed/static routes, causing the fixed/static routes to be matched as parameters of parameterised routes and emitting validation errors. You should check the file where the API routes are defined (e.g. `[module_name].controller.ts`) to see if the routes are in the correct order."

        new_db_entries = db_watcher.get_new_entries()
        new_db_entries = "\n".join([f"[{e['timestamp']}] message: {e['message']}" for e in new_db_entries])[:5000]

        return {
            "llmContent": llm_readable,
            "returnDisplay": json.dumps(summary_dict, indent=2),
            "new_db_entries": new_db_entries,
        }