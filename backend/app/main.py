import shutil

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import config
from .database import init_db
from .auth_routes import router as auth_router
from .chat_routes import router as chat_router
from .lead_routes import router as lead_router
from .dealer_routes import router as dealer_router

app = FastAPI(title="DriveFinder by Vicimus")

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(lead_router)
app.include_router(dealer_router)

app.mount("/images", StaticFiles(directory=str(config.IMAGE_CACHE_DIR)), name="images")
app.mount("/css", StaticFiles(directory=str(config.FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(config.FRONTEND_DIR / "js")), name="js")


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
