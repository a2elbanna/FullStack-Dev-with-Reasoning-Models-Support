import os
import subprocess
import time
import re
from typing import List, Tuple, Optional, Dict, Any
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from playwright.sync_api import TimeoutError as PWTimeout
from PIL import Image, ImageDraw, ImageFont
import base64
import io
import json
import sys
import logging

import shlex
from pathlib import Path
import bashlex
import libtmux

DOM_IDLE_MS   = 100       # how long the DOM must stay unchanged
DOM_TIMEOUT_MS = 2000     # give up after this time
MAX_RETRIES    = 30        # how many times we try the whole sequence
MAX_LOG_CHARS_BEFORE_SUMMARISE = 2000
REPEAT_MAX = 2          # how many identical replies in a row ≡ loop
LOOP_NUDGE = (
    "WARNING: You have repeated the **exact same** response for several "
    "turns.  You are stuck in a repetition loop.  THINK CAREFULLY and "
    "produce a NEW, DIFFERENT action.  Do not repeat your previous reply."
)
FAST_LOAD_STATE   = "domcontentloaded"   # instead of "networkidle"
FAST_LOAD_TIMEOUT = 120_000               # 2 min is plenty for a local dev server

# Add the current directory to the path so we can import vlm_generation
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from vlm_generation import vlm_generation
from webtester_utils import kill_service_on_port, get_interactive_elements, clean_console, scrub_images, build_format_ele_text
from get_colors import most_used_colors


def _safe_dict(obj) -> dict:
    """Return obj if it is a mapping, else an empty dict."""
    return obj if isinstance(obj, dict) else {}


def _within(idx: int, items: list[Any]) -> bool:
    return 0 <= idx < len(items)


def _wait_clickable(el, timeout=10_000):
    """
    Wait until the element is visible, enabled and stable.
    Raise PWTimeout if it never becomes clickable.
    """
    el.wait_for_element_state("visible",  timeout=timeout)
    el.wait_for_element_state("enabled",  timeout=timeout)
    el.wait_for_element_state("stable",   timeout=timeout)


def get_frontend_message_compression_prompt(long_text: str) -> str:
    return f"""You are a technical log compressor. Your task is to process the output by performing a lossy compression that **strictly preserves factual data** while removing redundant noise.

**Your directive is to TRANSFORM the text, not SUMMARIZE it.**

### **CRITICAL RULES:**
1.  **Preserve:** All error codes, status messages, unique identifiers, file paths, URLs, key css styles, and any non-repetitive text.
2.  **Remove:** repetitive errors or warnings, as well as large blocks of minified code. Also remove any useless noise.
3.  **Condense:** Replace long, repetitive internal state objects (e.g., `self.__next_f.push([1, ...]`) with a clear placeholder like `<!-- [NEXT INTERNAL STATE...] -->` or `[Turbopack dev scripts truncated]`.
4.  **Do NOT** add external analysis, "Actionable" items, or guesses. Only reflect the content that is present in the output.
5.  The final output should be a shortened, yet still technical, version of the original text.

IMPORTANT: output ONLY the compressed text. Do NOT add any extra comment!

**Now, compress the following output:**

Output to compress:
{long_text}"""


def _invoke_llm_compresser(long_text: str, model: str) -> str:
    """
    Shrinks `long_text` with the OpenAI ChatCompletion API, returning
    a concise summary that highlights errors / stack-traces.
    """
    if len(long_text) > MAX_LOG_CHARS_BEFORE_SUMMARISE:
        try:
            prompt = get_frontend_message_compression_prompt(long_text)
            messages = [{"role": "system", "content": "You are an expert at compressing text."}, {"role": "user", "content": prompt}]
            response = vlm_generation(messages, model=model)
            compressed_text = response
        except Exception as e:
            print(f"Error during LLM compression: {str(e)}\n\nFalling to naive compression...")
            compressed_text = long_text[-MAX_LOG_CHARS_BEFORE_SUMMARISE:]
        is_compressed = True
    else:
        compressed_text = long_text
        is_compressed = False

    return compressed_text, is_compressed


def _attr(obj, name):
    """Return obj.<name>(); falling back to obj.<name> if it is a property."""
    val = getattr(obj, name)
    return val() if callable(val) else val


class WebAgentTester:
    """
    A tester class that automates website testing using Playwright with an agent loop.
    Maintains message history to form a trajectory for the VLM.
    """
    
    def __init__(self, 
        directory_path: str, 
        start_command: str, 
        required_ports: List[int],
        relative_url: str,
        instruction: str, 
        expected_result: str, 
        model: str, 
        log_dir: Optional[str] = None,
        max_img_num: int = 5,
        max_iterations: int = 20,
        height: int = 1440,
        width: int = 2560
    ):
        self.directory_path = directory_path
        self.start_command = start_command
        self.required_ports = required_ports
        self.instruction = instruction
        self.expected_result = expected_result
        self.model = model
        self.process: Optional[subprocess.Popen] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.iteration_count = 0
        self.max_iterations = max_iterations
        self.max_img_num = max_img_num
        self.messages = []  # Store conversation history
        self.service_output = ""  # Store service output for port detection
        self.detected_port = None  # Store detected port
        self.height = height
        self.width = width
        self.relative_url = relative_url
        self.error_messages = []
        self.console_entries: list[dict] = []
        self.javascript_errors: list[str] = []
        self.answer = None
        self.latest_elements: list[dict] = []
        self.action_error = ""
        
        self._last_llm_response: str | None = None
        self._same_response_streak: int = 0
        
        # Create logging directory
        if log_dir:
            self.log_dir = log_dir
            os.makedirs(self.log_dir, exist_ok=True)
        else:
            self.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(self.log_dir, exist_ok=True)

        self.log_file = os.path.join(self.log_dir, "frontend_service.log")  # Store log file path
        if os.path.exists(self.log_file):
            os.remove(self.log_file)
        print(f"Logs will be saved to: {self.log_file}")
        
        # Set up logging
        logging.basicConfig(
            filename=os.path.join(self.log_dir, "web_agent_tester.log"),
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
    def start_service(self) -> bool:
        """
        Start the user’s service inside a detached tmux session.

        Both STDOUT and STDERR are piped through `tee -a <log_file>` so that:
        • the pane keeps running,
        • the log file is created immediately, and
        • we can still see the live output in the tmux pane if we attach.
        """
        

        # ---------- 1. paths & logging -------------------------------------
        work_dir  = os.path.abspath(self.directory_path)
        log_path  = os.path.abspath(os.path.expanduser(self.log_file))

        # make sure parent dir exists and file is truncated
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("")          # touch & truncate

        # ---------- 2. unique tmux session ---------------------------------
        self.tmux_session = f"frontend-{int(time.time())}"

        # ---------- 3. launch inside tmux ----------------------------------
        try:
            server = libtmux.Server()
            if server.has_session(self.tmux_session):
                server.kill_session(self.tmux_session)

            session = server.new_session(
                session_name   = self.tmux_session,
                start_directory= work_dir,
                kill_session   = False,        # we handle duplicates above
                attach         = False,
            )
            pane = session.active_window.attached_pane   # new libtmux API

            # free requested ports
            for p in self.required_ports:
                print(kill_service_on_port(p))

            # Compose a shell command that:
            #   * runs the user command
            #   * redirects BOTH stdout & stderr
            #   * keeps the pane alive
            quoted_log = shlex.quote(log_path)
            pane.send_keys(
                f"bash -lc '( {self.start_command} ) 2>&1 | tee -a {quoted_log}'",
                enter=True,
                suppress_history=True,
            )

            # give the process a couple seconds to appear
            time.sleep(3)
            if not server.has_session(self.tmux_session):
                err = "Service failed to start (tmux session vanished)."
                self.error_messages.append({"type": "Start Service Error",
                                            "content": err})
                print(err)
                return False

            print(f"Service started in tmux session '{self.tmux_session}'.")
            return True

        except Exception as exc:
            err = f"Error starting service: {exc}"
            self.error_messages.append({"type": "Start Service Error",
                                        "content": err})
            print(err)
            return False

    def stop_service(self):
        """
        Gracefully terminate the tmux session created by `start_service`.
        """
        if not hasattr(self, "tmux_session"):
            print("No tmux_session recorded on this object.")

        try:
            server = libtmux.Server()
            if server.has_session(self.tmux_session):
                server.kill_session(self.tmux_session)
                print(f"Killed tmux session '{self.tmux_session}'.")
            else:
                print(f"No tmux session named '{self.tmux_session}' exists.")

            for p in self.required_ports:
                print(kill_service_on_port(p))

        except Exception as exc:
            print(f"Error stopping service: {exc}")
    
    def wait_for_url_in_log(self, timeout=60):
        """Wait for a URL to appear in the service log and extract the port."""
        print("Waiting for URL to appear in log...")
        url_pattern = re.compile(
            r"http://(?:localhost|(?:\d{1,3}\.){3}\d{1,3}):\d+/?"
        )
        deadline = time.time() + timeout
        url = None
        last_content = ""
        while time.time() < deadline:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    content = clean_console(content)
                    if url is None:
                        match = url_pattern.search(content)
                        if match:
                            url = match.group(0)
                            print(f"Found service URL: {url}")
                            # Extract port from URL
                            port_match = re.search(r":(\d+)", url)
                            if port_match:
                                self.detected_port = port_match.group(1)
                                print(f"Detected port: {self.detected_port}")
                    if content == last_content and url is not None:
                        return url
                    last_content = content
            time.sleep(1)
            
        if url is None:
            raise TimeoutError("Timed out waiting for service URL in log.")

        return url

    def _on_console(self, msg):
        loc = _safe_dict(_attr(msg, "location"))
        entry = {
            "type": _attr(msg, "type"),
            "text": _attr(msg, "text"),
            "url":  loc.get("url"),
            "line": loc.get("lineNumber"),
        }
        self.console_entries.append(entry)

    def _on_page_error(self, exc):
        loc = _safe_dict(getattr(exc, "location", {}))
        err_info = {
            "name":    getattr(exc, "name", None),
            "message": getattr(exc, "message", str(exc)),
            "stack":   getattr(exc, "stack", None),
            "url":     loc.get("url"),
            "line":    loc.get("lineNumber"),
            "column":  loc.get("columnNumber"),
        }
        self.javascript_errors.append(err_info)
    
    def initialize_browser(self):
        """Initialize Playwright browser."""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True)
            # Set a fixed viewport size for consistent screenshots
            self.context = self.browser.new_context(
                viewport={"width": self.width, "height": self.height}
            )
            self.page = self.context.new_page()
            self.page.on("console", self._on_console)
            self.page.on("pageerror", self._on_page_error)
            print("Browser initialized successfully")
        except Exception as e:
            error_message = f"Error initializing browser: {e}"
            print(error_message)
            self.error_messages.append({"type": "Browser Initialization Error", "content": error_message})
            raise
    
    def close_browser(self):
        """Close the browser and clean up Playwright resources."""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def _install_dom_version_counter(self) -> None:
        """
        Injects a MutationObserver that bumps window.__domVersion whenever the
        DOM changes.
        Only the *first* call actually injects; subsequent calls are no-ops.
        """
        self.page.evaluate(
            """
            () => {
                if (window.__domVersionObserver) return;      // already installed
                window.__domVersion = 0;
                window.__domVersionObserver = new MutationObserver(
                    () => window.__domVersion++
                );
                window.__domVersionObserver.observe(
                    document,
                    {subtree: true, childList: true,
                     attributes: true, characterData: true}
                );
            }
            """
        )

    # ----------------------------------------------------------------------------------
    def _wait_for_dom_idle(self,
                           idle_ms: int = DOM_IDLE_MS,
                           timeout_ms: int = DOM_TIMEOUT_MS) -> None:
        """
        Blocks until the DOM sees no mutations for `idle_ms` **and**
        one full paint has occurred. Raises if it never becomes idle.
        """
        self.page.evaluate(
            """
            ([idle, to]) => new Promise((resolve, reject) => {
                const start = performance.now();
                let lastMutation = performance.now();

                const obs = new MutationObserver(
                    () => lastMutation = performance.now()
                );
                obs.observe(document,
                            {subtree: true, childList: true,
                             attributes: true, characterData: true});

                function raf(cb){requestAnimationFrame(cb);}  // shorthand

                function check() {
                    if (performance.now() - lastMutation >= idle) {
                        obs.disconnect();
                        // double RAF ⇒ frame with these DOM changes is on screen
                        raf(()=>raf(resolve));
                        return;
                    }
                    if (performance.now() - start > to) {
                        obs.disconnect();
                        reject('DOM never became idle');
                        return;
                    }
                    raf(check);
                }
                check();
            })
            """,
            [idle_ms, timeout_ms],
        )

    # ----------------------------------------------------------------------------------
    def capture_screenshot_with_boxes(self) -> tuple[str, list]:
        """
        Atomically capture a screenshot + bounding boxes.
        Returns (base-64 PNG, list_of_elements)
        """
        self._install_dom_version_counter()

        self.page.set_viewport_size(
            {"width": self.width, "height": self.height}
        )

        screenshot_bytes: bytes | None = None   # initialise
        elements: list = []

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                time.sleep(0.2)

                # 1. wait for quiescent page
                self.page.wait_for_load_state(FAST_LOAD_STATE,
                                            timeout=FAST_LOAD_TIMEOUT)
                self._wait_for_dom_idle()

                # 2. atomic snapshot
                dom_before = self.page.evaluate("() => window.__domVersion")
                screenshot_bytes = self.page.screenshot(
                    clip={"x": 0, "y": 0,
                        "width": self.width, "height": self.height},
                )
                elements = get_interactive_elements(self.page)
                dom_after = self.page.evaluate("() => window.__domVersion")

                if dom_before == dom_after:
                    # success
                    img_b64, elements = self._annotate_and_encode(
                        screenshot_bytes, elements
                    )
                    self.latest_elements = elements
                    return img_b64, elements

            except Exception as e:
                print(f"[capture] attempt {attempt} failed: {e}")

        try:
            screenshot_bytes = self.page.screenshot(
                    clip={"x": 0, "y": 0,
                        "width": self.width, "height": self.height},
                )
            elements = get_interactive_elements(self.page)
            img_b64, elements = self._annotate_and_encode(screenshot_bytes, elements)
            self.latest_elements = elements
            return img_b64, elements
        except Exception as e:
            # All retries failed ─────────────────────────────────────────────────
            raise RuntimeError(
                f"Could not capture a stable screenshot after {MAX_RETRIES} attempts. Fallback to capture a screenshot anyway also failed: {e}"
            )

    # ----------------------------------------------------------------------------------
    def _annotate_and_encode(self, screenshot_bytes: bytes, elements: list
                             ) -> Tuple[str, list]:
        """
        Your original PIL drawing + base-64 encoding logic, extracted unchanged.
        """
        image = Image.open(io.BytesIO(screenshot_bytes))
        draw  = ImageDraw.Draw(image)
        font  = ImageFont.load_default()

        dash_len, gap_len = 5, 3
        label_size        = 15

        for el in elements:
            el_id = el["id"]
            for r in el["rects"]:
                # dashed rectangle
                for x0, y0, x1, y1 in (
                    (r["left"],  r["top"],    r["right"], r["top"]),     # top
                    (r["left"],  r["bottom"], r["right"], r["bottom"]),  # bottom
                    (r["left"],  r["top"],    r["left"],  r["bottom"]),  # left
                    (r["right"], r["top"],    r["right"], r["bottom"]),  # right
                ):
                    if x0 == x1:   # vertical
                        y = y0
                        while y < y1:
                            draw.line([x0, y, x1, min(y + dash_len, y1)],
                                      fill="black", width=2)
                            y += dash_len + gap_len
                    else:          # horizontal
                        x = x0
                        while x < x1:
                            draw.line([x, y0, min(x + dash_len, x1), y1],
                                      fill="black", width=2)
                            x += dash_len + gap_len

                # label square
                lx = max(0, r["left"])
                ly = max(0, r["top"] - label_size)
                draw.rectangle([lx, ly, lx + label_size, ly + label_size],
                               fill="black", outline="black")

                # center text
                w, h = draw.textbbox((0, 0), str(el_id), font=font)[2:]
                draw.text((lx + (label_size - w)//2, ly + (label_size - h)//2),
                          str(el_id), fill="white", font=font)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        # optional logging
        path = os.path.join(
            self.log_dir, f"screenshot_iter_{self.iteration_count}.png"
        )
        with open(path, "wb") as fh:
            fh.write(buf.getvalue())

        return img_b64, elements
    
    def execute_action(self, action: dict, *, timeout: int = 60_000) -> bool:
        """
        Execute one GUI-action produced by the LLM.
        Returns True on success; on failure sets self.action_error and returns False.
        """
        try:
            act = action.get("action")
            elems = self.latest_elements                       # cached snapshot

            # ---- CLICK -------------------------------------------------------- #
            if act == "click":
                idx = action.get("element", 0)
                if isinstance(idx, list) and len(idx) == 1:
                    idx = idx[0]
                if not _within(idx, elems):
                    self.action_error = f"Element {idx} not found"
                    return False

                el = elems[idx]["element"]                     # ElementHandle
                _wait_clickable(el, timeout)
                el.click(timeout=timeout)
                return True

            # ---- TYPE --------------------------------------------------------- #
            elif act == "type":
                idx     = action.get("element", 0)
                content = action.get("content", "")
                if not _within(idx, elems):
                    self.action_error = f"Element {idx} not found"
                    return False

                el = elems[idx]["element"]
                _wait_clickable(el, timeout)
                el.fill(content, timeout=timeout)
                el.press("Enter")
                return True

            # ---- SCROLL ------------------------------------------------------- #
            elif act == "scroll":
                target     = action.get("element", "WINDOW")
                direction  = action.get("direction", "down")
                delta      = -300 if direction == "up" else 300

                if target == "WINDOW":
                    self.page.mouse.wheel(0, delta)
                else:
                    if not _within(target, elems):
                        self.action_error = f"Target {target} not found"
                        return False
                    elems[target]["element"].scroll_into_view_if_needed()
                    self.page.mouse.wheel(0, delta)
                return True

            # ---- WAIT --------------------------------------------------------- #
            elif act == "wait":
                time.sleep(action.get("seconds", 5))
                return True

            # ---- HISTORY NAVIGATION ------------------------------------------- #
            elif act == "goback":
                self.page.go_back()
                return True

            # ---- ANSWER (terminate loop) -------------------------------------- #
            elif act == "answer":
                self.answer = action.get("content", "")
                print(f"Test answer: {self.answer}")
                return True

            # ---- DRAG --------------------------------------------------------- #
            elif act == "drag":
                x1, y1 = action.get("start", [0, 0])
                x2, y2 = action.get("end",   [0, 0])
                self.page.mouse.move(x1, y1)
                self.page.mouse.down()
                self.page.mouse.move(x2, y2)
                self.page.mouse.up()
                return True

            # ---- PRESS KEY ---------------------------------------------------- #
            elif act == "press":
                key = action.get("key")
                if not key:
                    self.action_error = "No key specified for press action"
                    return False
                self.page.keyboard.press(key)
                return True

            # ---- UNKNOWN ------------------------------------------------------ #
            else:
                self.action_error = f"Unknown action type: {act}"
                return False

        # ---------- Playwright-specific timeout --------------------------------- #
        except PWTimeout as e:
            self.action_error = f"Playwright timeout during {act}: {e}"
            return False

        # ---------- Any other unexpected error ---------------------------------- #
        except Exception as e:
            self.action_error = f"Error executing action {action}: {e}"
            return False

    def clip_message_and_obs(self):
        clipped_msg = []
        img_num = 0
        msg = self.messages
        max_img_num = self.max_img_num
        for idx in range(len(msg)):
            curr_msg = msg[len(msg) - 1 - idx]
            if curr_msg['role'] != 'user':
                clipped_msg = [curr_msg] + clipped_msg
            else:
                if type(curr_msg['content']) == str:
                    clipped_msg = [curr_msg] + clipped_msg
                elif img_num < max_img_num:
                    img_num += 1
                    clipped_msg = [curr_msg] + clipped_msg
                else:
                    curr_content = curr_msg['content'][0]['text'] + " Observation: A screenshot (Omitted in context)."
                    curr_msg_clip = {
                        'role': curr_msg['role'],
                        'content': curr_content
                    }
                    clipped_msg = [curr_msg_clip] + clipped_msg
        return clipped_msg
    
    def get_model_response(self, screenshot_b64: str, elements: List[Dict[str, Any]], previous_action: Optional[dict] = None) -> dict:
        """
        Send the screenshot and task to a multimodal model with conversation history.
        """
        # Format element information
        element_info = build_format_ele_text(elements)

        img_path = os.path.join(
            self.log_dir, f"screenshot_iter_{self.iteration_count}.png"
        )
        img_info = ""
        if os.path.isfile(img_path):
            img_info = most_used_colors(img_path)
        
        # Build the prompt with trajectory context
        if self.iteration_count == 1:
            # First iteration - initial prompt
            system_prompt = f"""
Imagine you are a robot browsing the web, just like humans. Now you need to complete a task. In each iteration, you will receive an Observation that includes a screenshot of a webpage and some texts. This screenshot will feature Numerical Labels placed in the TOP LEFT corner of each Web Element.
Carefully analyze the visual information to identify the Numerical Label corresponding to the Web Element that requires interaction, then follow the guidelines and choose one of the following actions:
1. Click a Web Element.
2. Delete existing content in a textbox and then type content. 
3. Scroll up or down. Multiple scrolls are allowed to browse the webpage. Pay attention!! The default scroll is the whole window. If the scroll widget is located in a certain area of the webpage, then you have to specify a Web Element in that area. I would hover the mouse there and then scroll.
4. Wait. Typically used to wait for unfinished webpage processes, with a duration of 5 seconds.
5. Go back, returning to the previous webpage.
6. Drag an element from one position to another.
7. Press a key on the keyboard.
8. Answer. This action should only be chosen when all questions in the task have been solved.

Correspondingly, Action should be returned as a JSON object with the following format:
- For Click: {{"action": "click", "element": Numerical_Label}}
- For Type: {{"action": "type", "element": Numerical_Label, "content": "text to type"}}
- For Scroll: {{"action": "scroll", "element": "Numerical_Label_or_WINDOW", "direction": "up_or_down"}}
- For Wait: {{"action": "wait"}}
- For GoBack: {{"action": "goback"}}
- For Drag: {{"action": "drag", "start": [x1, y1], "end": [x2, y2]}}
- For Press: {{"action": "press", "key": Any_Key_on_Keyboard}}
- For Answer: {{"action": "answer", "content": "your answer"}}

Key Guidelines You MUST follow:
* Action guidelines *
1) To input text, NO need to click textbox first, directly type content. After typing, the system automatically hits `ENTER` key. Sometimes you should click the search button to apply search filters. Try to use simple language when searching.
2) You must Distinguish between textbox and search button, don't type content into the button! If no textbox is found, you may need to click the search button first before the textbox is displayed. 
3) Execute only one action per iteration. 
4) STRICTLY Avoid repeating the same action if the webpage remains unchanged. You may have selected the wrong web element or numerical label. Continuous use of the Wait is also NOT allowed.
5) When a complex Task involves multiple questions or steps, select "answer" only at the very end, after addressing all of these questions (steps). Flexibly combine your own abilities with the information in the web page. Double check the formatting requirements in the task when "answer".
6) For Drag actions, you must specify exact pixel coordinates for both the starting point and the ending point. The coordinates should be within the bounds of the screenshot (0-{self.width-1} for x-axis, 0-{self.height-1} for y-axis).
7) For Press actions, you can send any key that can be pressed on the keyboard. This includes letters, numbers, special characters, and function keys. Examples: "a", "Enter", "Tab", "Escape", "ArrowUp", "F5", etc. 

* Web Browsing Guidelines *
1) Don't interact with useless web elements like Login, Sign-in, donation that appear in Webpages. Pay attention to Key Web Elements like search textbox and menu.
2) Visit video websites like YouTube is allowed BUT you can't play videos. Clicking to download PDF or other document formats0o is allowed and will be analyzed by the Assistant API.
3) Focus on the numerical labels in the TOP LEFT corner of each rectangle (element). Ensure you don't mix them up with other numbers (e.g. Calendar) on the page.
4) Focus on the date in task, you must look for results that match the date. It may be necessary to find the correct year, month and day at calendar.
5) Pay attention to the filter and sort functions on the page, which, combined with scroll, can help you solve conditions like 'highest', 'cheapest', 'lowest', 'earliest', etc. Try your best to find the answer that best fits the task.
6) Don't use GoBack as the first action in the trajectory. That would result in an empty page as the initially loaded page has nothing to go back to.

Your reply should be a single JSON object with two keys:
1. "thought": "Your brief thoughts (briefly summarize the info that will help ANSWER)"
2. "action": {{"action": "action_name", ...}}  // The action object as specified above

Example response format:
{{"thought": "I need to click the 'Click Me' button which is labeled as [0]", "action": {{"action": "click", "element": 0}}}}

Then the User will provide:
Observation: [A labeled screenshot Given by User]"""

            user_prompt = f"Now given a task:\n\n{self.instruction}\n\nPlease interact with {self.url} and get the answer.\nObservation: please analyze the attached screenshot and give the thought and action. I've provided the tag name of each element and the text it contains (if text exists). Note that <textarea> or <input> may be textbox, but not exactly. Please focus more on the screenshot and then refer to the textual information.\n{element_info}{img_info}"
            
            # Initialize messages
            self.messages = [{
                "role": "system",
                "content": system_prompt
            }, {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
                ]
            }]
        else:
            # Subsequent iterations - add observation and new screenshot
            if len(self.action_error) > 0:
                previous_error_msg = f"An error ocurred in the previous section: {self.action_error.strip()}\nThe action you have chosen cannot be executed. Please double-check if you have selected the wrong numerical label or action or action format. Then provide the revised thought and action.\n\n"
            else:
                previous_error_msg = ""
            user_prompt = f"{previous_error_msg}Observation: please analyze the attached screenshot and give the thought and action. I've provided the tag name of each element and the text it contains (if text exists). Note that <textarea> or <input> may be textbox, but not exactly. Please focus more on the screenshot and then refer to the textual information.\n{element_info}{img_info}"
            
            self.messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
                ]
            })
        
        try:
            # Clip messages to limit image count in context
            self.messages = self.clip_message_and_obs()

            # Get response from VLM with full conversation history
            response_text = vlm_generation(self.messages, model=self.model)
            print(f"Model response: {response_text}")

            if response_text == self._last_llm_response:
                self._same_response_streak += 1
            else:
                self._same_response_streak = 0
            self._last_llm_response = response_text

            if self._same_response_streak >= REPEAT_MAX:
                print(
                    f"[Loop-guard] Detected {self._same_response_streak + 1} "
                    "identical LLM replies → injecting nudge prompt."
                )
                # add a meta-prompt and try once more
                self.messages.append(
                    {"role": "user", "content": LOOP_NUDGE}
                )
                response_text = vlm_generation(self.messages, model=self.model)
                # reset streak so the guard can trigger again later
                self._same_response_streak = 0
                self._last_llm_response = response_text
                print(f"Model response (after nudge): {response_text}")

            # Add assistant response
            self.messages.append({
                "role": "assistant",
                "content": response_text
            })
            
            # Save messages and response
            messages_path = os.path.join(self.log_dir, f"messages_iter_{self.iteration_count}.json")
            with open(messages_path, "w") as f:
                json.dump(scrub_images(self.messages), f, indent=2)
            
            response_path = os.path.join(self.log_dir, f"response_iter_{self.iteration_count}.txt")
            with open(response_path, "w") as f:
                f.write(response_text)

            # Parse JSON response
            try:
                response_json = json.loads(response_text)
                return response_json.get("action", {"action": "wait"})
            except json.JSONDecodeError:
                # Try to extract JSON from response
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        response_json = json.loads(json_match.group())
                        return response_json.get("action", {"action": "wait"})
                    except:
                        pass
                return {"action": "wait"}
                
        except Exception as e:
            print(f"Error getting model response: {e}")
            return {"action": "wait"}
    
    def agent_loop(self, is_eval=False) -> bool:
        """
        Run the agent loop with trajectory history.
        """
        self.iteration_count = 0
        previous_action = None
        
        while self.iteration_count < self.max_iterations:
            self.iteration_count += 1
            print(f"--- Iteration {self.iteration_count} ---")
            
            # Capture screenshot with bounding boxes
            screenshot_b64, elements = self.capture_screenshot_with_boxes()
            
            # Get action from model with trajectory context
            action = self.get_model_response(screenshot_b64, elements, previous_action)
            
            if action.get("action") == "answer":
                print("Task completed successfully")
                self.answer = action.get("content")
                return True
                
            # Execute the action
            success = self.execute_action(action)
            previous_action = action  # Store for next iteration

            # In test mode, return as soon as error is detected
            if self.detect_error_message() and not is_eval:
                return False
            
            if not success:
                err_msg = f"Failed to execute action: {action}\n\n{self.action_error}"
                self.action_error = f"Failed to execute action: {action}\n\n{self.action_error}"
                print(err_msg)
                if ("ElementHandle.wait_for_element_state" in err_msg):
                    err_msg += "\nThe element is unresponsive. This might be because it's logic is implemented incorrectly. In this case, check and fix the logic. It can also be because the element would only be activated after certain operations. In this case, modify the UI to make the workflow clearer, or hide the element until it is activated, so that the user can better understand."
                elif ("ElementHandle.fill: Error: Element is not an <input>, <textarea>, <select> or [contenteditable] and does not have a role allowing [aria-readonly]" in err_msg):
                    err_msg += "\nThe element is not a text input box and cannot be filled with text input. This might be because it's logic is implemented incorrectly. In this case, check and fix the logic. It can also be because the GUI agent selected the wrong element to input the text. This might be caused by failing to correctly implement the element that actually takes the text filling, or that the element functionalities are not obvious enough for the user and GUI agent to understand the correct course of action. Check the components that are related to this function and make their appearance clear and easy to understand."
                    
                self.error_messages.append({"type": "Action Error", "content": err_msg})
                if not is_eval:
                    return False
                
            # Wait for action to take effect
            time.sleep(5)
            
        err_msg = "Maximum iterations reached, stopping agent loop"
        print(err_msg)
        self.error_messages.append({"type": "Reach Iteration Limit Error", "content": err_msg})
        return False

    def detect_error_message(self) -> bool:
        """
        Scan the combined console log for the word 'error' (case-insensitive).
        NEVER raises FileNotFoundError because we touch() the file up-front.
        """
        has_error = False

        # log file always exists, but double-check anyway
        if os.path.exists(self.log_file):
            with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
                content = clean_console(f.read())

            if "error:" in content.lower():
                # ─── keep only entries that are NOT "Console Error" ──▶
                self.error_messages = [
                    m for m in self.error_messages if m.get("type") != "Console Error"
                ]
                # add the newest console error
                self.error_messages.append({
                    "type": "Console Error",
                    "content": content
                })
                has_error = True

        for e in self.console_entries:
            if e["type"] == "error":
                if "A param property was accessed directly with `params.id`. `params` is now a Promise and should be unwrapped with `React.use()` before accessing properties of the underlying params object. In this version of Next.js direct access to param properties is still supported to facilitate migration but in a future version you will be required to unwrap `params` with `React.use()`." in str(e):
                    error_content = str(e) + """
Suggested Fix: You should search for direct property accesses such as `params.id`, and unwrap the promise first. For example:
```
import { use } from 'react';

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  // React.use waits for the promise during SSR and returns the real object
  const { id } = use(params);

  return <h1>Product {id}</h1>;
}
```
Or make the component itself async and await the params. For example:
```
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <h1>Product {id}</h1>;
}
```
The code blocks are demonstrative only. You should adapt them to the current codebase."""
                self.error_messages.append(
                    {"type": "Browser Console Error", "content": str(e)}
                )
                has_error = True

        if self.javascript_errors:
            for e in self.javascript_errors:
                lines = [
                    f"{e.get('name')}: {e.get('message')}",
                    f"    at {e.get('url')}:{e.get('line')}:{e.get('column')}" if e.get("url") else "",
                    e.get("stack") or ""
                ]
                self.error_messages.append({
                    "type": "Uncaught JS Error",
                    "content": "\n".join(filter(bool, lines))
                })
            self.javascript_errors.clear()
            has_error = True

        # clear buffers so we don’t report the same error again
        self.console_entries.clear()
        self.javascript_errors.clear()

        return has_error
    
    def generate_result(self, state: str) -> dict:
        """
        Validate the test result against the expected outcome.
        """
        error_messages_text = ""
        contain_console_error = False
        grouped_error_messages = []
        for error_message in self.error_messages:
            if error_message['type'] == "Console Error":
                contain_console_error = True

            for e in grouped_error_messages:
                if (e['type'], e['content']) == (error_message['type'], error_message['content']):
                    e['count'] += 1
                    break
            else:
                grouped_error_messages.append(
                    {"type": error_message["type"],
                    "content": error_message["content"],
                    "count": 1}
                )
        
        for error_message in grouped_error_messages:
            content, is_compressed = _invoke_llm_compresser(error_message['content'], self.model)
            count_text = '' if error_message['count'] == 1 else f' x {error_message["count"]}'
            error_messages_text += f"--- {error_message['type']}{count_text}{' (Compressed)' if is_compressed else ''} ---\n{content.strip()}\n\n"

        log_content_text = None
        if not contain_console_error and os.path.exists(self.log_file):
            with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
                log_content = clean_console(f.read())
            log_content, is_compressed = _invoke_llm_compresser(log_content, self.model)
            log_content_text = f"--- Console Output{' (Compressed)' if is_compressed else ''} ---\n{log_content.strip()}\n\n"

        prefix_map = {
            "page_loading": "Error(s) occurred while the site was loading its initial page.",
            "waiting_url": "Error(s) occurred while waiting for the service to print its address/port/URL.",
            "initializing_browser": "Error(s) occurred while launching or attaching the browser instance.",
            "starting_service": "Error(s) occurred while starting the service.",
            "execution_error": "Error(s) occurred in the tester execution.",
        }

        if state in prefix_map.keys():
            preamble = prefix_map.get(state, "")
            llm_content = f"{preamble} The error message(s) are as follows:\n\n--- Error Log Excerpts ---\n\n {error_messages_text.strip()}"
            if log_content_text is not None:
                llm_content += "\n\n" + log_content_text.strip()

        elif state == "agent_started":
            # build error-log block or a placeholder
            log_block = (
                error_messages_text.strip()
                if error_messages_text.strip()
                else "[No console or server errors were captured]"
            )
            if len(error_messages_text.strip()) == 0:
                prefix = "The above GUI agent testing finished without encountering any runtime errors."
                error_description_prompt = "Look carefully at the agent actions and website responses. Point out any incorrect reactions you observed and their triggering action. Observe any problems in layout or texts in the webpage screenshots. Observe unreasonable numbers such as N/A or zeros. If you find no problem problem in the agent trajectory, write “None observed”."
                function_score_prompt = """Evaluate the results of the GUI-agent test run and assign **one integer grade from 1 to 5** to reflect the functionality of the website:
   * 1: The vast majority of tested functions fail or behave incorrectly.
   * 2: Many functions fail; only a few behave as expected.
   * 3: About half of the functions work as expected; success is mixed.
   * 4: Most functions work as expected; only minor issues remain.
   * 5: All tested functions work exactly as expected; no issues observed."""
            else:
                prefix = f"The above GUI agent testing is prematurely terminated after encountering the following runtime error(s):\n\nError Logs:\n---\n{log_block}\n---"
                error_description_prompt = "Analyze the error logs and report any runtime errors or unexpected behaviours, as well as what action(s) triggered the errors or misbehaviour of the website. Point out what action(s) triggered each of the errors in the error logs; Also point out any incorrect reactions from the website and their triggering action(s). Observe any problems in layout or texts in the webpage screenshots. Observe unreasonable numbers such as N/A or zeros."
                function_score_prompt = """Evaluate the results of the GUI-agent test run and assign **one integer grade from 1 to 5** to reflect the functionality of the website:
   * 1: The vast majority of functions fail, behave incorrectly, or are not tested before the agent is terminated.
   * 2: Many functions fail or are not tested before the agent is terminated; only a few behave as expected.
   * 3: About half of the functions are tested and work as expected; success is mixed.
   * 4: Most functions work are tested and work as expected; only minor issues remain.
   * 5: All functions are tested and work exactly as expected; no issues observed."""

            summary_prompt = f"""{prefix}

Write a concise report of the GUI-agent testing process containing **exactly five sections in the order shown below**.  Begin each section with its title followed by a colon, then a single space, then the content of that section.  Do not add any other text (no explanations before or after the five sections).

1. GUI Agent Trajectory Description: Describe what the agent did in each step and how the web page responded (state changes, new elements appearing, navigation, etc.).

2. Errors / Misbehaviour and Triggering Actions: {error_description_prompt}

3. GUI Agent Testing Score: {function_score_prompt}

4. Website Visual Description: Describe the overall layout and colour palette of all the pages you observed in the agent trajectory. Use a "- [Page Name]: [Description]; [Color Theme] [Suggestion (if any)]" format. Consider the following perspectives:
  - Successful Rendering: Does the webpage render correctly without visual errors? Are colors, fonts, and components displayed correctly? Or is the pager empty or "Not Found"?
  - Layout Harmony: Is the arrangement of components (text, images, buttons) balanced, intuitive, and clutter-free? Are css effects correctly rendered? (Sometimes, a white background, black text, gray buttons, and abnormally large icons may suggest problems in css rendering)
  - Color Theme: What is the dominant background color? What are the primary and secondary colors used for texts, buttons, and highlights? Describe the color of the background and components (e.g. "white background, black text, gray buttons").
  - Theme consistency: Do all the pages have consistent color theme? Note pages that have inconsistent theme.
  - Content consistency: Do all the pages have consistent and relevant content? In particular, note words like "Build Modern Web Applications with Ease", "Backend", or "Frontend", which might suggest parts of the original template that have not been fixed with the relevant content. 
  - Contrastive Coloring: Are the texts and buttons clearly visible against their background? Their color should NOT be the same or similar to their background. If a button or space looks empty, it is possibly because of this as well. Idealy the color of texts and components should be opposite of the background. You should point out any texts or components that present this problem and make suggesetions on how to adjust them.
  - Layout correctness: Are the components in the correct position? For example, is the search box at the top of the page? Is the menu on the left or at the top? Is the footer at the bottom? Is the header correctly on the top of the page and is not mistakenly duplicated? If not, suggest how to fix it. 
  - Content correctness: Are the content of each page reasonable? For example, are the numbers and texts reasonable, or are they placeholders like N/A or zeros?
  - Modernness & Beauty: Does the design follow contemporary trends? Are colors, typography, and visual hierarchy aesthetically pleasing?
IMPORTANT: The description of each page must cover all of the above aspects. Inspect the screenshots of the webpages carefully and observe any possible problems. Suggest ways to fix the problem in the suggestions.

5. Appearance Grade: Grade the webpage's appearance on a scale of 1 to 5 (5 being highest). Grading Scale:
  - 1 (Poor): Major rendering issues (e.g., broken layouts, incorrect colors, blank pages). Content is irrelevant or missing. Layout is chaotic. Design is outdated or visually unappealing.
  - 2 (Below Average): Partial rendering with noticeable errors. Content is partially relevant but poorly organized. Layout lacks consistency. Design is basic or uninspired.
  - 3 (Average): Mostly rendered correctly with minor flaws. Content is relevant but lacks polish. Layout is functional but unremarkable. Design is clean but lacks modern flair.
  - 4 (Good): Rendered well with no major errors. Content is relevant and logically organized. Layout is harmonious and user-friendly. Design is modern and visually appealing.
  - 5 (Excellent): Flawless rendering. Content is highly relevant, intuitive, and tailored to user needs. Layout is polished, responsive, and innovative. Design is cutting-edge, beautiful, and memorable.

Rules
-----
- Keep each section comprehensive, clear, and concise.  
- Do NOT mention numeric element labels or indices of the components; refer to components by their textual role (e.g. "the 'Start Now' button").  
- Output only the five sections. Do NOT make any extra commentary.
""".strip()

            self.messages.append({
                "role": "user",
                "content": summary_prompt
            })

            response_text = vlm_generation(self.messages, model=self.model)

            llm_content = f"--- GUI-agent Testing Summary ---\n\n{response_text.strip()}"
            if len(error_messages_text.strip()) > 0:
                llm_content += f"\n\n--- Error Log Excerpts ---\n\n{error_messages_text.strip()}"
            if log_content_text is not None:
                llm_content += "\n\n" + log_content_text.strip()
            llm_content += "\n\nSystem Instruction: Fix any errors revealed in the GUI-agent testing. Do NOT stop until all the errors have been fixed!\n\nAlso, carefully compare the website reaction and the webpage appearance with the requirements in the user instruction. Fix anything that does not fit the user instruction, such as the color of the background and components. Do NOT stop untill everything satisties the user instruction!\n\nIf there is a connection error, do not assume timing errors in the testing tool. Check your code for problems such as data structure inconsistencies and API endpoint inconsistencies instead!"

        result = {
            "llmContent": llm_content,
            "returnDisplay": llm_content[:500],
            "errorMessages": self.error_messages,
            "messages": scrub_images(self.messages)
        }

        with open(os.path.join(self.log_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4)
        return result
    
    def run_test(self) -> bool:
        """
        Run the complete test sequence.
        """
        service_started = False
        browser_initialized = False
        
        try:
            # Start the service
            service_started = self.start_service()
            if not service_started:
                self.detect_error_message()
                return self.generate_result("starting_service")
            
            if self.detect_error_message():
                return self.generate_result("starting_service")

            # Wait for URL and detect port
            try:
                self.url = self.wait_for_url_in_log()
                print(f"Service is running at: {self.url}")
            except TimeoutError as e:
                error_message = f"Error detecting service URL: {e}"
                print(error_message)
                self.error_messages.append({"type": "URL Detection Error", "content": error_message})
                self.detect_error_message()
                return self.generate_result("waiting_url")

            if self.detect_error_message():
                return self.generate_result("waiting_url")

            time.sleep(30)
            
            self.url += self.relative_url
            # Initialize browser
            self.initialize_browser()
            browser_initialized = True

            if self.detect_error_message():
                return self.generate_result("initializing_browser")
            
            # Navigate to the detected URL
            print(f"Navigating to {self.url}")
            self.page.goto(self.url, wait_until=FAST_LOAD_STATE, timeout=FAST_LOAD_TIMEOUT)
            
            # Wait for page to load
            self.page.wait_for_load_state(FAST_LOAD_STATE, timeout=FAST_LOAD_TIMEOUT)
            time.sleep(15)

            if self.detect_error_message():
                return self.generate_result("page_loading")
            
            # Run the agent loop
            agent_success = self.agent_loop(is_eval=False)
            if not agent_success:
                self.detect_error_message()
                return self.generate_result("agent_started")
            
            self.detect_error_message()
            return self.generate_result("agent_started")
            
        except Exception as e:
            error_message = f"Error during test execution: {e}"
            print(error_message)
            self.error_messages.append({"type": "Tester Execution Error", "content": error_message})
            return self.generate_result("execution_error")
            
        finally:
            # Cleanup
            if browser_initialized:
                self.close_browser()
            if service_started:
                self.stop_service()

    def judge_result(self) -> str:
        ui_limit_prompt_template = (
            "You have reached the maximum number of allowed interactions with the website.\n\n"
            "Please evaluate the outcome of your attempts based on the expected result:\n\n"
            "Expected Result: {expected_result}\n\n"
            "Now, answer with one of the following:\n"
            "- YES: if the expected result was fully achieved during your interactions.\n"
            "- NO: if the expected result was not achieved at all.\n"
            "- PARTIAL: if the expected result was only partially achieved.\n\n"
            "Provide your final answer based on your testing experience."
        )
        result = {"result": "NO", "final_response": ""}
        if len(self.messages) <= 1:
            result["result"] = "NO"
        else:
            if self.answer is not None:
                result["final_response"] = self.answer
                if "YES" in self.answer:
                    result["result"] = "YES"
                elif "PARTIAL" in self.answer:
                    result["result"] = "PARTIAL"
                else:
                    result["result"] = "NO"
            else:
                try:
                    self.messages.append({
                        "role": "user",
                        "content": ui_limit_prompt_template.format(expected_result=self.expected_result)
                    })
                    response = vlm_generation(self.messages, model=self.model)
                    result["final_response"] = response
                    if "YES" in response:
                        result["result"] = "YES"
                    elif "PARTIAL" in response:
                        result["result"] = "PARTIAL"
                    else:
                        result["result"] = "NO"
                except:
                    result["result"] = "NO"

        with open(os.path.join(self.log_dir, "finished.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4)

        return result

    def run_eval(self) -> bool:
        """
        Run the eval task
        """
        self.instruction = f"""

Task: {self.instruction}

Expected Result: {self.expected_result}

Instructions:
- Attempt the task as a user would, using the UI elements available.
- Make multiple attempts if needed to try and achieve the expected result.
- Observe whether the expected result is fully, partially, or not at all achieved.
- IMPORTANT: You can at most interact with the website 15 times. If the limit is reached, directly output your answer.
- If prompted for a username, password, or email in the process of testing, enter "superadmin@example.com", "admin123", and "superadmin@example.com", respectively.

At the end of your testing, answer only with one of the following:
- YES: if the expected result was fully achieved.
- NO: if the expected result could not be achieved at all.
- PARTIAL: if only some aspects of the expected result were achieved.

"""
        service_started = False
        browser_initialized = False
        
        try:
            # Start the service
            service_started = self.start_service()
            if not service_started:
                return self.judge_result()

            # Wait for URL and detect port
            try:
                self.url = self.wait_for_url_in_log()
                print(f"Service is running at: {self.url}")
            except TimeoutError as e:
                error_message = f"Error detecting service URL: {e}"
                print(error_message)
                self.error_messages.append({"type": "URL Detection Error", "content": error_message})
                return self.judge_result()
            
            self.url += self.relative_url
            # Initialize browser
            self.initialize_browser()
            browser_initialized = True
            
            # Navigate to the detected URL
            print(f"Navigating to {self.url}")
            self.page.goto(self.url, wait_until=FAST_LOAD_STATE, timeout=FAST_LOAD_TIMEOUT)
            
            # Wait for page to load
            self.page.wait_for_load_state(FAST_LOAD_STATE, timeout=FAST_LOAD_TIMEOUT)
            time.sleep(15)
            
            # Run the agent loop
            agent_success = self.agent_loop(is_eval=True)
            if not agent_success:
                return self.judge_result()
            
            return self.judge_result()
            
        except Exception as e:
            print(f"Error during test execution: {e}")
            return self.judge_result()
            
        finally:
            # Cleanup
            if browser_initialized:
                self.close_browser()
            if service_started:
                self.stop_service()


def main():
    # Get the current directory
    # directory_path = "/mnt/cache/agent/Zimu/WebGen-Agent/workspaces_root/WebGenAgentV3_WebGen-Bench_Qwen3-Coder-480B-A35B-Instruct_iter20_select_best/000013"
    directory_path = "/mnt/cache/agent/Zimu/WebGen-Agent2/workspaces_root/model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-400_compress-0.5_val-1_sum-5_v7_planned-testing/000040"
    # Create a tester instance
    width = 1600
    height = 1200
    tester = WebAgentTester(
        directory_path=directory_path,
        start_command="npm run dev",
        required_ports=[3004, 3006],
        relative_url="",
        instruction="Test the e-commerce functionality by attempting to purchase a service.",
        expected_result="",
        log_dir=f"{directory_path}/debug{width}x{height}_1",
        model="/mnt/cache/k12_data/models/Qwen/Qwen2.5-VL-32B-Instruct",
        width=width,
        height=height,
    )
    
    # Run the test
    print("Starting web agent test...")
    result = tester.run_test()
    print("-------------- LLM Content Start --------------\n\n" + result["llmContent"] + "\n\n-------------- LLM Content End --------------")

if __name__ == "__main__":
    main()