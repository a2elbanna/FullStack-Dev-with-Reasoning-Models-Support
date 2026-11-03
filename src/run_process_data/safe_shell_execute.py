#!/usr/bin/env python3
"""
Safe execution of **rm / mkdir** commands embedded in an arbitrary
shell-like command line.  
  
New requirement:  
If a *cd* appears before *rm* or *mkdir*, the working directory that
is checked **and** used for execution must be updated first.
"""

from __future__ import annotations
import os
import shlex
import subprocess
from pathlib import Path
from typing import List, Tuple, Sequence, Union, Optional

# --------------------------------------------------------------------------- #
#                               Small helpers                                 #
# --------------------------------------------------------------------------- #
_SEPARATORS = {";", "&&", "||", "|", "&"}          # tokens that delimit commands
_RM_MKDIR    = {"rm", "mkdir"}


def _resolve_dir(current: Path, token: str) -> Path:
    """Return *token* interpreted as a path relative to *current*."""
    if token == "~":                      # expand home manually (shlex kept it)
        return Path.home().resolve()

    p = Path(token)
    if not p.is_absolute():
        p = current / p
    return p.resolve()


# --------------------------------------------------------------------------- #
#                      Parsing the original command line                      #
# --------------------------------------------------------------------------- #
def _collect_segments(tokens: Sequence[str],
                      base_cwd: Union[str, os.PathLike]
                      ) -> List[Tuple[List[str], Path]]:
    """
    Walk through *tokens* left→right and collect every rm/mkdir *segment*
    together with the *cwd* that is in effect **after** applying all `cd`
    tokens seen so far.

    Returned value:  list of (segment_tokens, cwd_for_that_segment)
    """
    segments: List[Tuple[List[str], Path]] = []
    cwd = Path(base_cwd).resolve()
    i = 0
    n = len(tokens)

    def skip_separators(idx: int) -> int:
        while idx < n and tokens[idx] in _SEPARATORS:
            idx += 1
        return idx

    while i < n:
        tok = tokens[i]

        # ---------------------  Handle a `cd`  --------------------- #
        if tok == "cd":
            # Expect exactly one directory token right after `cd`
            if i + 1 < n and tokens[i + 1] not in _SEPARATORS:
                cwd = _resolve_dir(cwd, tokens[i + 1])
                i += 2
            else:                       # malformed -> just ignore
                i += 1
            i = skip_separators(i)
            continue

        # ------------------  Handle rm / mkdir  -------------------- #
        if tok in _RM_MKDIR:
            seg = [tok]
            j = i + 1
            # Everything until the next separator or next recognised command
            while (j < n and
                   tokens[j] not in _SEPARATORS and
                   tokens[j] not in _RM_MKDIR and
                   tokens[j] != "cd"):
                seg.append(tokens[j])
                j += 1
            segments.append((seg, cwd))
            i = skip_separators(j)
            continue

        # Anything else → just skip
        i += 1

    return segments


# --------------------------------------------------------------------------- #
#                           Safety-checking paths                             #
# --------------------------------------------------------------------------- #
def _all_paths_safe(seg: Sequence[str], cwd: Path) -> bool:
    """
    True ⇢ every non-option path inside *seg* stays *inside* *cwd*.
    """
    for token in seg[1:]:                       # skip "rm"/"mkdir"
        if token.startswith("-"):               # option → ignore
            continue
        path = Path(token)
        if not path.is_absolute():
            path = cwd / path
        try:
            path = path.resolve()
        except FileNotFoundError:
            # Even if the path does not (yet) exist, we can still validate
            path = (cwd / path).resolve()

        try:
            path.relative_to(cwd)               # raises ValueError if outside
        except ValueError:
            return False
    return True


# --------------------------------------------------------------------------- #
#                              Public function                                #
# --------------------------------------------------------------------------- #
def safe_shell_execute(command: str,
                          cwd: Union[str, os.PathLike],
                          *,
                          check: bool = True,
                          capture_output: bool = False
                          ) -> Optional[List[subprocess.CompletedProcess]]:
    """
    Parse *command*, honour any `cd` that appears before each `rm`/`mkdir`,
    and execute **only** those `rm`/`mkdir` segments whose paths stay inside
    the (possibly updated) working directory.

    Nothing is executed when:
      • the line contains no rm/mkdir  
      • any path would escape its corresponding cwd  
    """
    tokens = shlex.split(command, posix=True)
    segments = _collect_segments(tokens, cwd)

    if not segments:                       # no rm / mkdir found
        return None

    # Validate *all* segments before executing anything
    for seg, seg_cwd in segments:
        if not _all_paths_safe(seg, seg_cwd):
            return None                    # abort the entire call

    results: List[subprocess.CompletedProcess] = []
    for seg, seg_cwd in segments:
        cp = subprocess.run(
            seg,
            cwd=seg_cwd,
            check=check,
            capture_output=capture_output,
            text=True,
        )
        results.append(cp)

    return results


# --------------------------------------------------------------------------- #
#                                   Demo                                      #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    project_root = "/home/alice/project"

    cmd_ok = (
        "cd src && rm -rf build/temp ; "
        "cd .. && mkdir build/output"
    )
    cmd_bad1 = "cd / && rm -rf etc"             # outside the project tree
    cmd_bad2 = "echo just a test"               # no rm / mkdir

    print("OK   :", safe_execute_rm_mkdir(cmd_ok, project_root))
    print("BAD1 :", safe_execute_rm_mkdir(cmd_bad1, project_root))
    print("BAD2 :", safe_execute_rm_mkdir(cmd_bad2, project_root))