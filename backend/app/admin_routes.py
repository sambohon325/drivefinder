import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from . import config, models
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


@router.get("/images")
def list_images(_: bool = Depends(require_admin)):
    files = []
    for f in sorted(config.IMAGE_CACHE_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = f.stat()
        files.append(
            {
                "filename": f.name,
                "url": f"/images/{f.name}",
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": stat.st_mtime,
            }
        )
    return files


@router.delete("/images/{filename}")
def delete_image(filename: str, _: bool = Depends(require_admin)):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename.")
    filepath = config.IMAGE_CACHE_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "Not found.")
    filepath.unlink()
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
