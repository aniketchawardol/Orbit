# Implementation Plan: Orbit Platform

## Overview

The Orbit platform lives at `d:\return-resale-ai\repo`, with the Django backend under `backend/` and the React SPA under `frontend/`. All file paths below are relative to that repo root.

The implementation is **complete** — every task below has been built, tested, and verified. This document serves as the authoritative build record, tracing each implemented component back to its design rationale and requirement references.

Build order followed dependencies: backend project scaffold → identity/core → deterministic fallback helpers → catalog → green credits → the four AI engines (grading, rerouting, next-owner, return-prevention) → marketplace (the integration hub) → seller/facility portals → frontend SPA → final settings/URL wiring, migrations, and the full offline test suite.

Testing is example/integration-based (Django `TestCase`/`SimpleTestCase`), run fully offline with `CELERY_TASK_ALWAYS_EAGER=1` and forced mock providers — the design explicitly opts out of property-based testing. Test sub-tasks are marked with `*`.

## Tasks

- [x] 1. Backend project scaffold and infrastructure
  - [x] 1.1 Create the Django project skeleton and dependencies
    - Create `backend/manage.py`, `backend/config/__init__.py` (exposing the Celery app), `backend/config/wsgi.py`, and `backend/config/celery.py` (Celery app that auto-discovers each app's `tasks.py`)
    - Create `backend/requirements.txt` pinning Django 5.x, djangorestframework, celery 5.3, redis, psycopg, Pillow, python-dateutil, django-storages[s3], whitenoise, gunicorn, openai
    - _Requirements: 23.1, 23.3_
  - [x] 1.2 Write base `config/settings.py`
    - Configure `AUTH_USER_MODEL = "core.User"`, DRF `SessionAuthentication` + CSRF + `IsAuthenticatedOrReadOnly` default, `cached_db` sessions, `SECURE_PROXY_SSL_HEADER`, `SECURE_COOKIES` flag handling
    - Configure PostgreSQL, Redis cache/broker (with local-memory fallback when `REDIS_URL` unset), media (local volume default, S3 when `USE_S3=1`), WhiteNoise static, `TIME_ZONE="Asia/Kolkata"`, `USE_TZ=True`, `CELERY_TASK_ALWAYS_EAGER`, the `LLM_PROVIDERS` table (gemini/openai/modal), and the per-app `LOG_LEVEL` logging config
    - Leave `INSTALLED_APPS` and the full business-knob block to task 14.1 (apps reference knobs via `getattr(settings, …, default)`)
    - _Requirements: 1.13, 1.15, 1.16, 1.17, 21.1, 23.7, 23.8, 23.10_
  - [x] 1.3 Write base `config/urls.py`
    - Mount Django admin and media/static serving; leave per-app `/api/...` includes to task 14.2
    - _Requirements: 23.1_
  - [x] 1.4 Author container and environment files
    - Create `backend/Dockerfile`, `backend/docker-compose.yml`, `backend/docker-compose.dev.yml`, `backend/.env.example`, `backend/.dockerignore`
    - Compose services: PostgreSQL 16, Redis 7, Gunicorn backend (`GUNICORN_WORKERS` default 3), Celery worker (shared media volume), and the entrypoint that migrates with retry, collects static, conditionally seeds on `SEED_ON_BOOT=1`, then serves
    - _Requirements: 23.1, 23.2, 23.4_

- [x] 2. core app — identity, auth, permissions, uploads
  - [x] 2.1 Implement `core/models.py`
    - `Roles` (BUYER/SELLER/FACILITY), `User(AbstractUser)` with `role` (default BUYER), JSON `profile` (default `{}`), `city`, nullable `lat`/`lng`; abstract `TimeStamped`; abstract `StatefulItem` with `state`, `state_changed_at`, `unit_ref()`, and the `transition()` method that flips state, saves, and appends an immutable `UnitEvent` when `unit_ref()` is non-null
    - _Requirements: 1.1, 1.2, 3.6, 3.7_
  - [x] 2.2 Implement `core/permissions.py`
    - `IsSeller` (authenticated + role SELLER) and `IsFacility` (authenticated + role FACILITY)
    - _Requirements: 1.14_
  - [x] 2.3 Implement `core/uploads.py`
    - `ALLOWED_EXT`, `MAX_BYTES` (8 MiB), `MAX_PHOTOS` (6); `validate_image(f)` (case-insensitive extension check with "unknown" fallback, size check); `save_photos(files, subdir)` (enforce 6-photo cap before persisting, store under `<subdir>/<uuid4hex><ext>` via `default_storage`, return media-relative paths in upload order)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [x] 2.4 Implement `core/views.py` and `core/urls.py`
    - `register` (role-check → presence-check → uniqueness-check ordering with 400/400/409), `login_view` (401 / session + payload), `logout_view` (204), `me` (200 with user|null); `_user_payload` (id, username, role, email, names, city, lat, lng, profile, date_joined, green-credit balance defaulting 0); `_precompute_return_prevention` enqueues the task and swallows broker errors
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12_
  - [x] 2.5 Add `core/admin.py`, `core/apps.py`, and `core/migrations` (User + city/lat/lng)
    - _Requirements: 1.1, 1.2_
  - [x] 2.6 Implement `core/management/commands/seed_demo.py` and `refresh_product_images.py`
    - Idempotent seed (guard on `username="seller1"`): buyers across `rerouting.geo.CITY_COORDS`, a seller, a facility operator, an admin superuser, size profiles, a 25-product catalog from `images/` with branded-placeholder fallback, NEW listings per stock unit, units across lifecycle states, seller rules, demo orders, starting green-credit balances; call `seed_rewards()` unconditionally. `refresh_product_images` re-attaches catalog photos
    - _Requirements: 23.9_
  - [x]\* 2.7 Write unit tests for core
    - Auth ordering (400 role → 400 presence → 409 uniqueness), `me` authed/anon, upload validation (extension/size/cap), `transition()` event append
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.10, 2.1, 2.2, 2.3, 2.4, 3.6, 3.7_

- [x] 3. services app — deterministic fallback AI helpers
  - [x] 3.1 Implement `services/__init__.py` and `services/ai.py`
    - Network-free, deterministic `grade()` heuristic (untouched claim + return photos), `price()` (est value + fair-value band from MRP and grade), and `fit_check()`; identical output for identical input
    - _Requirements: 24.1, 24.2, 24.3_
  - [x]\* 3.2 Write unit tests for `services/ai`
    - Determinism and grade/price boundaries
    - _Requirements: 24.1, 24.2, 24.3_

- [x] 4. catalog app — Product, ItemUnit, event trail, warranty
  - [x] 4.1 Implement `catalog/models.py`
    - `ProductOrigin`, `Product`, `UnitStates`, `ItemUnit(StatefulItem)` (grade, grade_confidence, untouched, est_value, purchased_at, arrived_at_facility, storage_cost_accrued, owner; `save()` defaults state NEW; `unit_ref()` returns self), `UnitEvent` (ascending `created_at` ordering, append-only)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [x] 4.2 Implement `catalog/warranty.py`
    - `warranty_expiry(purchased_at, text)` (first `(\d+)\s*(year|month|week|day)`, relativedelta for years/months, timedelta for weeks/days, None on the documented guards), `warranty_remaining_label(product, purchased_at)` (floor to whole years ≥1y else whole months, None rather than "0 months")
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - [x] 4.3 Implement `catalog/serializers.py`
    - `ProductSerializer` (`image_url`/`thumbnail_url` with newest-ACTIVE-listing first-photo fallback), `UnitEventSerializer`, `ItemUnitSerializer` (nested product + events + `routing_recommendation` dropped when `include_routing` is False)
    - _Requirements: 3.11, 11.1, 11.2_
  - [x] 4.4 Implement basic catalog views and `catalog/urls.py`
    - `product_list` (newest first, optional `q` icontains over title/description, optional exact `category`, cap 60), `product_detail` (+ ACTIVE listings, 404), `product_related` (≤12 same-category newest excluding self, 404), `product_fitcheck` (delegates to `services.ai.fit_check`)
    - _Requirements: 3.8, 3.9, 3.10_
  - [x] 4.5 Add `catalog/admin.py`, `catalog/apps.py`, and migrations (initial + origin + purchased_at)
    - _Requirements: 3.1, 3.3_
  - [x] 4.6 Implement Health Card and pre-loved views (extend `catalog/views.py`/`urls.py`)
    - `unit_health_card` (public, `include_routing=False`, `current_price` from active auction else active listing, `warranty_remaining`, full ascending event trail), `preloved_list` (active `ResaleAuction` cards with per-user `recommended` from `MatchEdge`) — reads nextowner models via local import
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 3.11_
  - [x]\* 4.7 Write unit tests for catalog
    - Warranty math (calendar vs exact, floors, omissions), product list filters + cap, health card public access + price resolution + routing field hidden
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 3.8, 3.9, 3.10, 11.1, 11.2, 11.3, 11.6_

- [x] 5. greencredits app — account, transactions, rewards
  - [x] 5.1 Implement `greencredits/models.py`
    - `Account` (balance ≥ 0), append-only `Transaction` (signed amount, ≤30-char type, ≤200-char description, optional positive reference id), `Reward` (title, description, positive cost, icon, active), `RewardClaim`
    - _Requirements: 18.1_
  - [x] 5.2 Implement `greencredits/logic.py`
    - `award(user, amount, type, description, ref_id)` (create account if missing, increase balance, append one transaction), `spend`/claim helper, and idempotent `seed_rewards()` default catalog
    - _Requirements: 18.2, 18.3, 18.7_
  - [x] 5.3 Implement `greencredits/serializers.py`, `views.py`, `urls.py`
    - Balance (current, total earned, total spent, impact stats), history (≤50 newest first), rewards list, claim (atomic deduct + negative txn + claim; 400 with shortfall when insufficient; 404 when missing/inactive)
    - _Requirements: 18.5, 18.6, 18.8, 18.9, 18.10_
  - [x] 5.4 Add `greencredits/admin.py`, `apps.py`, `management/__init__.py`, and migrations
    - _Requirements: 18.1_
  - [x]\* 5.5 Write unit tests for greencredits
    - Award creates account + transaction, balance floor, history cap/order, claim success/insufficient/missing
    - _Requirements: 18.2, 18.5, 18.6, 18.8, 18.9, 18.10_

- [x] 6. grading app — multi-source AI condition grading
  - [x] 6.1 Implement `grading/models.py`
    - `AssessmentContext`, `AssessmentStatus`, `ImageRole`, `GradingAssessment` (order FK as string `marketplace.Order`, raw per-source signals, blended scores, indexes/ordering), `GradingImage` (path/role/client+server metadata/phash/embedding_ref/notes/quality)
    - _Requirements: 7.1, 7.2_
  - [x] 6.2 Implement `grading/providers/base.py` and `grading/providers/registry.py`
    - `GradingImageData`, `VLMRequest`, abstract `VLMProvider.grade`/`EmbeddingProvider.compare`; registry resolves from settings, caches per process, never raises, auto order gemini→openai→modal else mock, `_is_usable` (model + api_key or keyless self-hosted base_url)
    - _Requirements: 21.2, 21.3, 21.4, 21.5_
  - [x] 6.3 Implement `grading/providers/mock.py`
    - `MockVLM` deterministic reason-aware verdict seeded by product+reason; derives size_class/fragility/category; provider name `"mock"`; output matches the real VLM schema
    - _Requirements: 7.8, 24.4_
  - [x] 6.4 Implement `grading/providers/openai_compat.py`, `bedrock.py`, `modal.py`
    - `OpenAICompatVLM` (single OpenAI-SDK client; json_schema → json_object degradation; drop `reasoning_effort` on 400; remember both per process; ≤1 transport retry, ≤3 attempts; configured timeout); `bedrock` stub; `modal` optional CLIP embedding falling back to phash
    - _Requirements: 7.8, 21.6, 21.7, 21.8, 21.9_
  - [x] 6.5 Implement `grading/providers/phash.py`
    - `PHashEmbedding`: 64-bit dHash + coarse RGB colour histogram (colour weight 0.45); `compare` returns best `overall`, per-image phashes, duplicate pairs at dHash ≥ 0.96; caches reference signatures
    - _Requirements: 7.9_
  - [x] 6.6 Implement `grading/prompts.py` and `grading/jsonio.py`
    - `SYSTEM_PROMPT`, `grade_schema()`, `build_vlm_messages` (text + base64 image_url parts), `normalize_vlm_output`; `extract_json` tolerant parser
    - _Requirements: 7.4, 24.4_
  - [x] 6.7 Implement `grading/metadata.py`
    - `server_metadata_from_bytes`, `analyze_image` (weighted flags stale_capture 0.5, future_capture 0.5, software_edited 0.4, dimension_mismatch 0.4, is_screenshot 0.35, no_capture_time 0.15, no_camera_exif 0.15, low_resolution 0.1 below 230,400 px; clamp [0,1]), `summarize` = 0.6×worst + 0.4×mean
    - _Requirements: 7.10_
  - [x] 6.8 Implement `grading/history.py`
    - `analyze(buyer_id, exclude_order_id)`: cap 0.3 when < 3 prior orders, else 0.6×min(rate,1) + 0.4×min(recent_30d/3,1); never raises
    - _Requirements: 7.11_
  - [x] 6.9 Implement `grading/scoring.py`
    - `blend(...)`: quality = clamped VLM estimate; five fraud signals (VLM 0.0/0.6 + 0.15·flags capped +0.4; similarity; metadata; history; reason-mismatch 0.5 via `_reason_mismatch`); weights VLM 0.30 / similarity 0.25 / metadata 0.20 / history 0.15 / reason-mismatch 0.10 renormalized over present signals; real-VLM `item_matches_reference=False` with confidence ≥ 0.6 floors fraud at 0.6; confidence blend (self-confidence ×0.6 if not real, availability, 1−stdev agreement); grade = worse of VLM grade and quality-derived grade; explainable `scores`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_
  - [x] 6.10 Implement `grading/orchestrator.py`
    - `run_vlm`/`run_similarity`/`run_metadata`/`run_history` keyed by assessment id; `aggregate(aid, partials)` merges, calls `scoring.blend`, persists verdict + `latency_ms` (now − created_at), sets DONE, persists grader attributes (real VLM only, merge-preserving), and hands off RETURN→`rerouting.decide_route` / RESALE→`nextowner.price_and_match` (best-effort); `run_all_sync` inline path; `_persist_grader_attributes`
    - _Requirements: 7.3, 7.7, 7.8, 7.12, 7.13, 7.14, 7.15, 3.12_
  - [x] 6.11 Implement `grading/services.py`
    - `create_return_assessment(order, uploaded_paths, client_metadatas)` (PENDING, UPLOADED with index-aligned EXIF, listing photos + product image as REFERENCE, enqueue swallowing broker errors), `create_resale_assessment(...)`, `_reference_paths`
    - _Requirements: 7.1, 7.3_
  - [x] 6.12 Implement `grading/tasks.py`
    - `run_assessment` (eager → `run_all_sync`; else RUNNING + chord of vlm/similarity/metadata/history into `aggregate_subtask`, inline fallback on dispatch failure); each subtask wrapped in `_safe` returning `{}` on error; no image bytes through broker
    - _Requirements: 7.5, 7.6, 7.7_
  - [x] 6.13 Add `grading/admin.py`, `apps.py`, and migrations
    - _Requirements: 7.1, 7.2_
  - [x]\* 6.14 Write tests for grading
    - Blend weights/renormalization, fraud floor override, confidence agreement, metadata flags, history caps, registry never-raises + auto order, mock determinism, eager chord completes < 2000 ms
    - _Requirements: 7.5, 7.6, 7.7, 7.10, 7.11, 7.15, 8.3, 8.4, 21.2, 21.3, 21.5, 24.4_

- [x] 7. rerouting app — disposition engine (EV ∥ LLM) + keep-it offer
  - [x] 7.1 Implement `rerouting/geo.py`
    - `CITY_COORDS` (10 centroids), `FACILITY_CITY="Bengaluru"`, `haversine_km`, `coords_for(user)`, `distance_between(seller, buyer)` with facility fallback
    - _Requirements: 9.1_
  - [x] 7.2 Implement `rerouting/costs.py`
    - Risk-adjusted profit per route: `rate_per_km = RATE_PER_KM[size]·FRAGILITY_MULT[fragility]`, `repair_cost=(1−q)·MRP·REPAIR_FACTOR` capped at `REPAIR_MAX_PCT·MRP`, `sell_through(q)=base+(1−base)·q`, `_realize=sell_through(q)·(1−fraud·fraud_weight)`; two inter-city legs RESELL/REFURBISH, two local P2P, one local DONATE; returns `{routes, inputs}`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [x] 7.3 Implement `rerouting/optimizer.py`
    - `optimize(costs)` argmax profit → `{route, profit, loss, ranking}`
    - _Requirements: 9.6_
  - [x] 7.4 Implement `rerouting/prompts.py` and `rerouting/llm.py`
    - `SYSTEM_PROMPT`, `build_messages` (per-route profit lines + logistics), `decision_schema`; `decide(context, cost)` resolves provider (auto/named else None→EV), parses via `grading.jsonio.extract_json`, validates route ∈ {RESELL,REFURBISH,P2P,DONATE}, json_schema→json_object degradation
    - _Requirements: 9.7, 9.8, 21.2, 21.5_
  - [x] 7.5 Implement `rerouting/models.py`
    - `RouteChoices`, `DecisionStatus`/`StrategyKinds`, `OfferStatus`, `RouteDecision` (OneToOne assessment, order/unit FKs, ev/llm routes, costs + context JSON, error), `ReturnOffer` (OneToOne decision, cash_refund, green_credits, expected_loss, company_cost, message, responded_at)
    - _Requirements: 9.9, 10.1_
  - [x] 7.6 Implement `rerouting/strategies.py`
    - `build_context(assessment)` snapshot → `costs.compute`; `ev_result`, `llm_result`; `finalize(decision, ev, llm_out)` (LLM authoritative else EV, persist, then `maybe_offer`); `maybe_offer` (only when loss > 0, fraud ≤ 0.3, quality ≥ 0.4; make_whole = round(min(paid·(1−q), loss)); cash = round(0.6·make_whole); credits = max(make_whole−cash, 0); company_cost = round(cash + 0.9·credits); PENDING)
    - _Requirements: 9.10, 9.11, 9.12, 9.13, 9.14, 9.15, 10.1, 10.2, 10.3, 10.4, 10.5, 10.10_
  - [x] 7.7 Implement `rerouting/services.py`
    - `recommendation_for(unit)`, `ensure_recommendation_for(unit)` (compute inline from latest DONE assessment, running grading inline if needed), `_shape_recommendation`, `latest_offer`, transactional idempotent `accept_offer` (award credits, order→PREVENTED, unit→SOLD with buyer) and `decline_offer`
    - _Requirements: 10.6, 10.7, 10.8, 10.9, 9.13_
  - [x] 7.8 Implement `rerouting/tasks.py`
    - `decide_route(assessment_id)` (build decision then EV ∥ LLM chord into `finalize_subtask`, inline in eager mode), `decide_route_now` synchronous variant; subtasks return empty partials on error
    - _Requirements: 9.6, 9.7, 9.15_
  - [x] 7.9 Implement `rerouting/views.py` and `rerouting/urls.py`
    - `accept_offer`/`decline_offer` (owner-checked, 404 otherwise; non-PENDING returns current status + balance)
    - _Requirements: 10.6, 10.7, 10.8, 10.9_
  - [x] 7.10 Add `rerouting/admin.py`, `apps.py`, and migrations
    - _Requirements: 9.9, 10.1_
  - [x]\* 7.11 Write tests for rerouting
    - Cost model per route, optimizer argmax, keep-it gating + split + company cost, accept/decline idempotency + ownership 404, EV fallback when no LLM
    - _Requirements: 9.6, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_

- [x] 8. nextowner app — Next Best Owner matching + Dutch auction
  - [x] 8.1 Implement `nextowner/embeddings.py`
    - numpy-free cosine, weighted mean, normalization helpers
    - _Requirements: 14.2_
  - [x] 8.2 Implement `nextowner/providers/` (base, local MiniLM, mock hash-based, registry)
    - Deferred heavy import at construction; worker-only embedding; mock fallback when model can't load; registry caches keyed by provider name
    - _Requirements: 14.11, 23.5_
  - [x] 8.3 Implement `nextowner/models.py`
    - `DemandProfile`, `ProductVector`, `ResaleStatus`, `ResaleRequest`, `ResaleAuction`, `MatchEdge` (with string FKs to catalog/marketplace where needed)
    - _Requirements: 14.9, 14.10, 16.1, 17.1_
  - [x] 8.4 Implement `nextowner/products.py`
    - `ProductVector` cache keyed by embedding-provider name; rebuild when provider differs
    - _Requirements: 14.9_
  - [x] 8.5 Implement `nextowner/profiles.py`
    - Build `DemandProfile` from order + green-credit history (recency-weighted taste vector with 45-day half-life, normalized category/brand histograms, spend mean/std, green propensity = 0.6·preloved-ratio + 0.4·min(1, credits/200), order count); neutral cold-start
    - _Requirements: 14.6, 14.10_
  - [x] 8.6 Implement `nextowner/matching.py`
    - Five signals (semantic taste via (cos+1)/2 with 0.5 cold-start, category affinity, price fit Gaussian with 0.5 neutral, quality fit grade map, green propensity); weights 0.45/0.20/0.20/0.10/0.05; restrict to BUYER role excluding seller + current owner (+ city match unless same-locality demo); rank top K = tier_size×max_tier (12), assign rank + tier = min(rank/tier_size, max_tier−1)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.7, 14.8_
  - [x] 8.7 Implement `nextowner/pricing.py`
    - est_value = int(round(orig × quality_realization × depreciation × fraud_penalty)); quality_realization = rho_min + (rho_max−rho_min)·quality^gamma (0.15/0.75/1.2); depreciation = (1−cat_rate)^age (electronics 0.05/apparel 0.03/footwear 0.035/default 0.03); fraud_penalty = max(0, 1−0.5·fraud); fair-value band ±0.15·(1−confidence) clamped; input clamps + defaults (q 0.5, fraud 0.0, conf 0.6); retain pricing factors
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7_
  - [x] 8.8 Implement `nextowner/auction.py`
    - Open (ceiling = round(est×1.25), floor = round(est×0.70) clamped, tier 0, step 12%, interval 60s, max tier 4); `step` (price = max(round(price·0.88), floor), advance tier, emit alert, refresh bonus); expire only at floor + last tier; row-locked steps skipping early/duplicate triggers unless forced; bonus = round(clamp((ceiling−price)/(ceiling−floor),0,1)·40); `buy` (row-lock auction+listing, verify active + not already owner, transfer unit + create order, auction SOLD, winning edge PURCHASED rest EXPIRED, award buyer 20 + bonus, seller 30, payout-released at int(0.92·price), 409 otherwise); `rematch`
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.7, 16.8, 16.9, 16.10, 16.11, 16.13, 18.4_
  - [x] 8.9 Implement `nextowner/services.py`
    - `price_and_match` (RESALE handoff: price, create USER_RESALE listing at ceiling, unit→RELISTED, match, alert tier 0, schedule first step); resale initiation from order (reuse unit, paid price, catalog reference image, anchor purchase date, DELIVERED order→SETTLED, age months = max(0, days/30)) and external item (EXTERNAL product + NEW unit, no reference); validation (400/404/409 per spec)
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 17.11, 17.12_
  - [x] 8.10 Implement `nextowner/tasks.py`
    - `price_and_match` chord precomputing product vector ∥ candidate demand profiles (best-effort, continue on per-item failure), then price/list/match/alert/schedule; self-rescheduling Dutch stepper with countdown = interval, no auto-advance in eager mode
    - _Requirements: 14.12, 14.13, 16.6_
  - [x] 8.11 Implement `nextowner/serializers.py`, `views.py`, `urls.py`
    - Resell endpoint (201 + context), resale alerts (active-auction alerts ordered by tier then rank, current price + bonus, mark SENT→VIEWED), Dutch buy delegation target, demo force-step and rematch (active auctions only)
    - _Requirements: 16.12, 17.10, 17.12_
  - [x] 8.12 Add `nextowner/admin.py`, `apps.py`, and migrations
    - _Requirements: 14.9, 16.1, 17.1_
  - [x]\* 8.13 Write tests for nextowner
    - Five-signal scoring + cold starts, tiering top-K, pricing formula + band, auction step/floor/expiry/bonus, buy atomicity + awards + 409, resale initiation (order vs external) + warranty anchor + SETTLED, eager no-auto-advance
    - _Requirements: 14.1, 14.2, 14.7, 15.1, 15.5, 16.4, 16.5, 16.8, 16.9, 16.10, 16.11, 17.1, 17.3, 17.4, 17.6, 17.7_

- [x] 9. returnprevention app — fit guide + accessory compatibility
  - [x] 9.1 Implement `returnprevention/rules.py`
    - Apparel-top scale (XS..XXXL) nearest-ordinal and numeric nearest-absolute size selection; deterministic compatibility rules (warn only when buyer owns a same-line device whose variant differs; suppress cross-line)
    - _Requirements: 12.3, 13.4, 13.5_
  - [x] 9.2 Implement `returnprevention/prompts.py` and `returnprevention/llm.py`
    - Compatibility LLM provider resolution + parse; fall back to rules on missing provider/failure/parse error
    - _Requirements: 13.3, 21.2, 21.5_
  - [x] 9.3 Implement `returnprevention/services.py`
    - `fit_guide` (sized detection, read buyer profile size, recommend closest, pure in-memory, null cases), `get_compat` (collect owned devices from order history, LLM-or-rules verdict, suppress unless same-line variant mismatch, cache by (buyer,product) TTL 3600, forced recompute), `purchase_warnings` (size_required / warnings / recommended_size; error → no warning + rules fallback)
    - _Requirements: 12.1, 12.2, 12.4, 12.5, 12.6, 12.7, 13.1, 13.2, 13.5, 13.6, 13.8_
  - [x] 9.4 Implement `returnprevention/tasks.py`
    - `precompute_for_user` (parallel best-effort compatibility verdicts for every purchasable accessory with an ACTIVE listing; broker failure logged, no error)
    - _Requirements: 13.7, 1.12_
  - [x] 9.5 Implement `returnprevention/views.py` and `returnprevention/urls.py`
    - Fit-guide and compatibility read endpoints
    - _Requirements: 12.2, 13.1_
  - [x]\* 9.6 Write tests for returnprevention
    - Closest-size selection (apparel + numeric), null cases, same-line vs cross-line compatibility, cache hit + TTL, rules fallback on LLM failure
    - _Requirements: 12.2, 12.3, 12.7, 13.4, 13.5, 13.6, 13.8_

- [x] 10. marketplace app — listings, purchase, return flow (integration hub)
  - [x] 10.1 Implement `marketplace/models.py`
    - `ListingSources`, `ListingStates`, `Listing(StatefulItem)` (unit FK not OneToOne, source, price, band_lo/hi, photos, lister; defaults ACTIVE; `unit_ref()`), `OrderStates`, `ReturnReasons`, `Order(StatefulItem)` (buyer, listing, chosen_size, return fields, delivered_at; defaults PLACED; `unit_ref()`)
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 10.2 Implement `marketplace/returns.py`
    - `return_window_days(category)` (per-category overrides case-insensitive, default 7), `return_deadline(order)` (delivered_at fallback created_at + days), `buyer_started_resale(order)`, `is_return_eligible(order)`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [x] 10.3 Implement `marketplace/serializers.py`
    - `photo_urls()` (tolerant), `ListingSerializer`, `OrderSerializer` (computed `return_eligible`, `return_deadline`, `prevention_offer` from latest pending `ReturnOffer`)
    - _Requirements: 5.3, 6.4, 11.4_
  - [x] 10.4 Implement `marketplace/views.py` and `marketplace/urls.py`
    - `place_order` (run `returnprevention.purchase_warnings` outside lock: 400 size_required / 409 warnings unless `ack`; delegate auction-backed listings to `nextowner.auction.buy`; else atomic `select_for_update` ACTIVE listing → 409 gone / 409 already owns, transition listing+unit SOLD, set owner, create order, award 20 USER_RESALE + PICKUP_SCHEDULED event / 25 FACILITY_RELIST), `my_orders`, `request_return` (gates 404/409, reason coercion to OTHER, photo validation, per-photo client EXIF from JSON `metadata`, order→RETURN_REQUESTED + unit→RETURN_PENDING, best-effort `create_return_assessment` + 5-credit untouched award), `advance_order` (PLACED→DELIVERED stamping delivered_at / RETURN_REQUESTED→RETURN_RECEIVED, else 409)
    - _Requirements: 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14, 5.15, 5.16, 5.17, 5.18, 5.19, 5.20, 5.21, 5.22, 11.4_
  - [x] 10.5 Add `marketplace/admin.py`, `apps.py`, and migrations
    - _Requirements: 5.1, 5.2, 5.3_
  - [x]\* 10.6 Write tests for marketplace
    - Purchase atomicity + 409 gone/already-owns, size_required/warnings/ack gating, auction delegation, return gates (not delivered, resold, window closed) + reason coercion + EXIF passthrough + best-effort awards, advance single-step, return-window policy
    - _Requirements: 5.5, 5.6, 5.8, 5.9, 5.10, 5.11, 5.13, 5.14, 5.15, 5.16, 5.17, 5.20, 5.21, 6.1, 6.4, 6.5_

- [x] 11. sellerportal app — catalog, rules, auto-disposition
  - [x] 11.1 Implement `sellerportal/models.py` and rule-matching logic
    - `SellerRule` (min_grade default B, min_recovery default 60, action AUTO_RELIST/LIQUIDATE/DONATE default AUTO_RELIST, active default true); matching predicate (assigned grade, non-null est_value, non-zero MRP; grade ≥ min; recovery = est×100//MRP ≥ min_recovery)
    - _Requirements: 19.4, 19.5_
  - [x] 11.2 Implement `sellerportal/views.py`, `serializers.py`, `urls.py`
    - Catalog create (clamp stock 1..50, validate image, create product + one NEW listing per stock unit at MRP; 400 on invalid title/category/MRP/stock), seller catalog (own, newest first), rules CRUD (own only), inbox (AT_FACILITY units newest-updated, annotated with first matching active rule action/id or null), apply (execute action; DONATE awards 15; 400 invalid action; 404 no match; AUTO_RELIST opens Dutch auction via nextowner with seller as owner+lister), bulk_apply (ascending rule-id order, first match wins, return handled + remaining counts); restrict all to `IsSeller`
    - _Requirements: 19.1, 19.2, 19.3, 19.6, 19.7, 19.8, 19.9, 19.10_
  - [x] 11.3 Add `sellerportal/admin.py`, `apps.py`, and migrations
    - _Requirements: 19.4_
  - [x]\* 11.4 Write tests for sellerportal
    - Stock clamp + listing creation, validation 400s, rule matching boundaries, inbox annotation, apply (DONATE award / 400 / 404), bulk_apply ordering + counts
    - _Requirements: 19.1, 19.2, 19.5, 19.6, 19.7, 19.8_

- [x] 12. facility app — intake, relist, watchlist, storage engine
  - [x] 12.1 Implement `facility/engine.py`
    - Daily storage accrual by category (electronics 8 / apparel 3 / footwear 4 / other 5 ₹/day) over AT_FACILITY + RELISTED units with arrival time; price step-down; liquidate when accrued storage ≥ value
    - _Requirements: 20.7, 20.8, 20.9_
  - [x] 12.2 Implement `facility/views.py` and `facility/urls.py`
    - incoming (RETURN_PENDING oldest first), receive (record untouched + arrival, grade preferring latest DONE assessment with suggested grade else heuristic, set est_value, unit→AT_FACILITY, order→REFUNDED, ensure recommendation inline + routing event best-effort, 404 if none), relist (price + open Dutch auction via nextowner; 409 if ACTIVE/RESERVED listing; 404 if none), watchlist (AT_FACILITY + RELISTED with non-null/non-zero est_value ranked by storage/value desc), dispose (LIQUIDATE/DONATED only; withdraw ACTIVE listing; 400 other; 404 wrong state), simulate-day (identical accrual, `IsFacility`)
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.10, 24.2_
  - [x] 12.3 Implement `facility/management/commands/accrue_storage.py`
    - Management command running the same accrual logic as the simulate-day endpoint
    - _Requirements: 20.7, 20.10_
  - [x]\* 12.4 Write tests for facility
    - Storage accrual by category + liquidation threshold, intake grading preference + REFUNDED + recommendation, relist 409/404, watchlist ranking, dispose validation
    - _Requirements: 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8_

- [x] 13. Frontend — React 18 + Vite SPA
  - [x] 13.1 Scaffold the Vite project
    - `frontend/package.json` (react 18, react-dom, react-router-dom, exifr, vite, @vitejs/plugin-react), `frontend/vite.config.js`, `frontend/index.html`, `frontend/public/logo.png`, `frontend/.dockerignore`
    - _Requirements: 22.1_
  - [x] 13.2 Implement `src/api.js` and `src/auth.jsx`
    - Fetch wrapper (GET retry up to 6 attempts, exponential backoff from ~400 ms on network error/5xx; CSRF token on unsafe single-attempt requests); session auth context loading current user on start with login/register/logout actions
    - _Requirements: 22.3, 22.4_
  - [x] 13.3 Implement `src/lib/image.js` and `src/lib/motion.js`
    - Client EXIF extraction + compression helpers; count-up and scroll-detection motion utilities
    - _Requirements: 22.7, 22.8_
  - [x] 13.4 Implement reusable components in `src/components/`
    - `PhotoPicker.jsx` (extracts per-photo EXIF before compression, emits index-aligned JSON), `Toast.jsx`, `icons.jsx`, `ConfirmModal.jsx`, `ProductCarousel.jsx`, `ResaleAlerts.jsx`
    - _Requirements: 22.7, 22.8_
  - [x] 13.5 Implement the app shell: `src/main.jsx`, `src/App.jsx`, `src/styles.css`
    - React Router routes for all pages, auth provider mount, global vanilla CSS
    - _Requirements: 22.1, 22.2, 22.3_
  - [x] 13.6 Implement shopping/resale pages
    - `Shop.jsx`, `ProductPage.jsx`, `PreLoved.jsx` (Recommended-for-you rail + general grid, 3s poll cleared on unmount animating descending price + growing bonus), `NextOwner.jsx`, `HealthCard.jsx`
    - _Requirements: 22.2, 22.5_
  - [x] 13.7 Implement account pages
    - `Orders.jsx` (accept/decline pending keep-it offer), `Resell.jsx` (PhotoPicker EXIF submission), `Rewards.jsx`, `Profile.jsx`, `Login.jsx`, `Register.jsx`
    - _Requirements: 22.2, 22.6, 22.8_
  - [x] 13.8 Implement portal pages
    - `SellerPortal.jsx` (catalog create, rules CRUD, inbox, apply/bulk-apply), `FacilityPortal.jsx` (incoming, receive, relist, watchlist, dispose, simulate-day)
    - _Requirements: 22.2_
  - [x] 13.9 Author frontend container files
    - `frontend/Dockerfile` (build + Nginx static), `frontend/Dockerfile.dev`, `frontend/nginx.conf` (serve SPA, reverse-proxy `/api` `/media` `/static` `/admin`)
    - _Requirements: 22.1, 23.1_
  - [x]\* 13.10 Verify the production build compiles
    - Run the Vite build and confirm assets emit without errors
    - _Requirements: 22.1_

- [x] 14. Final wiring, migrations, and full test suite
  - [x] 14.1 Finalize `config/settings.py`
    - Add `INSTALLED_APPS` (core, catalog, marketplace, grading, rerouting, nextowner, returnprevention, greencredits, sellerportal, facility, services + DRF) and the complete env-overridable business-knob block (storage rates, return windows, rerouting rate-per-km/fragility/repair/resale/sell-through/fraud weights, keep-it thresholds + split, match weights, recency half-life, auction tier-size/max-tier/step/interval/start-premium/reserve-discount, pricing rho/gamma/lambda/band-width, category depreciation rates, green-credit awards)
    - _Requirements: 21.1, 23.6_
  - [x] 14.2 Finalize `config/urls.py`
    - Mount every app's `urls.py` under `/api/...`
    - _Requirements: 22.1, 23.1_
  - [x] 14.3 Run migrations and the full offline test suite
    - `makemigrations` + `migrate`; run `core catalog marketplace grading rerouting nextowner returnprevention greencredits sellerportal facility` tests with `CELERY_TASK_ALWAYS_EAGER=1` and forced mock providers (`GRADING_VLM_PROVIDER=mock`, `REROUTING_LLM_PROVIDER=mock`, `RETURNPREV_LLM_PROVIDER=mock`), no network; fix any failures
    - _Requirements: 21.10, 23.3_

- [x] 15. Final checkpoint
  - Ensure all migrations apply cleanly and the full test suite passes offline; ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (unit/integration tests, build verification) and can be skipped for a faster first pass, but are recommended before the final checkpoint.
- Each task references the specific requirement clauses it implements for traceability.
- Cross-app references (e.g. catalog Health Card reading nextowner auctions, marketplace delegating to grading/nextowner/returnprevention) use local imports and string-based model FKs, so module files can be authored before the apps they reference are fully built; Django resolves everything at migration time in task 14.3.
- Per the design, this system uses example/integration-based testing rather than property-based testing; the offline suite pins behavior with representative examples and edge cases.
- Checkpoints validate incrementally; run the relevant app tests as each engine lands.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.4", "13.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "13.2", "13.3", "13.9"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "3.1", "13.4", "13.5"] },
    { "id": 3, "tasks": ["2.5", "4.1", "4.2", "5.1", "13.6", "13.7", "13.8"] },
    { "id": 4, "tasks": ["3.2", "4.3", "4.5", "5.2", "5.4", "13.10"] },
    { "id": 5, "tasks": ["2.4", "4.4", "5.3"] },
    { "id": 6, "tasks": ["2.7", "4.7", "5.5", "6.1", "6.2"] },
    { "id": 7, "tasks": ["6.3", "6.4", "6.5", "6.6", "6.7", "6.8"] },
    {
      "id": 8,
      "tasks": ["6.9", "7.1", "7.2", "7.3", "7.4", "8.1", "9.1", "9.2"]
    },
    { "id": 9, "tasks": ["6.10", "7.5", "8.2", "8.3", "8.7", "10.1", "11.1"] },
    {
      "id": 10,
      "tasks": [
        "6.11",
        "6.12",
        "6.13",
        "7.6",
        "8.4",
        "8.5",
        "9.3",
        "10.2",
        "10.5",
        "11.3"
      ]
    },
    {
      "id": 11,
      "tasks": ["6.14", "7.7", "7.8", "7.10", "8.6", "9.4", "9.5", "10.3"]
    },
    { "id": 12, "tasks": ["7.9", "7.11", "8.8", "9.6"] },
    { "id": 13, "tasks": ["4.6", "8.9", "8.10", "8.12", "12.1"] },
    { "id": 14, "tasks": ["2.6", "8.11", "10.4", "11.2", "12.2", "12.3"] },
    { "id": 15, "tasks": ["8.13", "10.6", "11.4", "12.4", "14.1", "14.2"] },
    { "id": 16, "tasks": ["14.3"] }
  ]
}
```
