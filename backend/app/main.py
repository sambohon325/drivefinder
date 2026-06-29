import asyncio
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import config
from .database import init_db, SessionLocal
from .auth_routes import router as auth_router
from .chat_routes import router as chat_router
from .lead_routes import router as lead_router
from .dealer_routes import router as dealer_router
from .admin_routes import router as admin_router, require_admin
from . import regions as regions_module, prewarm, image_cache

app = FastAPI(title="DriveFinder by Vicimus")


@app.middleware("http")
async def no_cache_for_app_code(request: Request, call_next):
    """Without this, a browser can keep using a stale cached copy of app.js
    or styles.css after a deploy ships a fix — which looks exactly like 'the
    fix didn't work' even though the new code is live on the server. Forcing
    revalidation (not a full no-store; ETags still make this cheap) removes
    that entire class of confusion for an app this actively being iterated on.
    """
    response = await call_next(request)
    if request.url.path.startswith(("/js/", "/css/", "/assets/")) or request.url.path in (
        "/", "/dealer", "/admin", "/privacy", "/terms"
    ):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(lead_router)
app.include_router(dealer_router)
app.include_router(admin_router)

app.mount("/images", StaticFiles(directory=str(config.IMAGE_CACHE_DIR)), name="images")
app.mount("/css", StaticFiles(directory=str(config.FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(config.FRONTEND_DIR / "js")), name="js")
app.mount("/assets", StaticFiles(directory=str(config.FRONTEND_DIR / "assets")), name="assets")


def _within_prewarm_window() -> bool:
    """True if pre-warming should run right now, given PREWARM_RESTRICT_HOURS
    and the configured start/end hour in PREWARM_TIMEZONE. Uses an explicit
    IANA timezone rather than the container's system TZ, since that can vary
    by deploy environment and silently mean something different than
    intended.
    """
    if not config.PREWARM_RESTRICT_HOURS:
        return True
    start, end = config.PREWARM_ACTIVE_START_HOUR, config.PREWARM_ACTIVE_END_HOUR
    if start == end:
        return True  # equal start/end means "no restriction"
    now_hour = datetime.now(ZoneInfo(config.PREWARM_TIMEZONE)).hour
    if start < end:
        return start <= now_hour < end
    return now_hour >= start or now_hour < end  # window wraps past midnight


async def _prewarm_loop():
    """Generates one missing render per interval, forever, until the cache
    is fully warm for the current inventory — then just keeps checking in
    case inventory changes. Runs the actual (blocking) Gemini call in a
    worker thread via asyncio.to_thread so it never stalls the event loop
    that's serving real user requests; that would defeat the entire point.
    """
    consecutive_failures = 0
    max_backoff_multiplier = 10

    while True:
        backoff_multiplier = min(2 ** consecutive_failures, max_backoff_multiplier)
        await asyncio.sleep(config.PREWARM_INTERVAL_SECONDS * backoff_multiplier)

        if not config.GEMINI_API_KEY or not _within_prewarm_window():
            continue
        try:
            task = await asyncio.to_thread(prewarm.next_missing_render)
            if not task:
                consecutive_failures = 0
                continue
            key, prompt, meta = task
            url = await asyncio.to_thread(image_cache.get_or_generate, key, prompt, meta)
            # get_or_generate already swallows its own exceptions and returns
            # None on failure — back off on that, not just a raised error.
            consecutive_failures = 0 if url else consecutive_failures + 1
        except Exception:
            # Never let one failed generation kill the background loop —
            # it just waits longer and tries again.
            consecutive_failures += 1


@app.on_event("startup")
def on_startup():
    init_db()
    # Seed the runtime mock_db.json into the (likely empty, volume-mounted)
    # DATA_DIR on first boot only — never overwrite once it's there, since a
    # real inventory feed may replace it later.
    if not config.MOCK_DB_PATH.exists() and config.SEED_MOCK_DB_PATH.exists():
        shutil.copy(config.SEED_MOCK_DB_PATH, config.MOCK_DB_PATH)

    db = SessionLocal()
    try:
        regions_module.seed_region_table(db)
    finally:
        db.close()

    if config.PREWARM_ENABLED:
        asyncio.create_task(_prewarm_loop())


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dealer")
def dealer_page():
    return FileResponse(str(config.FRONTEND_DIR / "dealer.html"))


@app.get("/")
def index_page():
    return FileResponse(str(config.FRONTEND_DIR / "index.html"))


@app.get("/privacy")
def privacy_page():
    return FileResponse(str(config.FRONTEND_DIR / "privacy.html"))


@app.get("/terms")
def terms_page():
    return FileResponse(str(config.FRONTEND_DIR / "terms.html"))


@app.get("/admin")
def admin_page(_: bool = Depends(require_admin)):
    return FileResponse(str(config.FRONTEND_DIR / "admin.html"))
