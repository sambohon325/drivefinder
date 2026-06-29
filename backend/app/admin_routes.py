import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import config

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
