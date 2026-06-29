import shutil

from fastapi import FastAPI, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import config
from .database import init_db
from .auth_routes import router as auth_router
from .chat_routes import router as chat_router
from .lead_routes import router as lead_router
from .dealer_routes import router as dealer_router
from .admin_routes import router as admin_router, require_admin

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
    if request.url.path.startswith(("/js/", "/css/", "/assets/")) or request.url.path in ("/", "/dealer", "/admin"):
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


@app.on_event("startup")
def on_startup():
    init_db()
    # Seed the runtime mock_db.json into the (likely empty, volume-mounted)
    # DATA_DIR on first boot only — never overwrite once it's there, since a
    # real inventory feed may replace it later.
    if not config.MOCK_DB_PATH.exists() and config.SEED_MOCK_DB_PATH.exists():
        shutil.copy(config.SEED_MOCK_DB_PATH, config.MOCK_DB_PATH)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dealer")
def dealer_page():
    return FileResponse(str(config.FRONTEND_DIR / "dealer.html"))


@app.get("/")
def index_page():
    return FileResponse(str(config.FRONTEND_DIR / "index.html"))


@app.get("/admin")
def admin_page(_: bool = Depends(require_admin)):
    return FileResponse(str(config.FRONTEND_DIR / "admin.html"))
