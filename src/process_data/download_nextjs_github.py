#!/usr/bin/env python3
# crawl_next_repos_all.py
"""
Download every GitHub repository that
  • matches the keyword "next.js"
  • has at least 100 stars

A JSON-Lines file `downloaded.jsonl` keeps one record per repo:
  {
    "url":        <clone url>,
    "stars":      <int>,
    "updated_at": <ISO-8601 pushed time>,
    "path":       <absolute clone folder>
  }

The script is idempotent: if interrupted, re-run it and already logged
repositories will be skipped.
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
from dotenv import load_dotenv
load_dotenv()

# ───────────────────────── configuration ────────────────────────────
QUERY = "next.js"
STAR_FLOOR = 50               # minimum stars required
PER_PAGE = 100                 # GitHub maximum
DEST = Path("/mnt/cache/agent/Zimu/WebGen-Agent2/data_train/websites/nextjs_github-repos")
LOG_FILE = DEST / "downloaded.jsonl"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
print(GITHUB_TOKEN)
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

# ────────────────────── low-level API helpers ───────────────────────
def github_search(params: dict, retry: int = 3) -> dict:
    url = "https://api.github.com/search/repositories"
    while True:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code == 403 and "X-RateLimit-Reset" in r.headers:
            wait = max(int(r.headers["X-RateLimit-Reset"]) - int(time.time()) + 5, 5)
            print(f"Rate-limited → sleeping {wait}s")
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
    q = f"{QUERY} stars:{star_min}..{star_max}"
    res = github_search(
        {
            "q": q,
            "per_page": PER_PAGE,
            "page": page,
            "sort": "stars",
            "order": "desc",
        }
    )
    return res.get("items", [])

# ───────────────────────── logging & clone ──────────────────────────
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

# ───────────────── recursive bucket processing ──────────────────────
def split_and_process(star_min: int, star_max: int, downloaded: Set[str]) -> None:
    total = count_repos(star_min, star_max)
    if total == 0:
        return

    if total > 1000 and star_max - star_min > 0:
        mid = (star_min + star_max) // 2
        split_and_process(star_min, mid, downloaded)
        split_and_process(mid + 1, star_max, downloaded)
        return

    pages = (total + PER_PAGE - 1) // PER_PAGE
    for page in range(1, pages + 1):
        items = fetch_page(star_min, star_max, page)
        for repo in tqdm(items, desc=f"⭐ {star_min}..{star_max} p{page}", unit="repo"):
            url = repo["clone_url"]
            if url in downloaded:
                continue
            local_dir = DEST / repo["full_name"]
            try:
                git_clone(url, local_dir)
                append_log(
                    url,
                    repo["stargazers_count"],
                    repo["pushed_at"],          # last code push
                    local_dir,
                )
                downloaded.add(url)
            except subprocess.CalledProcessError as e:
                print(f"❌ clone failed {url}: {e}")

# ───────────────────────────── main ─────────────────────────────────
def star_ceiling() -> int:
    res = github_search({"q": QUERY, "per_page": 1, "sort": "stars", "order": "desc"})
    return max(res["items"][0]["stargazers_count"], STAR_FLOOR) if res["items"] else STAR_FLOOR

def main() -> None:
    DEST.mkdir(exist_ok=True)
    downloaded = read_log()
    highest = star_ceiling()
    print(f"Highest star count observed: {highest}")
    split_and_process(STAR_FLOOR, highest, downloaded)
    print("✅ Finished. All matching repos processed.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Progress saved in downloaded.jsonl")
        sys.exit(1)