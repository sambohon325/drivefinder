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


def get_or_generate(key: str, prompt: str, db=None, meta: Optional[dict] = None) -> Optional[str]:
    """Returns a public URL path for the cached (or freshly generated) render.
    Returns None only if generation fails and nothing is cached yet — callers
    should treat that as 'no image available this turn', not as an error.

    When db + meta are supplied, also records structured (make/model/color/
    category) metadata for the admin filter UI — on both a fresh generation
    and a cache hit, so older files naturally get backfilled the next time
    they're requested through the normal app flow.
    """
    filename = f"{key}.png"
    filepath = config.IMAGE_CACHE_DIR / filename

    if filepath.exists():
        if db is not None and meta is not None:
            _ensure_meta(db, filename, meta)
        return f"/images/{filename}"

    try:
        ok = gemini_client.generate_image(prompt, filepath)
    except Exception:
        return None

    if ok and db is not None and meta is not None:
        _ensure_meta(db, filename, meta)

    return f"/images/{filename}" if ok else None


def _ensure_meta(db, filename: str, meta: dict) -> None:
    from . import models  # local import: avoids a circular import at module load time

    existing = db.query(models.CachedRenderMeta).filter(models.CachedRenderMeta.filename == filename).first()
    if existing:
        return
    db.add(
        models.CachedRenderMeta(
            filename=filename,
            make=meta.get("make"),
            model=meta.get("model"),
            color=meta.get("color"),
            category=meta.get("category"),
        )
    )
    db.commit()
