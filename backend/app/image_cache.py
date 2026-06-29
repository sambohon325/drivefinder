import re
from typing import Optional

from . import config, gemini_client


def _slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "x"


def cache_key(*parts: str) -> str:
    """Builds a deterministic filename from spec parts, e.g.
    cache_key('Toyota', 'Camry', 'Red', 'side') -> 'toyota_camry_red_side_v2'.
    Same spec always maps to the same file, so repeat requests across
    different users are cache hits instead of new Gemini image calls.

    The trailing version segment means a prompt-wording fix (like the one
    that corrected wrong-vehicle renders) automatically invalidates every
    old render instead of silently continuing to serve it.
    """
    base = "_".join(_slug(p) for p in parts if p)
    return f"{base}_{config.IMAGE_PROMPT_VERSION}"


def get_or_generate(key: str, prompt: str) -> Optional[str]:
    """Returns a public URL path for the cached (or freshly generated) render.
    Returns None only if generation fails and nothing is cached yet — callers
    should treat that as 'no image available this turn', not as an error.
    """
    filename = f"{key}.png"
    filepath = config.IMAGE_CACHE_DIR / filename

    if filepath.exists():
        return f"/images/{filename}"

    try:
        ok = gemini_client.generate_image(prompt, filepath)
    except Exception:
        return None

    return f"/images/{filename}" if ok else None
