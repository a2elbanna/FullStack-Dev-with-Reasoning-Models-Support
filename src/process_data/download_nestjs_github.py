#!/usr/bin/env python3
# crawl_nestjs_repos_all.py
"""
Clone every GitHub repository that
  • matches the keyword "nestjs"
  • has at least 100 stars

Each successful clone is recorded to downloaded.jsonl:
  {url, stars, updated_at, path}

The process is fully resumable.
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Set

import requests
from tqdm import tqdm

# ────────────────── CONFIGURATION ──────────────────
QUERY      = "nestjs"       # ← keyword to search
STAR_FLOOR = 25               # minimum stars required
PER_PAGE = 100                 # GitHub maximum
DEST = Path("/mnt/cache/agent/Zimu/WebGen-Agent2/data_train/websites/nestjs_github-repos")
LOG_FILE = DEST / "downloaded.jsonl"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

# ───────────── LOW-LEVEL SEARCH HELPERS ─────────────
def github_search(params: dict, retry: int = 3) -> dict:
    """Wrapper around GET /search/repositories with basic rate-limit handling."""
    url = "https://api.github.com/search/repositories"
    while True:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code == 403 and "X-RateLimit-Reset" in r.headers:
            wait = max(int(r.headers["X-RateLimit-Reset"]) - int(time.time()) + 5, 5)
            print(f"Rate limited → sleeping {wait}s")
            time.sleep(wait)
            continue
        try:
            r.raise_for_status()
        except requests.HTTPError:
            if retry:
                retry -= 1
                time.sleep(2)
                continue
            raise
        return r.json()

def count_repos(star_min: int, star_max: int) -> int:
    q = f"{QUERY} stars:{star_min}..{star_max}"
    return github_search({"q": q, "per_page": 1})["total_count"]

def fetch_page(star_min: int, star_max: int, page: int) -> List[dict]:
    params = {
        "q": f"{QUERY} stars:{star_min}..{star_max}",
        "per_page": PER_PAGE,
        "page": page,
        "sort": "stars",
        "order": "desc",
    }
    return github_search(params).get("items", [])

# ───────────────── LOGGING & CLONING ─────────────────
def read_log() -> Set[str]:
    done = set()
    if LOG_FILE.exists():
        with LOG_FILE.open() as fp:
            for line in fp:
                try:
                    done.add(json.loads(line)["url"])
                except Exception:
                    pass
    return done

def append_log(url: str, stars: int, updated_at: str, path: Path) -> None:
    record = {
        "url": url,
        "stars": stars,
        "updated_at": updated_at,
        "path": str(path),
    }
    with LOG_FILE.open("a") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")

def git_clone(url: str, dst: Path) -> None:
    if dst.exists():
        return
    subprocess.run(
        ["git", "clone", "--depth=1", url, str(dst)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

# ────────────── RECURSIVE STAR-BUCKETING ─────────────
def split_and_process(star_min: int, star_max: int, downloaded: Set[str]) -> None:
    total = count_repos(star_min, star_max)
    if total == 0:
        return

    # If bucket exceeds the 1000-item API cap, split in half and recurse.
    if total > 1000 and star_max - star_min > 0:
        mid = (star_min + star_max) // 2
        split_and_process(star_min, mid, downloaded)
        split_and_process(mid + 1, star_max, downloaded)
        return

    # Otherwise, page through this bucket.
    pages = (total + PER_PAGE - 1) // PER_PAGE
    for page in range(1, pages + 1):
        for repo in tqdm(
            fetch_page(star_min, star_max, page),
            desc=f"⭐ {star_min}..{star_max} p{page}",
            unit="repo",
        ):
            url = repo["clone_url"]
            if url in downloaded:
                continue
            local_dir = DEST / repo["full_name"]
            try:
                git_clone(url, local_dir)
                append_log(
                    url,
                    repo["stargazers_count"],
                    repo["pushed_at"],   # last code push (ISO-8601 UTC)
                    local_dir,
                )
                downloaded.add(url)
            except subprocess.CalledProcessError as e:
                print(f"❌ Clone failed {url}: {e}")

# ───────────────────────── MAIN ─────────────────────────
def star_ceiling() -> int:
    """Return the highest star count among 'nestjs' repos."""
    res = github_search(
        {"q": QUERY, "per_page": 1, "sort": "stars", "order": "desc"}
    )
    return max(res["items"][0]["stargazers_count"], STAR_FLOOR) if res["items"] else STAR_FLOOR

def main() -> None:
    DEST.mkdir(exist_ok=True)
    downloaded = read_log()
    highest = star_ceiling()
    print(f"Highest star count found: {highest}")
    split_and_process(STAR_FLOOR, highest, downloaded)
    print("✅ All matching repositories processed.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved in downloaded.jsonl")
        sys.exit(1)