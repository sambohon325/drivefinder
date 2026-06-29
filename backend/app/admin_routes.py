import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from . import config, models, inventory as inv
from .database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])
security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> bool:
    if not config.ADMIN_PASSWORD:
        raise HTTPException(
            503, "Admin access isn't configured yet — set ADMIN_USERNAME / ADMIN_PASSWORD."
        )
    user_ok = secrets.compare_digest(credentials.username, config.ADMIN_USERNAME)
    pass_ok = secrets.compare_digest(credentials.password, config.ADMIN_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(401, "Invalid admin credentials.", headers={"WWW-Authenticate": "Basic"})
    return True


def _slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "x"


def _guess_legacy_meta(filename: str) -> dict:
    """Best-effort fallback for files generated before structured metadata
    tracking existed. Cross-references known (make, model) pairs from the
    actual inventory instead of guessing word boundaries blindly — that
    matters because slugified multi-word models ('F-150' -> 'f_150', '3
    Series' -> '3_series') would otherwise be ambiguous to split correctly.
    """
    base = re.sub(r"\.png$", "", filename)
    base = re.sub(r"_v\d+$", "", base)  # strip a trailing version suffix if present

    if base.startswith("generic_"):
        return {"make": None, "model": None, "color": None, "category": base}

    known_pairs = sorted(
        {(c["make"], c["model"]) for c in inv.load_inventory()},
        key=lambda pair: -len(pair[1]),  # longer model names first, avoids partial-prefix collisions
    )
    for make, model in known_pairs:
        prefix = f"{_slug(make)}_{_slug(model)}"
        if base == prefix or base.startswith(prefix + "_"):
            remainder = base[len(prefix):].strip("_")
            return {"make": make, "model": model, "color": None, "category": remainder or "unknown"}

    return {"make": None, "model": None, "color": None, "category": "unknown"}


@router.get("/images")
def list_images(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        meta_by_filename = {m.filename: m for m in db.query(models.CachedRenderMeta).all()}
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        meta_by_filename = {}

    files = []
    for f in sorted(config.IMAGE_CACHE_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = f.stat()
        meta = meta_by_filename.get(f.name)
        if meta:
            make, model, color, category = meta.make, meta.model, meta.color, meta.category
            is_approved = meta.is_approved
        else:
            guess = _guess_legacy_meta(f.name)
            make, model, color, category = guess["make"], guess["model"], guess["color"], guess["category"]
            is_approved = True  # predates the review feature — already implicitly reviewed by hand

        files.append(
            {
                "filename": f.name,
                "url": f"/images/{f.name}",
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": stat.st_mtime,
                "make": make,
                "model": model,
                "color": color,
                "category": category,
                "is_approved": is_approved,
            }
        )
    return files


@router.post("/images/{filename}/approve")
def approve_image(filename: str, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename.")
    meta = db.query(models.CachedRenderMeta).filter(models.CachedRenderMeta.filename == filename).first()
    if not meta:
        # No metadata row (legacy file) — nothing to approve, it's already
        # treated as reviewed. Make this idempotent rather than an error.
        return {"filename": filename, "is_approved": True}
    meta.is_approved = True
    db.add(meta)
    db.commit()
    return {"filename": filename, "is_approved": True}


@router.delete("/images/{filename}")
def delete_image(filename: str, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename.")
    filepath = config.IMAGE_CACHE_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "Not found.")
    filepath.unlink()

    db.query(models.CachedRenderMeta).filter(models.CachedRenderMeta.filename == filename).delete()
    db.commit()

    return {"deleted": filename}


@router.get("/regions")
def list_regions(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(models.RegionAvailability)
        .order_by(models.RegionAvailability.country, models.RegionAvailability.name)
        .all()
    )
    return [
        {"country": r.country, "code": r.code, "name": r.name, "is_enabled": r.is_enabled}
        for r in rows
    ]


@router.post("/regions/{country}/{code}/toggle")
def toggle_region(country: str, code: str, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    row = (
        db.query(models.RegionAvailability)
        .filter(models.RegionAvailability.country == country.upper(), models.RegionAvailability.code == code.upper())
        .first()
    )
    if not row:
        raise HTTPException(404, "Region not found.")
    row.is_enabled = not row.is_enabled
    db.add(row)
    db.commit()
    return {"country": row.country, "code": row.code, "name": row.name, "is_enabled": row.is_enabled}


@router.post("/regions/{country}/bulk")
def bulk_set_country(
    country: str, enabled: bool, _: bool = Depends(require_admin), db: Session = Depends(get_db)
):
    """Quick 'turn everything on/off for this country' action — the
    realistic go-live workflow is flipping a whole country off, then
    selectively re-enabling the handful of launched states, rather than
    clicking 50+ individual toggles."""
    country = country.upper()
    if country not in ("US", "CA"):
        raise HTTPException(400, "country must be 'US' or 'CA'.")
    db.query(models.RegionAvailability).filter(models.RegionAvailability.country == country).update(
        {"is_enabled": enabled}
    )
    db.commit()
    return {"country": country, "is_enabled": enabled}


@router.get("/prewarm/status")
def prewarm_status(_: bool = Depends(require_admin)):
    from . import prewarm

    generated, total = prewarm.progress_summary()
    return {
        "generated": generated,
        "total": total,
        "enabled": config.PREWARM_ENABLED,
        "interval_seconds": config.PREWARM_INTERVAL_SECONDS,
    }


@router.post("/prewarm/run-now")
def prewarm_run_now(count: int = 1, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    """Manually generate the next few missing renders immediately, instead
    of waiting for the paced background loop — handy for testing or for
    quickly warming a specific gap rather than the whole inventory."""
    from . import prewarm, image_cache

    count = max(1, min(count, 10))
    generated = []
    for _i in range(count):
        task = prewarm.next_missing_render()
        if not task:
            break
        key, prompt, meta = task
        url = image_cache.get_or_generate(key, prompt, db=db, meta=meta)
        generated.append({"key": key, "generated": bool(url)})
    return {"generated": generated}
