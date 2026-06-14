# Tech Stack & Commands — Orbit

## Stack

| Layer      | Technology                                                                                                               |
| ---------- | ------------------------------------------------------------------------------------------------------------------------ |
| Backend    | Django 5.x, Django REST Framework, Celery, PostgreSQL 16, Redis 7                                                        |
| Frontend   | React 18, Vite 5, React Router 6, vanilla CSS, `exifr` for client EXIF                                                  |
| AI/ML      | OpenAI SDK (Gemini 2.5 Flash / GPT-4o-mini compatible), `networkx` (bipartite matching), Pillow (perceptual hashing)     |
| Infra      | Docker Compose, Gunicorn, Nginx, WhiteNoise, django-storages[s3], Python 3.12                                            |
| Deployment | AWS (CloudFront + S3 static, EC2/ECS backend, RDS, ElastiCache)                                                          |

### Python dependencies (`requirements.txt`)

Django, djangorestframework, psycopg[binary], gunicorn, whitenoise, requests, redis, Pillow, django-storages[s3], celery, openai, networkx, python-dateutil.

### Frontend dependencies (`package.json`)

react, react-dom, react-router-dom, exifr. Dev: @vitejs/plugin-react, vite.

### Embedding provider

The `nextowner` app ships a local embedding provider (`nextowner/providers/local.py`) that loads `sentence-transformers/all-MiniLM-L6-v2` at runtime when available. It is **not** in `requirements.txt` — the mock provider (hash-based, deterministic) is the default and is always used when `sentence-transformers` is not installed. To enable real embeddings, install `sentence-transformers` manually.

## Architecture conventions

- **Auth:** DRF `SessionAuthentication`, CSRF on unsafe methods, default permission `IsAuthenticatedOrReadOnly`. Sessions use `cached_db`. Custom user model is `core.User` (`AUTH_USER_MODEL`).
- **Async:** Celery worker auto-discovers each app's `tasks.py`. Heavy AI work (grading, rerouting, matching, embeddings) runs on the worker, never in the web process. Use the **chord** pattern: fan independent sources out in parallel, blend in an aggregate/finalize callback. Every subtask is wrapped in try/except and returns an empty partial instead of sinking the chord.
- **Graceful degradation:** Every AI call resolves a provider via a per-app registry that caches per process and falls back to a deterministic mock on any failure. The system MUST work fully offline with zero API keys.
- **Provider abstraction:** Add a provider by adding a `LLM_PROVIDERS` entry in `config/settings.py` — never a new call site. Auto-selection order is gemini → openai → modal, else mock.
- **Configuration over code:** All business knobs (storage rates, return windows, rerouting cost/risk factors, match weights, auction params, pricing constants, credit awards) live in `config/settings.py` and are env-overridable.
- **State transitions:** Every `ItemUnit`/`Listing`/`Order` transition must append an immutable `UnitEvent`. Never edit or delete events. The Health Card is a direct read of this trail. The `StatefulItem.transition()` helper in `core/models.py` handles this automatically.
- **Media:** Local volume by default; S3/CloudFront when `USE_S3=1`. Backend and worker share a media volume so grading reads uploaded photos without network round-trips.
- **Time:** `TIME_ZONE = "Asia/Kolkata"`, `USE_TZ = True`. Use timezone-aware datetimes and `dateutil.relativedelta` for calendar-accurate warranty math.
- **Currency:** All money is integer ₹ (INR).

## Commands

All commands run via Docker Compose from `backend/`.

```bash
# Start the full stack (db, redis, backend, worker, frontend on port 80)
docker compose up --build

# Start with HMR dev frontend on port 5173 instead of Nginx
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Run the test suite (eager Celery, mock providers, no network)
docker compose exec backend python manage.py test grading rerouting returnprevention

# Migrations
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate

# Seed demo data (25 products w/ real photos, 5 users w/ sizes + geo)
docker compose exec backend python manage.py seed_demo

# Seed green-credit rewards store
docker compose exec backend python manage.py seed_greencredits

# Refresh product images from images/ directory
docker compose exec backend python manage.py refresh_product_images

# Storage accrual (facility daily clock)
docker compose exec backend python manage.py accrue_storage
```

- For real AI grading, set `GEMINI_API_KEY` in `backend/.env`. Without it, deterministic mocks run every flow.
- Tests run with `CELERY_TASK_ALWAYS_EAGER=1` and mock providers — no external dependencies, no flakiness.
- Do not start long-running dev servers in automation; ask the user to run `docker compose up` manually.

## Verification expectations

- After backend changes, run the relevant app tests above.
- New AI behavior needs a deterministic mock path and a test that passes offline.
- Network-exposed endpoints must state their auth posture; the API defaults to authenticated-or-read-only.
