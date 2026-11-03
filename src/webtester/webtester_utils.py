import subprocess
import re
import time
import os
import copy

from typing import List, Dict, Any, Set, Union
from playwright.sync_api import Page, ElementHandle


def kill_service_on_port(port):
    """
    Finds the process running on the specified port and terminates it.

    Args:
        port (int): The port number to check and terminate the corresponding process.

    Returns:
        str: A message indicating the result of the operation.
    """
    try:
        # Run the `ss` command to find the process using the specified port
        cmd = f"ss -tulnp | grep :{port}"
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
        
        if result.returncode != 0 or not result.stdout.strip():
            return f"No process found running on port {port}."
        
        # Extract the process ID (PID) from the output
        output = result.stdout.strip()
        pid_start = output.find("pid=")
        if pid_start == -1:
            return f"Could not find the PID for port {port} in the output: {output}"
        
        pid_start += len("pid=")
        pid_end = output.find(",", pid_start)
        pid = output[pid_start:pid_end].strip()
        
        # Kill the process
        os.kill(int(pid), 9)  # Signal 9 is SIGKILL
        return f"Successfully terminated the process with PID {pid} running on port {port}."
    
    except ValueError as ve:
        return f"Error parsing PID: {ve}"
    except PermissionError:
        return "Permission denied. Please run this script with sudo or as root."
    except Exception as e:
        return f"An error occurred: {e}"


def get_interactive_elements(page: Page,
                             *,
                             min_area: int = 20) -> List[Dict[str, Any]]:
    """
    Replicates the `get_web_element_rect` algorithm *without* drawing any
    overlay.  
    Returned list ≃
        {
          id:         int,
          rects:      [ {left, top, right, bottom, width, height}, … ],
          text:       str,
          tag:        str,
          type:       str,
          ariaLabel:  str,
          element:    ElementHandle            # <-- live handle
        }
    """

    # ------------------------------------------------------------------
    # 1.  JavaScript that builds the filtered list of DOM nodes
    # ------------------------------------------------------------------
    js_collect = f"""
    (minArea) => {{

        // -------------------------------------------------------------
        // helpers
        // -------------------------------------------------------------
        const include = (el) => {{
            const tag = el.tagName;
            const gs  = window.getComputedStyle(el);
            return (
                tag === "INPUT"   || tag === "TEXTAREA"   || tag === "SELECT"  ||
                tag === "BUTTON"  || tag === "A"          || el.onclick != null ||
                gs.cursor === "pointer"                   ||
                tag === "IFRAME"  || tag === "VIDEO"      ||
                tag === "LI"      || tag === "TD"         || tag === "OPTION"
            );
        }};

        const viewportW = Math.max(document.documentElement.clientWidth,  window.innerWidth  || 0);
        const viewportH = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);

        // -------------------------------------------------------------
        // 1-a  build initial candidates with area ≥ minArea
        // -------------------------------------------------------------
        let items = Array.from(document.querySelectorAll('*')).filter(el => {{
            if (!include(el)) return false;

            // clip every client-rect to viewport, then sum area
            const rects = Array.from(el.getClientRects()).map(r => {{
                const left   = Math.max(0, r.left);
                const top    = Math.max(0, r.top);
                const right  = Math.min(viewportW,  r.right);
                const bottom = Math.min(viewportH,  r.bottom);
                return {{ left, top, right, bottom,
                          width:  right - left,
                          height: bottom - top }};
            }});

            const area = rects.reduce((a, bb) => a + bb.width * bb.height, 0);
            el.__ai_rects = rects;       // stash for later
            return area >= minArea;
        }});

        // -------------------------------------------------------------
        // 1-b  keep only *inner* clickable elements
        // -------------------------------------------------------------
        const buttonLikeSel = 'button, a, input[type="button"], div[role="button"]';
        const isButtonLike  = el => el.matches(buttonLikeSel);

        // drop elements that are inside another kept button-like element
        items = items.filter(el =>
            !items.some(other => other !== el && isButtonLike(other) && other.contains(el))
        );

        // special “role=…” span wrapper case
        items = items.filter(el => !(
            el.parentNode &&
            el.parentNode.tagName === 'SPAN' &&
            el.parentNode.children.length === 1 &&
            el.parentNode.getAttribute('role') &&
            items.includes(el.parentNode)
        ));

        // generic de-dup: prefer leaf over ancestor
        items = items.filter(el =>
            !items.some(other => other !== el && el.contains(other))
        );

        return items;   // an array of actual Element nodes
    }}
    """

    # ------------------------------------------------------------------
    # 2.  Run the JS in every frame and collect ElementHandles
    # ------------------------------------------------------------------
    handles: List[ElementHandle] = []
    for frame in page.frames:
        try:
            arr_handle = frame.evaluate_handle(js_collect, min_area)
            count      = arr_handle.evaluate("a => a.length")
            for i in range(count):
                h = arr_handle.evaluate_handle("(a,i) => a[i]", i).as_element()
                handles.append(h)
        except Exception:
            # iframe may disappear between enumerate-and-iterate
            continue

    # ------------------------------------------------------------------
    # 3.  Build the Python-side objects – one per ElementHandle
    # ------------------------------------------------------------------
    elements: List[Dict[str, Any]] = []

    def _rects_for(el: ElementHandle):
        return el.evaluate("""
            (node) => {
                const vw = Math.max(document.documentElement.clientWidth,  window.innerWidth  || 0);
                const vh = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);
                return Array.from(node.getClientRects()).map(bb => {
                    const left   = Math.max(0, bb.left);
                    const top    = Math.max(0, bb.top);
                    const right  = Math.min(vw, bb.right);
                    const bottom = Math.min(vh, bb.bottom);
                    return {
                        left, top, right, bottom,
                        width:  right - left,
                        height: bottom - top
                    };
                });
            }
        """)

    for idx, el in enumerate(handles):
        try:
            elements.append(
                {
                    "id":         idx,
                    "rects":      _rects_for(el),
                    "text":       (el.text_content() or "").strip().replace("\n", " "),
                    "tag":        el.evaluate("n => n.tagName.toLowerCase()"),
                    "type":       el.get_attribute("type")       or "",
                    "ariaLabel":  el.get_attribute("aria-label") or "",
                    "element":    el,
                }
            )
        except Exception:
            # element might have detached between JS and here
            continue

    return elements


def build_format_ele_text(elements: List[Dict[str, Any]]) -> str:
    """
    Parameters
    ----------
    elements : List[Dict]
        The list produced by `get_interactive_elements`.

    Returns
    -------
    str
        A single string that contains one “label” per element, separated
        by TAB characters, e.g.

            [0]: "Sign in";  [1]: <input> "Email";
    """

    input_attr_types = {"text", "search", "password", "email", "tel"}
    button_attr_types = {"submit", "button"}

    parts: List[str] = []

    for idx, item in enumerate(elements):
        text = (item["text"] or "").strip()
        tag  = (item["tag"] or "").lower()
        typ  = (item["type"] or "").lower()
        aria = (item["ariaLabel"] or "").strip()

        # ------------------------------------------------------------------
        # 1.  elements with *no* visible text
        # ------------------------------------------------------------------
        if not text:
            if (
                (tag == "input" and typ in input_attr_types)
                or tag == "textarea"
                or (tag == "button" and typ in button_attr_types)
            ):
                if aria:
                    parts.append(f"[{idx}]: <{tag}> \"{aria}\";")
                else:
                    parts.append(f"[{idx}]: <{tag}> \"{text}\";")
            continue  # nothing else to say for empty-text nodes

        # ------------------------------------------------------------------
        # 2.  elements whose text is present but short enough
        # ------------------------------------------------------------------
        if len(text) < 200 and not ("<img" in text and "src=" in text):
            if tag in {"button", "input", "textarea"}:
                if aria and aria != text:
                    parts.append(f"[{idx}]: <{tag}> \"{text}\", \"{aria}\";")
                else:
                    parts.append(f"[{idx}]: <{tag}> \"{text}\";")
            else:
                if aria and aria != text:
                    parts.append(f"[{idx}]: \"{text}\", \"{aria}\";")
                else:
                    parts.append(f"[{idx}]: \"{text}\";")

    return "\t".join(parts)


# CSI / SGR / cursor-movement / colour sequences (same as before, very fast).
_CSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

# OSC sequences: ESC ] … BEL or ESC ] … ESC \
_OSC_RE = re.compile(r"\x1B](?:[^\x07\x1b]*?)(?:\x07|\x1B\\)")

# ST / PM / APC, Device-control, etc.  (rare but easy to strip)
_MISC_RE = re.compile(r"\x1B[][PX^_].*?\x1B\\", re.DOTALL)

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

def scrub_images(msg):
    """
    Return a deep-copy of *msg* where every “image_url” content block is replaced
    with the canonical OpenAI-placeholder:

        {"type": "image_url",
         "image_url": {"url": "data:image/png;base64,{b64_img}"}}

    The original *msg* object is never mutated.

    Parameters
    ----------
    msg : dict | list[dict]
        • A single Chat Completion message, e.g.  
          {"role":"user","content":[...]}  
        • or a full messages list - the function will recurse through it.

    Returns
    -------
    dict | list[dict]
        A deep-copied structure with the images scrubbed.
    """
    PLACEHOLDER = {"url": "data:image/png;base64,{b64_img}"}

    def _scrub(item):
        # Handle the two container types we expect from the OpenAI schema
        if isinstance(item, list):
            return [_scrub(x) for x in item]

        if isinstance(item, dict):
            # Replace image blocks in the "content" array of a message
            if item.get("type") == "image_url":
                # create *new* dicts so the deepcopy guarantee is preserved
                return {
                    "type": "image_url",
                    "image_url": copy.deepcopy(PLACEHOLDER)
                }

            # Otherwise recurse through all dict values
            return {k: _scrub(v) for k, v in item.items()}

        # Scalars (str, int, None, etc.) are returned unchanged
        return item

    # start from a deep-copy of the top-level object
    msg_copy = copy.deepcopy(msg)
    return _scrub(msg_copy)

if __name__ == "__main__":
    port_to_kill = 3000  # Example port
    result_message = kill_service_on_port(port_to_kill)
    print(result_message)

    port_to_kill = 3001  # Example port
    result_message = kill_service_on_port(port_to_kill)
    print(result_message)