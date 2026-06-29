import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Secrets / API keys ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# --- Models ---
# gemini-2.5-flash-image is scheduled for shutdown 2026-10-02 by Google.
# Build on the successor from day one to avoid a forced mid-flight migration.
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gemini-2.5-flash")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gemini-3.1-flash-image-preview")

# Bump this any time the prompt text in chat_logic.py changes meaningfully.
# It's folded into every cache key, so a bump makes every old render
# unreachable and forces a fresh generation — without it, fixing a prompt
# silently keeps serving the old (wrong) cached images forever.
IMAGE_PROMPT_VERSION = os.environ.get("IMAGE_PROMPT_VERSION", "v5")

# --- Admin (internal use only — reviewing/clearing cached renders) ---
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# --- Storage paths (mount DATA_DIR + IMAGE_CACHE_DIR as a Coolify persistent volume) ---
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
IMAGE_CACHE_DIR = Path(os.environ.get("IMAGE_CACHE_DIR", BASE_DIR / "image_cache"))
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "drivefinder.db"))

# mock_db.json lives in the *volume* (DATA_DIR) so it can eventually be swapped
# for a real inventory feed without rebuilding the image. SEED_MOCK_DB_PATH is
# the copy baked into the image, used to populate DATA_DIR on first boot.
MOCK_DB_PATH = DATA_DIR / "mock_db.json"
SEED_MOCK_DB_PATH = Path(os.environ.get("SEED_MOCK_DB_PATH", BASE_DIR / "data" / "mock_db.json"))

# Frontend static files (HTML/CSS/JS). Overridden in Docker to point at the
# copied frontend/ directory.
FRONTEND_DIR = Path(os.environ.get("FRONTEND_DIR", BASE_DIR.parent / "frontend"))

DATABASE_URL = f"sqlite:///{DB_PATH}"

# --- Misc ---
SESSION_COOKIE_NAME = "df_session"
SESSION_TTL_DAYS = 30
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Background cache pre-warming ---
# Quietly generates renders the current inventory needs before anyone asks
# for them, so the first real user to want a given spec doesn't wait on a
# live Gemini call. Paced deliberately slow by default — this isn't urgent,
# and there's no reason to burst-generate hundreds of images at once.
PREWARM_ENABLED = os.environ.get("PREWARM_ENABLED", "true").lower() != "false"
PREWARM_INTERVAL_SECONDS = int(os.environ.get("PREWARM_INTERVAL_SECONDS", "45"))
