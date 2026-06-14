# Orbit — The Intelligent Bridge for Product Second Lives

**Team:** Code404  
**Theme:** Resale  
**Deployed:** https://d3lm4idrl3uau7.cloudfront.net/

---

## The Problem

Millions of returned or unused products are written off every year. A pair of shoes returned from 600 km away costs more in reverse logistics than it is worth — liquidated. A perfectly functional baby monitor sits in a drawer because classifieds mean strangers and haggling. A small seller processes 200 "didn't match" returns a month — all fine — but manually inspects, guesses prices, and re-photographs each one on a phone.

There is no intelligent bridge between a returned product and its next owner.

---

## What Orbit Does

Orbit is a full-stack platform that closes the loop on returned, unused, and outgrown products. Every item that enters the system is automatically graded, priced, routed to its optimal disposition, and matched to the buyer who wants it most — with sustainability incentives at every step.

The system handles six interconnected problems as one cohesive pipeline:

1. AI condition grading from buyer-uploaded photos (under 2 seconds, no manual inspection)
2. Smart routing that decides resell / refurbish / peer-to-peer / donate per item
3. A trust layer ("Product Health Card") so the next buyer knows exactly what they are getting
4. Return prevention that catches wrong-size and incompatible purchases before they happen
5. Peer-to-peer resale with personalized buyer matching and a descending-price auction
6. Green credits that reward sustainable behaviour at every touchpoint

---

## Consumer Centric Approach

Every design decision in Orbit traces back to removing friction for real people — the buyer who hesitates to trust a refurbished product, the seller drowning in returns, and the facility operator guessing where to send each item.

### The buyer never sees uncertainty

When a buyer opens a pre-loved listing, the Product Health Card shows them the AI-verified grade, the confidence score, how much warranty remains, the full audit history of every state transition, and the AI disposition reasoning. This is not a static label — it is a live document powered by the `UnitEvent` append-only trail (`catalog/models.py:UnitEvent`) and the warranty calculator (`catalog/warranty.py`) that parses free-text warranty strings, anchors them to the original purchase date, and renders a human-readable remaining duration using calendar-accurate arithmetic.

The Pre-Loved shop (`frontend/src/pages/PreLoved.jsx`) separates items into a "Recommended for you" rail — products the matching engine has scored highest for this buyer based on their taste vector, budget, category affinity, and green-buying propensity — and a general grid. The price on each card animates downward in real time (3-second polling) as the Dutch auction steps, and the green-credit bonus grows inversely with price, so hesitant buyers are nudged exactly when the deal gets better.

### Returns are prevented, not just processed

Before a purchase is confirmed, `marketplace/views.py:place_order` runs two pre-purchase guards:

- **Fit guide** (`returnprevention/services.py:fit_guide`): For apparel and footwear, the buyer's declared sizes from `User.profile["sizes"]` are matched against the product's `size_options`. The system recommends the closest size and warns if the buyer picks a different one. No LLM, no latency — pure lookup.
- **Accessory compatibility** (`returnprevention/services.py:get_compat`): For accessories with a `compatible_model` attribute, an LLM checks the buyer's order history for device conflicts (e.g., owns iPhone 15, buying iPhone 14 case). The verdict is cached in Redis per (user, product) and precomputed in parallel on login (`returnprevention/tasks.py:precompute_for_user`) so the buy path is instant.

A deterministic rules engine (`returnprevention/rules.py`) acts as both the offline fallback and a guard against LLM false positives: cross-family warnings (owning an iPhone while buying a Galaxy case) are suppressed regardless of what the LLM returned. Only genuine same-line conflicts surface.

### The "keep it" offer respects the buyer's time

When the rerouting engine determines that every disposition route loses money, but the item is genuinely usable and fraud is low, it generates a return-prevention offer (`rerouting/strategies.py:maybe_offer`): a partial cash refund plus green credits. The split is cash-majority (60/40 by default) so the customer feels fairly compensated. The offer is capped at the loss the company would otherwise take and only surfaces when `fraud < 0.3` and `quality >= 0.4`. The buyer accepts or declines from the Orders page; accepting atomically awards real credits, marks the order PREVENTED, and the unit never ships back.

### The seller gets automation, not another dashboard

Sellers define simple rules (`sellerportal/models.py:SellerRule`): "if grade >= B and recovery >= 60%, auto-relist." The `bulk_apply` endpoint runs all active rules across the inbox in one call. Every relist flows through the Next Best Owner engine — the seller never prices or photographs again.

---

## Scalability

Orbit is built as a production system, not a prototype. Every AI call, every matching run, and every auction step is designed to fail gracefully under load.

### Async-first with graceful inline fallback

The grading pipeline (`grading/tasks.py`) fans four independent sources — VLM, perceptual-hash similarity, EXIF metadata analysis, buyer history — out as parallel Celery subtasks using a chord. The aggregate callback blends them into a single verdict. If the broker goes down, the chord dispatch catches the exception and runs the full pipeline inline (`orchestrator.run_all_sync`) so grading never breaks.

The rerouting engine (`rerouting/tasks.py`) uses the same chord pattern: EV optimizer and LLM strategy run in parallel, finalize blends them. The Next Best Owner handoff (`nextowner/tasks.py:price_and_match`) precomputes every candidate buyer's demand profile in parallel via a chord before finalizing pricing and matching.

Every task is wrapped in a `try/except` that returns an empty partial rather than sinking the chord. A failing VLM does not break hash comparison. A failing LLM does not break the EV fallback.

### Provider abstraction — add capacity without code changes

Adding a new AI provider is a settings entry, not a new call site:

```python
# config/settings.py
LLM_PROVIDERS = {
    "gemini": {"base_url": "...", "api_key": "...", "model": "gemini-2.5-flash"},
    "openai": {"base_url": "...", "api_key": "...", "model": "gpt-4o-mini"},
    "modal":  {"base_url": "...", "api_key": "...", "model": "..."},
}
```

The registries (`grading/providers/registry.py`, `nextowner/providers/registry.py`, `rerouting/llm.py`, `returnprevention/llm.py`) resolve the provider from settings at runtime, cache the instance per-process, and fall back to deterministic mocks on any failure. The OpenAI-compatible VLM client (`grading/providers/openai_compat.py`) handles three degradation cases without falling back to the mock: if a model rejects `reasoning_effort`, the knob is dropped and remembered; if it rejects `json_schema`, the response format degrades to `json_object`; both are remembered per-worker-process so subsequent calls skip the failed round-trip.

### Embedding infrastructure designed for scale

Text embeddings for the matching engine run on the Celery worker, never in the web process. The `LocalTextEmbedding` provider (`nextowner/providers/local.py`) loads the MiniLM model once per process behind a thread lock and encodes in batches. The import of `sentence-transformers` (and transitively `torch`) is deferred to construction time, so the web server and the mock path never pull in 500 MB of dependencies.

Product vectors and demand profiles are cached in PostgreSQL (`nextowner/models.py:ProductVector`, `DemandProfile`) keyed by the provider name that built them. If the embedding model changes, stale vectors are automatically rebuilt on next access. The brute-force cosine over same-locality candidates is sufficient at current scale; the architecture (provider + cache + precompute) maps directly onto pgvector/ANN or a hosted embedding service when volume demands it.

### Storage and media

Media storage switches between local volume and S3 via a single environment variable (`USE_S3=1`). The `STORAGES` dict in settings, `django-storages[s3]`, and a CloudFront custom domain handle the rest. The Docker Compose mounts a shared media volume between the web and worker containers so grading can read the buyer's uploaded photos without network round-trips in the local case.

### The Dutch auction is self-rescheduling

`nextowner/tasks.py:step_auction` lowers the price one notch, widens the alert to the next buyer tier, and — if the auction is still active — schedules itself again with `apply_async(countdown=interval_seconds)`. No Celery Beat, no cron, no periodic sweep. Each auction manages its own lifecycle. The `select_for_update` row lock prevents duplicate or early triggers from corrupting state.

### Infrastructure

```
docker-compose.yml:
  db       → PostgreSQL 16
  redis    → Redis 7 (broker + cache + sessions)
  backend  → Gunicorn (configurable workers)
  worker   → Celery (configurable concurrency)
  frontend → Nginx (static SPA + reverse proxy)
```

The backend boots idempotently: migrate, collectstatic, conditional seed (`SEED_ON_BOOT=1`), then serve. The worker auto-discovers tasks from every app's `tasks.py`. Session storage uses `cached_db` so it scales by swapping the cache backend alone.

---

## Novelty

### Multi-source grading with cross-source fraud detection

Most grading systems run a single model and trust its output. Orbit runs four independent sources in parallel and blends them with explicit weights, cross-source agreement scoring, and a "decisive wrong item" floor.

The scoring engine (`grading/scoring.py:blend`) computes a per-source fraud signal:

- **VLM**: Did the model detect a wrong item or manipulation flags?
- **Perceptual hash + colour histogram** (`grading/providers/phash.py`): Does the uploaded image structurally and chromatically match the reference? The colour histogram catches the swap a dHash alone misses — a blue phone and a silver phone of the same shape hash identically in grayscale, but their colour signatures diverge sharply.
- **EXIF metadata** (`grading/metadata.py`): Was the image edited in Photoshop? Is it a screenshot (PNG, no camera EXIF)? Does the capture timestamp predate delivery? Do the declared dimensions mismatch the stored bytes?
- **Buyer history** (`grading/history.py`): What is this buyer's return rate and pattern?

These signals are weighted, renormalized over whichever sources are available (so a missing reference image doesn't zero the score), and a stated-reason-vs-observation cross-check adds a fifth signal (e.g., buyer claims "defective" but VLM sees pristine condition).

The decisive override: when a real (non-mock) VLM with confidence >= 0.6 reports that the returned item does not match the listed product, the blended fraud score is floored at 0.6 regardless of what weaker sources say. This prevents a colour-blind hash, clean history, and benign return reason from diluting a clear substitution into a deceptively low number.

### Risk-adjusted routing economics

The rerouting cost model (`rerouting/costs.py`) does not simply pick the route with the highest nominal value. It multiplies revenue by a realization probability:

```
realize = sell_through(quality) * (1 - fraud_risk)
expected_revenue = nominal_value * realize
```

This means a grade-A item with zero fraud risk realizes nearly 100% of its value through resale, while a suspicious item with doctored photos sees its resale revenue discounted toward zero — making DONATE (the risk-immune floor with no revenue but minimal cost) the rational choice. Without this adjustment, RESELL would always win on paper regardless of how damaged or fraudulent the item is.

Logistics costs scale with item physics: `rate_per_km[size_class] * fragility_mult[fragility]`. A delicate refrigerator moving 800 km inter-city costs 18x per km what a rigid phone case costs locally. These classifications are derived by the VLM from the product category and title, persisted as durable attributes on the product (`grading/orchestrator.py:_persist_grader_attributes`), and reused by all future assessments and routing decisions without re-running the model.

### Bipartite demand matching with five behavioural signals

The Next Best Owner matching engine (`nextowner/matching.py`) scores every candidate buyer against a resale product using five learned signals:

1. **Semantic taste** (0.45 weight): Cosine similarity between the buyer's recency-weighted purchase embedding (their "taste vector") and the product's text embedding. Cold-start buyers get 0.5 (neutral) rather than being excluded.
2. **Category affinity** (0.20): Normalized histogram of categories the buyer has purchased, weighted by recency (half-life 45 days).
3. **Price fit** (0.20): Gaussian kernel over the buyer's historical spend mean/std — a buyer who typically pays 2000 for electronics scores low on a 8000 item.
4. **Quality fit** (0.10): Grade tolerance — everyone prefers A, but this signal lets the auction target buyers who have historically accepted B/C grade items.
5. **Green propensity** (0.05): Derived from the buyer's green-credit transaction history — how often they buy pre-loved, how engaged they are with the sustainability system.

Buyers are ranked, bucketed into tiers (default 3 per tier, 4 tiers), and the Dutch auction alerts one tier per price step. The best-fit buyers see the item first at the highest price; as the price drops, progressively less-aligned buyers are notified, each seeing a growing green-credit bonus.

### The Dutch auction as a price-discovery mechanism

Traditional resale platforms ask the seller to guess a price. Orbit's descending-price auction (`nextowner/auction.py`) starts at a premium above fair value and steps down automatically, combining price discovery with urgency:

- The opening ask is `est_value * (1 + 0.25)` — above the fair band.
- The reserve is `est_value * (1 - 0.30)` — below the fair band.
- Each step drops the price by 12% and alerts one more buyer tier.
- The green-credit bonus is 0 at the ceiling and grows linearly to 40 credits at the floor.

This is not a gimmick — it solves the cold-start pricing problem. If the top-tier buyers (highest match score) buy at a high price, the seller gets a premium. If they don't, the price descends to where demand exists, and the credit bonus compensates the buyer for accepting a less-perfect match. The seller never guesses; the market finds the price.

### Warranty transfer as a trust primitive

When a buyer resells an item they purchased on the platform, Orbit anchors the warranty clock to the original delivery date (`nextowner/services.py:start_resale_from_order` sets `unit.purchased_at` from `order.delivered_at`). The Health Card then computes remaining warranty using calendar-accurate relativedelta arithmetic, so "1 year warranty" starting April 15 expires exactly April 15 next year, not 365 days later. This transfers verifiable manufacturer warranty to the next buyer — something no classifieds platform can offer.

### Return prevention that runs at zero latency on the buy path

The compatibility verdicts are precomputed on login (`returnprevention/tasks.py:precompute_for_user`), fanned out as a Celery group across every purchasable accessory, and cached in Redis with a configurable TTL (default 1 hour). By the time the buyer clicks "Buy," the verdict is a cache hit. The fit guide is a pure in-memory lookup with no async or network dependency. The combined gate (`purchase_warnings`) adds zero perceivable latency to the purchase flow.

---

## Architecture Diagram

```
                         +------------------+
                         |   React SPA      |
                         |   (Vite/Nginx)   |
                         +--------+---------+
                                  |
                         +--------+---------+
                         |   Django + DRF   |
                         |   (Gunicorn)     |
                         +--+-----+-----+--+
                            |     |     |
              +-------------+  +--+--+  +-------------+
              |                |     |                 |
     +--------v------+  +-----v--+  +-----v------+   |
     | PostgreSQL 16 |  | Redis 7|  | S3/Volume  |   |
     +---------------+  +--------+  +------------+   |
                                                      |
                         +----------------------------v--+
                         |       Celery Worker           |
                         |  (grading, rerouting,         |
                         |   nextowner, returnprev)      |
                         +--+--------+--------+---------+
                            |        |        |
               +------------+  +-----+-----+  +----------+
               | VLM (Gemini/  | Embeddings |  | LLM (route
               |  OpenAI/Mock) | (MiniLM/   |  |  decision/
               +---------------+  Mock)     |  |  compat)
                                +-----------+  +----------+
```

---

## Tech Stack

| Layer      | Technology                                                                                                               |
| ---------- | ------------------------------------------------------------------------------------------------------------------------ |
| Backend    | Django 5.x, Django REST Framework, Celery 5.3, PostgreSQL 16, Redis 7                                                    |
| Frontend   | React 18, Vite, React Router, vanilla CSS                                                                                |
| AI/ML      | OpenAI SDK (Gemini 2.5 Flash, GPT-4o-mini compatible), sentence-transformers (MiniLM-L6-v2), Pillow (perceptual hashing) |
| Infra      | Docker Compose, Gunicorn, Nginx, WhiteNoise, django-storages (S3)                                                        |
| Deployment | AWS (CloudFront + S3 static, EC2/ECS backend, RDS, ElastiCache)                                                          |

---

## Repository Structure

```
backend/
  config/          Settings, URLs, Celery app, WSGI
  core/            User model, auth, permissions, uploads, seed command
  catalog/         Product, ItemUnit, UnitEvent, warranty math
  marketplace/     Listing, Order, return flow, return-window policy
  grading/         Multi-source AI grading pipeline
    providers/     VLM (OpenAI-compat, Bedrock, Mock), PHash embedding
    orchestrator   Source runners + aggregate
    scoring        Multi-source blend + fraud floor
    prompts        Strict JSON schema for constrained VLM output
  rerouting/       Disposition engine (EV + LLM, parallel)
    costs          Risk-adjusted profit model
    optimizer      Argmax over routes
    strategies     Build context, finalize, keep-it offer
    geo            Haversine distance, Indian city centroids
  nextowner/       P2P resale: matching + Dutch auction
    matching       5-signal bipartite scoring
    pricing        Quality-depreciation-fraud formula
    auction        Dutch auction: start, step, buy, rematch
    profiles       Demand profile builder (taste + budget + green)
    products       Product vector cache
    embeddings     Cosine, weighted mean (numpy-free)
    providers/     Local (MiniLM), Mock (hash-based)
  returnprevention/  Pre-purchase guards
    services       Fit guide + compatibility gate
    rules          Deterministic same-family conflict detection
    llm            LLM compatibility check
  greencredits/    Account, transactions, rewards store
  sellerportal/    Seller rules + auto-disposition
  facility/        Storage engine, intake, relist, watchlist
  services/ai      Legacy deterministic mock grader/pricer

frontend/
  src/pages/       Shop, PreLoved, Orders, Resell, HealthCard, Rewards,
                   Profile, SellerPortal, FacilityPortal
  src/components/  PhotoPicker, Toast, icons, modals
  src/lib/         Motion utilities (countUp, scroll detection)
  src/auth.js      Session-based auth context
  src/api.js       Fetch wrapper with retry + CSRF
```

---

## Running Locally

```bash
cd backend
cp .env.example .env        # fill in POSTGRES_PASSWORD at minimum
docker compose up --build   # starts db, redis, backend, worker, frontend
```

The backend auto-migrates, seeds demo data (25 products with real photos, 5 users with size profiles and geo coordinates), and serves on port 80 via the frontend's nginx.

To run with real AI grading, set `GEMINI_API_KEY` in `.env`. Without it, the system runs fully offline using deterministic mocks — every flow works, every test passes, no network required.

### Running Tests

```bash
docker compose exec backend python manage.py test grading rerouting returnprevention
```

All tests run with `CELERY_TASK_ALWAYS_EAGER=1` and mock providers. No external dependencies, no flakiness.

---

## Key Design Principles

1. **No single source trusted.** The grading system blends four independent signals. A doctored photo, a false return reason, or a clean history alone cannot produce a fraudulent verdict.

2. **Graceful degradation everywhere.** Every AI call has a deterministic fallback. The system works identically with zero API keys configured — a degraded similarity still beats a 500 error.

3. **Configuration over code.** Adding a VLM provider, changing match weights, tuning the auction step percentage, or adjusting the fraud-risk discount — all are settings changes, not pull requests.

4. **The unit is the atom.** One physical `ItemUnit` flows through its entire lifecycle — NEW, SOLD, RETURN_PENDING, AT_FACILITY, RELISTED, SOLD again — accumulating an immutable event trail. The Health Card is a direct read of this trail.

5. **Economics are explicit.** Every routing decision comes with a per-route profit breakdown, the inputs that produced it, the realization probability, and the decision source (LLM or EV). Auditable, explainable, tunable.

---

## What Makes This Different

This is not a marketplace with an AI label on top. The AI is structural:

- The grading system does not produce a letter grade from a single model call. It runs four sources, cross-checks the buyer's stated reason against observations, detects colour swaps that perceptual hashes miss, flags screenshots and edited images from EXIF metadata, and floors the fraud score when a confident VLM reports a substitution.

- The routing system does not pick the highest-value route. It risk-adjusts revenue by quality and fraud, charges realistic logistics costs scaled by item physics and geography, and only offers "keep it" when the math says returning the item costs more than bribing the customer — and when the customer is unlikely to be a fraudster.

- The matching system does not recommend "similar products." It embeds the buyer's entire purchase history into a taste vector, computes budget fit as a Gaussian, measures green-buying propensity from credit transactions, and uses all five signals to rank buyers into alert tiers for a descending-price auction that discovers the market price without anyone guessing.

- The prevention system does not show a generic "are you sure?" modal. It knows the buyer's waist size, knows they own an iPhone 15, and only warns when the specific accessory they are buying fits an iPhone 14 — suppressing false positives across device families with a deterministic guard.

Every claim above maps to a specific file and function in this repository.
