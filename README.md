# DriveFinder by Vicimus

An AI chat-based car finder. The buyer describes what they want; the assistant
narrows it down against inventory and renders the build alongside the
conversation. Leads get routed to preferred (Vicimus client) or standard
dealers. A separate `/dealer` portal is a placeholder for dealers to sign in
or start a 30-day trial.

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
- **California geo-block** — a keyword match on free-text location input.
  Fine for a demo, not a real compliance mechanism. Swap for an actual
  zip/state lookup before this goes anywhere near production traffic.
- **"Preferred dealer" matching** — currently a static flag on the mock
  inventory record, not actually influenced by the buyer's location or a
  real Bumper sync. Real preferred-dealer routing needs Vicimus's actual
  Bumper API, which this prototype has no access to.
- **"Regular dealer" matching** — same mock data, no live lookup of real
  local dealerships yet. See the open question below.
- **Dealer inventory sync** — the dashboard shows a status string only.
- **Dealer lead routing** — leads are stored with a `dealer_id` from the mock
  inventory match, but there's no real auth linking a dealer account to a
  specific dealership's leads yet (the dashboard is a placeholder render).

### Open question: real local-dealer lookup

The idea of finding actual nearby dealerships (e.g. searching "Toyota
dealers near Fort Worth" and pulling back a real name, address, and phone
number for outreach) needs a data source decision before it's worth
building — this isn't something to guess at, since it carries an ongoing
per-search cost regardless of which path is picked:

- **Gemini search grounding** — since the chat already runs on Gemini, this
  is the path requiring no new vendor relationship. Has its own per-search
  pricing on top of the existing chat/image costs.
- **Google Places API** — gives cleaner structured fields (address, phone,
  hours) than parsing search snippets, but is a separate Google Cloud
  product/billing setup.
- **A dedicated search API** (Serper, SerpAPI, Bing) — another vendor,
  another key to manage.

None of these are wired up yet. Worth a short conversation about budget and
which one before building against it.

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
