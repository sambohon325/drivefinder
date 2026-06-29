# DriveFinder by Vicimus

An AI chat-based car finder. The buyer describes what they want; the assistant
narrows it down against inventory and renders the build alongside the
conversation. Every dealer in the system is a Vicimus customer — DriveFinder
only operates in markets where Vicimus already has dealer coverage, managed
state-by-state and province-by-province from `/admin` (see "Region
availability" below), expanding market by market rather than trying to
serve everywhere on day one. A separate `/dealer` portal is a placeholder for
dealers to sign in or start a 30-day trial.

## How it's put together

```
drivefinder/
├── backend/
│   ├── app/            FastAPI app: auth, chat, leads, dealer routes
│   ├── data/            mock_db.json (seed inventory, baked into the image)
│   └── requirements.txt
├── frontend/            Plain HTML/CSS/JS — no build step
│   ├── index.html       Consumer chat + build panel
│   ├── dealer.html       Dealer sign-in / trial / dashboard placeholder
│   ├── css/styles.css
│   └── js/{app,dealer}.js
├── Dockerfile            Single container: FastAPI serves the API + the static frontend
├── docker-compose.yml    For local testing
└── .env.example
```

One container, one process. FastAPI serves the API under `/api/*` and the
two HTML pages directly — no separate frontend server, no build step, which
keeps this a single Dockerfile for Coolify.

### Why chat history lives in the database, not in memory

The original prototype kept a `chat.create()` object alive in memory for the
whole CLI session. A web app needs sessions to survive page reloads, server
restarts, and "come back tomorrow and finish your build" — so every turn is
written to `chat_messages`, and each request to Gemini replays that history
from the database instead of relying on an in-memory object. That's also
what makes "track this lead / continue your chat later" actually work.

### Image generation is cached by spec, not by session

`image_cache.py` builds a filename from `(make, model, color, angle)` — *not*
from the session or the user. The first person to configure a red Camry
generates that render; every person after them gets a cache hit. See
`IMAGE_CACHE_DIR` below — this directory is the whole cost-control strategy,
so it needs to be on persistent storage, not wiped on every deploy.

**If you change the prompt wording in `chat_logic.py`**, bump
`IMAGE_PROMPT_VERSION` in your environment (or the default in `config.py`).
It's folded into every cache key, so a bump makes every previously-cached
render unreachable and forces a fresh one — without this, a prompt fix
silently keeps serving the old (possibly wrong) cached images forever, which
is exactly what happened once already.

### Admin tool: reviewing and clearing cached renders

Visit `/admin` (HTTP Basic Auth, separate from regular user/dealer accounts
— set `ADMIN_USERNAME` / `ADMIN_PASSWORD`) to see every cached render with
its filename, size, and age, and delete any that look wrong. Deleting just
removes the file; it regenerates fresh the next time that exact spec comes
up. Leave `ADMIN_PASSWORD` blank to disable the tool entirely.

### Background cache pre-warming

A loop started on app startup (`main.py` → `_prewarm_loop`) quietly
generates whichever render the current inventory needs next — one at a
time, paced by `PREWARM_INTERVAL_SECONDS` (default 45s) — so a real visitor
asking for a make/model/color nobody's requested yet doesn't have to wait
on a live Gemini call. It's fully resumable: `prewarm.py` recomputes the
"what's still missing" list from inventory + what's already on disk every
time, rather than keeping a separate queue table that could drift out of
sync. Set `PREWARM_ENABLED=false` to turn it off.

The blocking Gemini call runs via `asyncio.to_thread` specifically so it
never stalls the event loop that's serving real requests — the whole point
is to make things faster for users, not to introduce a background job that
competes with them.

`/admin` also shows overall progress (e.g. "340 / 511 renders") and has a
"Generate one now" button for nudging it along without waiting for the next
interval.

### Unprocessed renders: review without gating

Every render — whether from the background pre-warm or from someone
actually using the chat — lands in an **Unprocessed** queue at `/admin`
first. Critically, **this never gates serving**: an unprocessed render is
exactly as live as an approved one the moment it exists on disk. The queue
is purely for your review, so you can catch something wrong before it's
sitting in front of a lot of people, without making anyone wait on that
review to happen.

- **Approve** marks it reviewed and moves it into the normal filterable
  "Cached renders" section below.
- **Delete** removes it (same as the main grid) — it regenerates fresh
  next time that spec is needed.
- Files that predate this feature (no metadata row at all) are treated as
  already-reviewed and show up directly in "Cached renders," not in the
  queue — there'd be no point retroactively flagging hundreds of renders
  you've already been looking at throughout testing.

### Region availability

Also on `/admin`: every US state and Canadian province/territory, each with
its own on/off toggle, split into two groups. This is what the location gate
actually checks — **not** an environment variable — so it can be changed
live without a redeploy.

- **Seeded all-enabled** on first boot (`regions.py` → `seed_region_table`),
  matching "open to everyone for testing." Never re-seeds after that, so
  toggles you make survive restarts and redeploys.
- **"Enable all" / "Disable all"** per country are there for the realistic
  go-live workflow: flip a whole country off, then selectively re-enable
  the handful of states you've actually launched in, rather than clicking
  every toggle individually.
- **California is excluded from the toggle grid** (shown as "LEGAL," not
  clickable) — it's blocked by the separate, hardcoded franchise-law check
  in `chat_routes.py`, which always runs first regardless of what this
  table says. That's intentional: a legal constraint shouldn't be one
  accidental admin click away from being switched back on.
- Detecting *which* state/province someone's in from a free-text location
  field is still just matching against state/province names and
  abbreviations (`regions.detect_region`) — fine for testing, not a real
  geocoding lookup. An unrecognized location is let through rather than
  blocked, so this only restricts places it can actually identify.

### The build progressively renders, in three stages

1. **Body style only** ("show me an SUV") → an intentionally soft, blurred
   generic placeholder for that body type — three of these exist total
   (sedan/SUV/truck), so this stage costs almost nothing.
2. **Make + model chosen, no color yet** → a sharp, de-badged "clay" render
   in neutral grey.
3. **A specific option is locked in** → the real multi-angle set (front,
   side, rear, cockpit, seating) in the actual color.

### Checkout is conversational, not a popup

Delivery preference, financing approach, and the dealer-cross-sell question
are asked as part of the chat thread itself (quick-reply buttons inline in
the conversation), not a modal that covers the screen. Sign-up, when
needed, is also an embedded card in the thread rather than a separate
overlay. The only modal left is the nav's Sign in/Sign up, which is a
different context (account management, not the build flow).

### Notify-me-when-available

If someone asks for a make/model that's not in inventory, the assistant
names one or two close in-stock alternatives and offers a "notify me"
capture (email + what they wanted), stored in `notify_requests`. **No
notification pipeline actually emails these yet** — there's nowhere for
that list to go until it's wired to something (Listmonk, presumably, given
the rest of the stack). Right now it's just captured, not acted on.

### What's a placeholder right now

These are intentionally stubbed so the prototype is testable without being
load-bearing for real users yet:

- **Bumper credit pull** (`lead_routes.py`) — returns a hardcoded "Tier 1"
  result. Replace with the real Bumper API before this touches a real
  applicant's credit profile.
- **Welcome email / delivery notifications** — the chat now *tells* the
  buyer this is coming ("we'll email you a welcome message with your
  build's render and dealership details..."), but no email actually sends.
  That copy is describing the intended experience, not a working feature —
  needs a real email pipeline before it's true.
- **Dealer F&I perks** (free delivery, etc.) — copy-only on the frontend,
  not tied to real dealer agreements yet.
- **California geo-block** — a hardcoded keyword match on free-text
  location input, kept deliberately separate from the region-availability
  table (it's a legal constraint, not a business rollout decision, so it
  can't accidentally be toggled back on from the admin UI). The region
  allowlist itself is real (DB-backed, admin-toggleable — see below), but
  detecting *which* state/province from free text is still just text
  matching, not a real geocoding lookup. Swap for an actual zip/state
  lookup before this goes anywhere near production traffic.
- **Dealer matching** — every dealer in the mock inventory is treated as a
  Vicimus customer (no more preferred/standard distinction — that's the
  point of the region gate), but matching itself is still mock data, not a
  real Bumper sync tied to which dealers actually carry which inventory.
- **Dealer inventory sync** — the dashboard shows a status string only.
- **Dealer lead routing** — leads are stored with a `dealer_id` from the mock
  inventory match, but there's no real auth linking a dealer account to a
  specific dealership's leads yet (the dashboard is a placeholder render).

Deliberately **not** building: live web search/scraping for dealers outside
Vicimus's network. The model going forward is region-gated and
Vicimus-customers-only — expand market by market (alongside regional
marketing) rather than try to surface every dealership everywhere.

## Running it locally

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY + a real SECRET_KEY
docker compose up --build
```

Then open http://localhost:8000 (consumer) and http://localhost:8000/dealer
(dealer portal).

Without `docker compose`, you can also run it directly:

```bash
cd backend
pip install -r requirements.txt
GEMINI_API_KEY=... SECRET_KEY=... FRONTEND_DIR=../frontend uvicorn app.main:app --reload
```

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Used for both chat extraction and image generation |
| `SECRET_KEY` | Yes | Signs session cookies — use a real random string in production |
| `ENVIRONMENT` | No | Set to `production` to enable secure (HTTPS-only) cookies |
| `CHAT_MODEL` | No | Defaults to `gemini-2.5-flash` |
| `IMAGE_MODEL` | No | Defaults to `gemini-3.1-flash-image-preview` (see note below) |
| `IMAGE_PROMPT_VERSION` | No | Bump on any meaningful prompt change — see above |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | No | Enables `/admin`. Leave password blank to disable it |
| `PREWARM_ENABLED` | No | Set `false` to turn off background cache pre-warming |
| `PREWARM_INTERVAL_SECONDS` | No | Seconds between each pre-warmed render. Defaults to 45 |

**Heads up:** `gemini-2.5-flash-image` (the model in the original prototype)
is scheduled to shut down by Google on **October 2, 2026**. This build
defaults to its successor, `gemini-3.1-flash-image-preview`, from day one so
there's no forced mid-flight migration. Check Google's current Gemini API
pricing/deprecation page before launch in case that timeline shifts.

## Deploying: GitHub + Coolify

1. **Push to GitHub**
   ```bash
   cd drivefinder
   git init
   git add .
   git commit -m "Initial DriveFinder prototype"
   git branch -M main
   git remote add origin <your-new-repo-url>
   git push -u origin main
   ```
   This is a fresh repo — nothing here is wired to a remote yet, so create
   the GitHub repo first (empty, no README) and use its URL above.

2. **In Coolify: New Resource → Application → your GitHub repo.**
   Coolify will detect the `Dockerfile` at the repo root automatically —
   no build pack selection needed.

3. **Set environment variables** (Coolify → your app → Environment Variables):
   - `GEMINI_API_KEY`
   - `SECRET_KEY` (generate one: `python3 -c "import secrets; print(secrets.token_hex(32))"`)
   - `ENVIRONMENT=production`
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD` (optional — enables `/admin` for reviewing cached renders)

4. **Add persistent storage** (Coolify → your app → Storages). Mount two
   volumes so the database and image cache survive redeploys:
   - `/app/data`
   - `/app/image_cache`

   Skipping this means every redeploy wipes the user database *and* the
   entire image cache — which defeats the whole cost-saving point of the
   cache.

5. **Set the domain** to `www.drivefinder.xyz` in Coolify's domain settings,
   and point your DNS A/CNAME record at the server. Coolify handles the
   Let's Encrypt certificate.

6. **Deploy.** Every push to `main` (or whichever branch you point Coolify
   at) triggers a rebuild — that's the "tech team can see it on their side
   too" part, since anyone with repo access can see exactly what shipped.

## Known gaps before this is more than a prototype

- Auth has no email verification or password reset flow.
- No rate limiting on chat or image generation endpoints — a script could
  rack up Gemini costs by hammering `/api/chat/message`. Worth adding
  before sharing a public link.
- SQLite is fine for testing; move to Postgres before real concurrent load.
- No automated tests yet — only the manual end-to-end pass done during
  development.
