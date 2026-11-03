import json
import re


def parse_json_response(response_text: str) -> dict:
    """
    Parses a JSON response string and returns a dictionary.
    If parsing fails, returns an empty dictionary.
    """
    try:
        response_json = json.loads(response_text)
        return response_json
    except json.JSONDecodeError:
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                response_json = json.loads(json_match.group())
                return response_json
            except:
                return None
        return None

_JSON_BLOCK_RE = re.compile(r"```json(.*?)```", re.S)

def parse_json_response_with_codeblock(raw_text: str):
    """
    Extract the list of data structures from the model's raw response.
    Returns [] if nothing could be parsed.
    """
    # 1) Prefer the fenced ```json ... ``` block
    match = _JSON_BLOCK_RE.search(raw_text)
    json_src = match.group(1).strip() if match else raw_text

    try:
        parsed = json.loads(json_src)
        return parsed
    except json.JSONDecodeError:
        pass  # fall through to next attempt

    # 2) Fallback: try to find a list-like string manually
    try:
        parsed = json.loads(re.search(r"\{.*\}", raw_text, re.S).group())
        return parsed
    except Exception:
        return None