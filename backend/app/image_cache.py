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


def get_or_generate(key: str, prompt: str, meta: Optional[dict] = None) -> Optional[str]:
    """Returns a public URL path for the cached (or freshly generated) render.
    Returns None only if generation fails and nothing is cached yet — callers
    should treat that as 'no image available this turn', not as an error.

    When meta is supplied, also records structured (make/model/color/
    category) metadata for the admin filter UI — on both a fresh generation
    and a cache hit, so older files naturally get backfilled the next time
    they're requested through the normal app flow. That write uses its own
    independent database session (see _ensure_meta) — deliberately not the
    caller's session, so it can never interfere with whatever the caller is
    doing with its own pending writes.
    """
    filename = f"{key}.png"
    filepath = config.IMAGE_CACHE_DIR / filename

    if filepath.exists():
        if meta is not None:
            _ensure_meta(filename, meta)
        return f"/images/{filename}"

    try:
        ok = gemini_client.generate_image(prompt, filepath)
    except Exception:
        return None

    if ok and meta is not None:
        _ensure_meta(filename, meta)

    return f"/images/{filename}" if ok else None


def _ensure_meta(filename: str, meta: dict) -> None:
    """Records metadata for the admin review queue. This is a secondary
    feature and must never be allowed to break real image generation or
    serving for an actual user — so it gets its own fully independent
    session, opened and closed right here:

    1. A dedicated session means this can never share an open transaction
       with whatever the calling request (e.g. a chat turn) is doing with
       its own session — a metadata hiccup literally cannot roll back or
       interfere with unrelated pending writes elsewhere in that request,
       because there's no shared state to interfere with.
    2. An atomic upsert (ON CONFLICT DO NOTHING) instead of 'check, then
       insert', so the background pre-warm loop and a live request racing
       to record the same filename at once can't collide on a duplicate key.
    3. try/except + rollback as a second layer, in case of any other
       unexpected DB hiccup — this function is purely best-effort.
    """
    from . import models
    from .database import SessionLocal
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    db = SessionLocal()
    try:
        stmt = (
            sqlite_insert(models.CachedRenderMeta)
            .values(
                filename=filename,
                make=meta.get("make"),
                model=meta.get("model"),
                color=meta.get("color"),
                category=meta.get("category"),
            )
            .on_conflict_do_nothing(index_elements=["filename"])
        )
        db.execute(stmt)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
