# Project Structure — Orbit

## Repository layout

```
backend/
  config/          Settings, URLs, Celery app, WSGI
  core/            User model (TimeStamped, StatefulItem), auth,
                   permissions, uploads, management commands (seed_demo,
                   refresh_product_images)
  catalog/         Product, ItemUnit, UnitEvent, warranty math
  marketplace/     Listing, Order, return flow, return-window policy
  grading/         Multi-source AI grading pipeline
    providers/     VLM (OpenAI-compat, Bedrock, Modal, Mock), PHash
                   embedding, registry
    orchestrator   Source runners + aggregate
    scoring        Multi-source blend + fraud floor
    jsonio         Deterministic JSON recovery from LLM output
    history        Buyer order-history fraud signals
    metadata       EXIF + server-side image fraud anomaly detection
    prompts        Strict JSON schema for constrained VLM output
    services       High-level grading entry point (views → services → tasks)
  rerouting/       Disposition engine (EV + LLM, parallel)
    costs          Risk-adjusted profit model
    optimizer      Argmax over routes
    strategies     Build context, finalize, keep-it offer
    llm            LLM strategy caller (OpenAI-compat)
    prompts        LLM rerouting prompt templates
    geo            Haversine distance, Indian city centroids
  nextowner/       P2P resale: matching + Dutch auction
    matching       5-signal bipartite scoring (networkx)
    pricing        Quality-depreciation-fraud formula + auction bounds
    auction        Dutch auction: start, step, buy, rematch
    profiles       Demand profile builder
    products       Product vector cache
    embeddings     Cosine, weighted mean (numpy-free)
    providers/     Local (MiniLM), Mock (hash-based), registry
    services       Resale pipeline orchestration
    serializers    DRF serializers for auction/match/resale
  returnprevention/  Pre-purchase guards
    rules          Deterministic size/compatibility checks
    llm            LLM compatibility caller
    prompts        LLM compatibility prompt templates
    services       Fit-check + compatibility orchestration
  greencredits/    Account, transactions, rewards store + management
                   command (seed_greencredits)
  sellerportal/    Seller rules + auto-disposition
  facility/        Storage engine (engine.py), intake, relist, watchlist,
                   management command (accrue_storage). No models — operates
                   on catalog.ItemUnit and marketplace.Listing.
  services/ai      Legacy deterministic mock grader/pricer

frontend/
  src/pages/       Shop, ProductPage, PreLoved, Orders, Resell,
                   NextOwner, HealthCard, Rewards, Profile,
                   SellerPortal, FacilityPortal, Login, Register
  src/components/  PhotoPicker, Toast, ConfirmModal, ProductCarousel,
                   ResaleAlerts, icons
  src/lib/         motion (countUp, scroll detection),
                   image (EXIF extraction, compression, preparePhoto)
  src/auth.jsx     Session-based auth context
  src/api.js       Fetch wrapper with retry + CSRF
  src/styles.css   Global stylesheet (vanilla CSS)

images/            Seed product photos (25 JPEGs)
.kiro/
  specs/orbit-platform/   Authoritative spec (requirements/design/tasks)
  steering/               product.md, tech.md, structure.md
```

## Conventions

- **Django apps are vertical slices.** Each capability is its own app with `models.py`, `views.py`, `urls.py`, and (where async) `tasks.py`. Keep cross-app coupling in explicit service/engine modules, not in views.
- **URL mounting** is centralized in `config/urls.py` under `/api/...`. New endpoints register through an app's `urls.py`.
- **Engines vs views.** Views stay thin: validate input, call an engine/service, serialize. Decision logic (grading blend, route EV, matching, pricing, auction) lives in dedicated modules and must be unit-testable without HTTP.
- **AI providers** follow the `providers/` + `registry.py` pattern: a `base` interface, one module per backend, a `mock` deterministic fallback, and a registry that resolves from settings and caches per process.
- **Determinism for tests.** Anything calling a model must have a deterministic mock path so the offline test suite stays green.
- **Base models.** `TimeStamped` (created_at/updated_at) and `StatefulItem` (adds state, state_changed_at, transition helper that appends UnitEvents) are in `core/models.py`.
- **Frontend** is a Vite SPA: pages in `src/pages/`, reusable UI in `src/components/`, all network through `src/api.js`, auth state through `src/auth.jsx`. Served as static assets behind Nginx, which reverse-proxies `/api` and `/media`. A `docker-compose.dev.yml` overlay swaps Nginx for a Vite dev server with HMR.

## Where to make changes

- New buyer/seller/facility behavior → the matching Django app + its `urls.py`, plus a page/component in the frontend.
- New AI capability → a new source/provider under the relevant app's `providers/`, wired through its registry and chord, with a mock fallback.
- New tunable → add to `config/settings.py` (env-overridable) and reference it; do not hard-code.
- Behavior questions → defer to `.kiro/specs/orbit-platform/requirements.md`.
