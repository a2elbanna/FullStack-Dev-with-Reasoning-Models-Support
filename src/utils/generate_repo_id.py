from urllib.parse import urlparse

def generate_repo_id(repo_url: str) -> str:
    """
    Convert a GitHub repository URL into an identifier in the form
    "{user_name}__{repo_name}".

    Parameters
    ----------
    repo_url : str
        A GitHub repository URL, e.g.
        "https://github.com/cod3rcursos/curso-nextjs.git"
        "git@github.com:cod3rcursos/curso-nextjs.git"
        "https://github.com/cod3rcursos/curso-nextjs"

    Returns
    -------
    str
        The identifier, e.g. "cod3rcursos__curso-nextjs".

    Raises
    ------
    ValueError
        If the URL cannot be parsed or doesn’t look like a GitHub repo.
    """
    # 1.  Normalize variations such as git@github.com:... ↦ https://github.com/...
    if repo_url.startswith("git@github.com:"):
        repo_url = repo_url.replace("git@github.com:", "https://github.com/")

    # 2.  Use `urlparse` to split the URL.
    parsed = urlparse(repo_url)

    # For scp-style URLs (git@github.com:user/repo.git) urlparse gives an empty netloc.
    if not parsed.netloc:            # fall back to a manual split
        path = parsed.path.lstrip(":")
    else:
        path = parsed.path

    # 3.  Extract path components ("/user/repo[.git]").
    parts = [p for p in path.split("/") if p]  # remove empty pieces
    if len(parts) < 2:
        raise ValueError(f"Unable to extract user/repo from: {repo_url}")

    user, repo = parts[0], parts[1]

    # 4.  Strip an optional ".git" suffix.
    if repo.endswith(".git"):
        repo = repo[:-4]

    return f"{user}___{repo}"


# ── simple demo ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    urls = [
        "https://github.com/cod3rcursos/curso-nextjs.git",
        "https://github.com/cod3rcursos/curso-nextjs",
        "git@github.com:cod3rcursos/curso-nextjs.git"
    ]
    for u in urls:
        print(f"{u}  ->  {generate_repo_id(u)}")