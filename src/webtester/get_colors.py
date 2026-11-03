from collections import Counter
from pathlib import Path
from typing import Tuple, List

from PIL import Image


def rgba_to_hex(rgba: Tuple[int, int, int, int]) -> str:
    """Convert an 8-bit RGBA tuple to a hex color string (#rrggbb)."""
    r, g, b, _ = rgba
    return f"#{r:02x}{g:02x}{b:02x}"


def most_used_colors(
    file_path: str | Path,
    top_n: int = 5,
    *,
    ignore_alpha: bool = True,
    min_alpha: int = 1,
    decimal_places: int = 1,
) -> str:
    """
    Find the `top_n` most-common colors in a PNG file.

    Parameters
    ----------
    file_path : str | pathlib.Path
        Path to the PNG image.
    top_n : int, default 5
        Number of dominant colors to return.
    ignore_alpha : bool, default True
        If True, pixels whose alpha channel is < `min_alpha` are ignored.
    min_alpha : int, default 1
        Minimum alpha value (0-255) considered opaque enough to count.
    decimal_places : int, default 1
        Precision for the percentage values.

    Returns
    -------
    str
        A comma-separated list like:
        "#f0f0f0: 87.1%, #dc143c: 13.5%, ..."
    """
    img = Image.open(file_path).convert("RGBA")
    pixels = img.getdata()

    if ignore_alpha:
        pixels = [px for px in pixels if px[3] >= min_alpha]

    if not pixels:
        raise ValueError("Image has no visible (non-transparent) pixels.")

    total = len(pixels)
    counts = Counter(pixels).most_common(top_n)

    parts: List[str] = []
    for rgba, cnt in counts:
        hex_color = rgba_to_hex(rgba)
        pct = round(cnt * 100 / total, decimal_places)
        parts.append(f"{hex_color}: {pct:.{decimal_places}f}%")

    return "\nTop 5 colors in the screenshot by pixel share: " + ", ".join(parts) + "\nTrust this over your own ability to identify colors."


# ---------------------------------------------------------------------------
# Example usage (uncomment to test):
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(most_used_colors("/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-Qwen3-Coder-480B-A35B-Instruct-FP8_hist-100_iter-400_compress-0.5_val-1_sum-5_v7_backend-limit/000011/frontend_test_272/screenshot_iter_1.png"))