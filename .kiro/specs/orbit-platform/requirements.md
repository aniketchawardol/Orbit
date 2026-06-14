# Requirements Document

## Introduction

Orbit is a full-stack platform that closes the loop on returned, unused, and outgrown products. Every physical item that enters the system is automatically graded for condition, priced, routed to its optimal disposition (resell, refurbish, peer-to-peer, donate), and matched to the buyer who wants it most — with sustainability incentives (green credits) awarded at every touchpoint.

This document is the definitive, exhaustive specification of the entire Orbit platform. It is intended to be complete enough that the entire system — backend (Django + Django REST Framework + Celery + PostgreSQL + Redis), frontend (React 18 + Vite SPA), AI/ML pipelines, and infrastructure (Docker Compose, optional AWS S3/CloudFront) — could be built from these requirements alone.

The platform serves three human roles (Buyer, Seller, Facility operator) plus the Platform/Admin role, and is organized around a single atomic concept: one physical **ItemUnit** flows through its entire lifecycle (NEW → SOLD → RETURN_PENDING → AT_FACILITY → RELISTED → SOLD again, or LIQUIDATE/DONATED), accumulating an immutable, append-only event trail that powers the buyer-facing Product Health Card.

Five engineering principles govern the whole system and are treated as cross-cutting requirements:

1. **No single source trusted.** Grading blends five independent signals with cross-source agreement and a fraud floor.
2. **Graceful degradation everywhere.** Every AI call has a deterministic fallback; the system runs identically with zero API keys configured.
3. **Configuration over code.** Adding a provider, changing match weights, tuning the auction, adjusting fraud-risk discounts — all are settings changes, not code changes.
4. **The unit is the atom.** One physical ItemUnit carries its entire lifecycle and an immutable event trail.
5. **Economics are explicit.** Every routing decision carries a per-route profit breakdown, the inputs that produced it, the realization probability, and the decision source.

## Glossary

- **Orbit_Platform (System)**: The complete full-stack application comprising the Django/DRF backend, Celery worker, PostgreSQL database, Redis (broker/cache/sessions), and React SPA frontend.
- **Buyer**: A user (role `BUYER`) who purchases products, returns them, and may resell items they own. Buyers also act as sellers in peer-to-peer resale; no separate role is required.
- **Seller**: A user (role `SELLER`) who lists catalog products, manages returned-unit inboxes, and defines automation rules.
- **Facility_Operator**: A user (role `FACILITY`, admin-created only) who physically receives returned units, grades them, relists them, and manages storage.
- **Platform_Admin**: An operator with Django admin/superuser access who configures business knobs, providers, and seed data.
- **Product**: A catalog entry (`catalog.Product`) with title, description, category, MRP, image, origin (PLATFORM or EXTERNAL), open-ended JSON `attributes`, and a seller.
- **ItemUnit (Unit)**: One physical unit of a Product (`catalog.ItemUnit`), the central atom of the system, carrying a lifecycle state, grade, estimated value, ownership, purchase anchor, and storage cost.
- **UnitEvent**: An append-only audit record (`catalog.UnitEvent`) describing one state transition or notable event for a Unit. Powers the Health Card.
- **Listing**: An offer to sell one Unit (`marketplace.Listing`) with a source (NEW, FACILITY_RELIST, USER_RESALE, SELLER_RETURN), price, fair-value band, and photos.
- **Order**: A purchase of a Listing (`marketplace.Order`), with return data folded in (reason, photos, comment, delivery time, chosen size).
- **Grading_Engine**: The multi-source AI condition grader (`grading` app) that blends VLM, perceptual-hash/colour similarity, EXIF metadata, and buyer history into a verdict.
- **GradingAssessment**: The durable verdict record for one grading run, storing raw per-source signals and blended scores (quality, fraud, confidence, suggested grade).
- **VLM**: Vision-Language Model — an OpenAI-compatible multimodal model (e.g. Gemini 2.5 Flash) used to inspect uploaded photos.
- **Rerouting_Engine**: The disposition decision engine (`rerouting` app) that chooses RESELL / REFURBISH / P2P / DONATE per returned unit using a risk-adjusted expected-value cost model plus an LLM strategy.
- **RouteDecision**: The durable disposition decision record, holding per-route profit breakdown, inputs, and the chosen route + decision source.
- **Keep_It_Offer (ReturnOffer)**: A return-prevention proposal offering a partial cash refund plus green credits when every disposition route loses money.
- **Health_Card**: The public, buyer-facing trust document for a Unit, showing AI-verified grade, confidence, remaining warranty, the append-only event trail, and the live price.
- **Return_Prevention_Engine**: The pre-purchase guard system (`returnprevention` app) providing a fit guide and accessory compatibility check.
- **NextBestOwner_Engine**: The peer-to-peer resale matching engine (`nextowner` app) that embeds buyers and products, scores matches over five behavioural signals, ranks buyers into tiers, and runs a descending-price (Dutch) auction.
- **DemandProfile**: A buyer's learned demand snapshot (taste vector, category/brand affinity, budget, green propensity) in the product embedding space.
- **ProductVector**: A cached text embedding for a Product.
- **ResaleAuction**: A descending-price (Dutch) auction over one resale Listing.
- **MatchEdge**: One scored buyer↔auction match, tiered and tracked from alert → view → purchase.
- **Green_Credits**: The sustainability reward currency (`greencredits` app) with an account, transactions, and a rewards store.
- **Storage_Engine**: The facility storage-cost accrual engine that charges daily storage, steps down prices, and liquidates units whose storage exceeds their value.
- **Provider_Registry**: The runtime resolver (per app) that selects an AI provider from settings, caches it per process, and falls back to a deterministic mock on any failure.
- **LLM_PROVIDERS**: The settings table of OpenAI-compatible provider configurations (gemini, openai, modal).
- **Celery_Chord**: A parallel-fan-out-then-aggregate task pattern; a group of subtasks runs in parallel, then a callback blends their results.
- **EV (Expected Value)**: The deterministic profit optimizer used by the Rerouting_Engine.
- **MRP**: Maximum Retail Price (₹), the product's original price.
- **est_value**: The estimated resale value (₹) of a Unit, computed from grade/quality/depreciation/fraud.
- **Mock_Provider**: A deterministic, network-free AI implementation used as a fallback so the system works fully offline with zero API keys.

## Requirements

### Requirement 1: Core Identity, Authentication, and User Profile

**User Story:** As a buyer or seller, I want to register, sign in, and maintain a profile with my sizes and location, so that the platform can personalize fit guidance, matching, and logistics decisions for me.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL provide a custom user model (`core.User`) extending Django's AbstractUser with a `role` field constrained to BUYER, SELLER, or FACILITY and defaulting to BUYER.
2. THE Orbit_Platform SHALL store on each User an open-ended JSON `profile` field (containing, for example, a `sizes` map) defaulting to an empty object, a `city` label defaulting to an empty string, and optional `lat` and `lng` floating-point coordinates each defaulting to null.
3. WHEN a registration request supplies a non-empty username, a non-empty password, and either a role of BUYER or SELLER or no role (defaulting to BUYER), THE Orbit_Platform SHALL create the user with that role, establish a session via login, enqueue the best-effort return-prevention precompute, and respond with HTTP 201 and the user payload.
4. IF a registration request supplies a role other than BUYER or SELLER, THEN THE Orbit_Platform SHALL reject the request with HTTP 400, evaluating this role check before the username/password presence and username-uniqueness checks, so that FACILITY accounts can only be created by an administrator.
5. IF a registration request omits the username or password, or supplies a username that is empty after surrounding whitespace is trimmed, THEN THE Orbit_Platform SHALL reject the request with HTTP 400.
6. IF a registration request supplies a username that already exists, THEN THE Orbit_Platform SHALL reject the request with HTTP 409, evaluating this uniqueness check after the role and presence checks.
7. WHEN a login request supplies valid credentials, THE Orbit_Platform SHALL establish a session, enqueue the best-effort return-prevention precompute, and respond with HTTP 200 and the user payload.
8. IF a login request supplies invalid credentials, THEN THE Orbit_Platform SHALL respond with HTTP 401.
9. THE user payload SHALL include id, username, role, email, first name, last name, city, lat, lng, profile, join date, and the current green-credit balance, defaulting the balance to 0 when the user has no green-credit account.
10. WHEN an authenticated user requests the current-user endpoint, THE Orbit_Platform SHALL respond with HTTP 200 and the user payload; WHEN an unauthenticated client requests it, THE Orbit_Platform SHALL respond with HTTP 200 and a null user value.
11. WHEN a logout request is received from an authenticated user, THE Orbit_Platform SHALL terminate the session and respond with HTTP 204.
12. WHEN a user successfully registers or logs in, THE Orbit_Platform SHALL enqueue a best-effort return-prevention precompute for that user, and IF the broker is unavailable THEN THE Orbit_Platform SHALL log the failure and complete authentication without error.
13. THE Orbit_Platform SHALL authenticate API requests using DRF session authentication, SHALL enforce CSRF protection on unsafe methods, and SHALL default API permissions to authenticated-or-read-only.
14. THE Orbit_Platform SHALL provide an `IsSeller` permission that grants access only to authenticated users with role SELLER, and an `IsFacility` permission that grants access only to authenticated users with role FACILITY.
15. WHEN the `SECURE_COOKIES` environment flag is enabled, THE Orbit_Platform SHALL mark the session and CSRF cookies as secure.
16. THE Orbit_Platform SHALL store sessions using the cached-database backend so session storage scales by swapping the cache backend alone.
17. THE Orbit_Platform SHALL honour the `X-Forwarded-Proto` header to detect HTTPS behind a proxy regardless of the `SECURE_COOKIES` flag.

### Requirement 2: Shared Image Upload Handling

**User Story:** As a buyer or seller uploading photos, I want my images validated and stored safely, so that grading and listings have reliable image inputs.

#### Acceptance Criteria

1. WHEN photos are uploaded, THE Orbit_Platform SHALL accept a file only when its filename extension, evaluated case-insensitively, is exactly one of .jpg, .jpeg, .png, or .webp.
2. IF an uploaded file's extension is not one of the four accepted extensions, THEN THE Orbit_Platform SHALL reject that upload with a user-facing error identifying the rejected extension, or indicating "unknown" when the filename has no extension.
3. IF an uploaded file's size is strictly greater than 8 megabytes (8,388,608 bytes), THEN THE Orbit_Platform SHALL reject that upload with a user-facing error naming the offending file.
4. IF a multi-photo upload contains more than 6 photos, THEN THE Orbit_Platform SHALL reject the upload, before persisting any photo from that upload, with a user-facing error stating the 6-photo maximum.
5. WHEN photos pass validation, THE Orbit_Platform SHALL persist each photo under the designated subdirectory of the configured media store using a generated unique filename that preserves the file's lowercased extension, and SHALL return the list of stored media-relative paths in upload order.

### Requirement 3: Catalog — Product, ItemUnit, and Event Trail

**User Story:** As a platform operator, I want every product and physical unit modelled with a complete lifecycle and immutable history, so that trust, routing, and resale all operate on a single source of truth.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL model a Product with title, description, category, MRP (positive integer ₹), optional image, an origin of PLATFORM or EXTERNAL (default PLATFORM), an open-ended JSON `attributes` map (default empty), and a seller reference.
2. WHERE a Product is brought from outside the platform for resale, THE Orbit_Platform SHALL set its origin to EXTERNAL so that grading runs in anomaly/quality mode without a reference image.
3. THE Orbit_Platform SHALL model an ItemUnit as the physical atom, with a lifecycle state, optional grade (one of A, B, C, or D), optional grade confidence, an `untouched` flag (default false), optional estimated value (₹), optional original purchase anchor (`purchased_at`), optional facility arrival time, accrued storage cost (₹, default 0), and an optional owner.
4. THE Orbit_Platform SHALL constrain the ItemUnit lifecycle state to exactly one of NEW, SOLD, RETURN_PENDING, AT_FACILITY, RELISTED, LIQUIDATE, or DONATED.
5. WHEN an ItemUnit is saved without an explicit state value, THE Orbit_Platform SHALL default its state to NEW.
6. WHEN any stateful object (ItemUnit, Listing, Order) transitions to a new state, THE Orbit_Platform SHALL update the state, SHALL stamp the change time, and SHALL append a UnitEvent recording the new state as the event type, the prior state, the originating model's class name, the acting user when one is supplied, and any additional payload.
7. THE Orbit_Platform SHALL store UnitEvents as append-only records ordered by creation time ascending, and SHALL NOT expose any operation that edits or deletes a recorded event.
8. WHEN a product list is requested, THE Orbit_Platform SHALL return products ordered by creation time descending (newest first), SHALL apply an optional text filter that selects a product when the query value occurs case-insensitively as a substring of its title or its description, SHALL apply an optional category filter that selects only products whose category exactly equals the requested value, and SHALL return at most 60 products.
9. WHEN a product detail is requested for an existing product, THE Orbit_Platform SHALL return the product together with its listings currently in the ACTIVE state; IF no product with the requested identifier exists, THEN THE Orbit_Platform SHALL respond with HTTP 404.
10. WHEN related products are requested for a product, THE Orbit_Platform SHALL return at most 12 other products that share the requested product's exact category, ordered newest first, excluding the requested product; IF no product with the requested identifier exists, THEN THE Orbit_Platform SHALL respond with HTTP 404.
11. THE Orbit_Platform SHALL expose a product image URL and a thumbnail URL, and WHERE a product has no image THE thumbnail SHALL fall back to the first photo of that product's newest ACTIVE listing when such a listing with at least one photo exists, otherwise resolving to null.
12. WHEN a real (non-mock) VLM derives durable classification attributes (size class, fragility) for a product during grading, THE Orbit_Platform SHALL merge those attributes onto the product, preserving any user-entered attribute keys, and SHALL skip the write when the attributes are already current.

### Requirement 4: Warranty Math for the Health Card

**User Story:** As a buyer of a pre-loved item, I want to see exactly how much manufacturer warranty remains, so that I can trust what I am buying.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL parse the free-text warranty string in a product's `attributes["warranty"]` by reading the first occurrence of a non-negative integer quantity followed by a unit of years, months, weeks, or days, evaluated case-insensitively.
2. WHEN both a parsed warranty period and an original purchase date are available, THE Orbit_Platform SHALL compute the expiry date by adding the period to the purchase date using calendar-accurate arithmetic for periods in years or months (so the expiry lands on the same calendar day-of-month) and exact-duration arithmetic for periods in weeks (7 days each) or days.
3. IF the purchase date is unknown, the warranty text is missing or not a string, the warranty text yields no parseable quantity-and-unit match, or the parsed quantity is not greater than zero, THEN THE Orbit_Platform SHALL omit the remaining-warranty field rather than display a value.
4. IF the computed expiry is at or before the current time, THEN THE Orbit_Platform SHALL omit the remaining-warranty field.
5. WHEN at least one whole year of warranty remains, THE Orbit_Platform SHALL render the remaining warranty floored to whole years; WHEN less than one year remains, THE Orbit_Platform SHALL render the remaining warranty floored to whole months.
6. IF the remaining duration floors to zero months, THEN THE Orbit_Platform SHALL omit the remaining-warranty field rather than display "0 months".

### Requirement 5: Marketplace — Listings, Purchase, and Return Flow

**User Story:** As a buyer, I want to purchase listings safely and return items within policy, so that I can shop with confidence and recover value when something doesn't work out.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL model a Listing referencing exactly one Unit with a source of NEW, FACILITY_RELIST, USER_RESALE, or SELLER_RETURN, a price as a positive integer count of ₹, an optional fair-value band whose band_lo and band_hi are positive integers when present, a list of stored photo paths (validated per Requirement 2, at most 6), and an optional lister reference.
2. THE Orbit_Platform SHALL define Listing states ACTIVE, RESERVED, SOLD, and WITHDRAWN, SHALL default a newly created Listing to ACTIVE, and SHALL enforce in code that at most one Listing per Unit is in ACTIVE or RESERVED state at any time.
3. THE Orbit_Platform SHALL model an Order referencing a buyer and a Listing, with optional chosen size, return reason, claimed-untouched flag, return photos, return comment, and delivery time, and SHALL define Order states PLACED, DELIVERED, RETURN_REQUESTED, RETURN_RECEIVED, REFUNDED, SETTLED, and PREVENTED.
4. WHEN a buyer places an order for a listing, THE Orbit_Platform SHALL run the pre-purchase return-prevention guard outside any database row lock so that no lock is held across an LLM call.
5. IF the guard determines a size is required but none was chosen, THEN THE Orbit_Platform SHALL reject the purchase with HTTP 400, the available size options, and the recommended size.
6. IF the guard produces one or more warnings and the buyer has not set the acknowledgement flag, THEN THE Orbit_Platform SHALL reject the purchase with HTTP 409, the warning messages, and the recommended size, so the buyer can re-submit with acknowledgement to proceed.
7. WHERE the target listing is backed by a Dutch auction, THE Orbit_Platform SHALL delegate the purchase to the Next Best Owner buy flow so the buyer pays the current descending price, earns the green-credit bonus, and the auction is closed atomically.
8. WHEN a buyer purchases a NEW listing, THE Orbit_Platform SHALL acquire a row lock on the listing, SHALL verify it is still ACTIVE, SHALL transition the listing to SOLD and the unit to SOLD, SHALL set the unit owner to the buyer, and SHALL create the order, all within one atomic transaction.
9. IF a buyer attempts to purchase a listing that is no longer ACTIVE, THEN THE Orbit_Platform SHALL respond with HTTP 409.
10. IF a buyer attempts to purchase a unit they already own, THEN THE Orbit_Platform SHALL respond with HTTP 409.
11. WHEN a buyer purchases a USER_RESALE listing, THE Orbit_Platform SHALL award 20 green credits and SHALL append a pickup-scheduled event for the unit; WHEN a buyer purchases a FACILITY_RELIST listing, THE Orbit_Platform SHALL award 25 green credits.
12. WHEN an authenticated buyer requests their orders, THE Orbit_Platform SHALL return only that buyer's orders ordered by creation time descending (newest first).
13. WHEN a buyer requests a return on an order in the DELIVERED state that is return-eligible per Requirement 6, THE Orbit_Platform SHALL record the return reason, claimed-untouched flag, comment, and uploaded return photos (validated per Requirement 2), SHALL transition the order to RETURN_REQUESTED and the unit to RETURN_PENDING, and SHALL start asynchronous multi-source grading.
14. IF a buyer requests a return on an order that is not in the DELIVERED state, THEN THE Orbit_Platform SHALL respond with HTTP 409.
15. IF a buyer requests a return on a unit for which that buyer has already filed a resale request, THEN THE Orbit_Platform SHALL refuse the return with HTTP 409 and a message indicating the item has been resold.
16. IF a buyer requests a return after the return deadline has passed, THEN THE Orbit_Platform SHALL refuse the return with HTTP 409, SHALL indicate that resale is available, and SHALL include the return deadline.
17. IF the supplied return reason is not one of the recognized reasons (DIDNT_MATCH, WRONG_SIZE, CHANGED_MIND, DEFECTIVE, OTHER), THEN THE Orbit_Platform SHALL substitute the OTHER reason.
18. WHEN a buyer claims the returned item is untouched, THE Orbit_Platform SHALL award 5 green credits as a best-effort action that never blocks completion of the return.
19. IF starting grading or awarding untouched-return credits fails, THEN THE Orbit_Platform SHALL log the failure and SHALL complete the return successfully.
20. WHEN the return request includes per-photo client EXIF metadata as a JSON array index-aligned to the uploaded photos, THE Orbit_Platform SHALL pass that metadata to the grading pipeline.
21. WHEN a demo advance action is invoked on an order, THE Orbit_Platform SHALL move it exactly one step forward (PLACED→DELIVERED or RETURN_REQUESTED→RETURN_RECEIVED), and WHEN the resulting state is DELIVERED THE Orbit_Platform SHALL record the current time as the delivery time used as the return-window anchor.
22. IF a demo advance action is invoked on an order whose state has no defined forward step, THEN THE Orbit_Platform SHALL respond with HTTP 409.

### Requirement 6: Return-Window Policy

**User Story:** As a platform operator, I want returns gated by a category-specific time window, so that out-of-policy returns are redirected to resale.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL determine the return-window length in whole days by matching the unit's product category case-insensitively against the configured per-category overrides, falling back to a configurable global default of 7 days when no override matches.
2. THE Orbit_Platform SHALL anchor the return window on the order's recorded delivery time, falling back to the order creation time when no delivery time was recorded.
3. WHEN computing the return deadline, THE Orbit_Platform SHALL add the category window length in days to the anchor time.
4. WHILE the current time is at or before the return deadline and the buyer has not filed a resale request for the unit, THE Orbit_Platform SHALL treat the order as return-eligible.
5. WHEN a buyer has filed a resale request for a unit, THE Orbit_Platform SHALL treat that buyer's originating order as no longer return-eligible, even while the order remains in the DELIVERED state.

### Requirement 7: AI Condition Grading — Multi-Source Pipeline

**User Story:** As a platform operator, I want returned and resold items graded automatically from buyer photos in under two seconds, so that no manual inspection is needed and fraud is caught.

#### Acceptance Criteria

1. THE Grading_Engine SHALL create one durable GradingAssessment per grading run, retaining every raw per-source signal (VLM output, image-similarity result, EXIF metadata findings, buyer-history snapshot), the resolved provider names (VLM and embedding), and the blended scores (quality, fraud, and confidence each as a value in [0,1] and a suggested grade in {A, B, C, D}), so that decisions can be re-reasoned without re-running models.
2. THE Grading_Engine SHALL support exactly three assessment contexts — RETURN, RESALE, and FACILITY intake — and SHALL track assessment status across the values PENDING, RUNNING, DONE, and FAILED, defaulting a newly created assessment to PENDING.
3. WHEN a return assessment is created, THE Grading_Engine SHALL record the buyer's uploaded photos as UPLOADED images and the listing photos plus the product image as REFERENCE images, and SHALL store each provided per-photo client EXIF entry on the UPLOADED image at the matching index.
4. THE Grading_Engine SHALL run exactly four independent sources for each assessment: a VLM source, an image-similarity source, an EXIF-metadata source, and a buyer-history source.
5. WHEN a broker is available, THE Grading_Engine SHALL set the assessment status to RUNNING, fan the four sources out as parallel Celery subtasks in a chord, and blend their results in the aggregate callback, and SHALL NOT pass image bytes through the broker — each subtask SHALL read the images it needs from storage by assessment id.
6. IF chord dispatch fails or the system is in eager mode, THEN THE Grading_Engine SHALL run all four sources and the aggregation inline within a single process.
7. IF any single grading source raises an error, THEN THE Grading_Engine SHALL substitute an empty partial result for that source, log the failure, and complete the remaining sources and the aggregation.
8. THE VLM source SHALL send product context, the buyer's claim (reason, comment, untouched flag), the UPLOADED images, and the REFERENCE images to the resolved VLM provider using the configured VLM timeout (default 30 seconds); IF the provider call fails or times out, THEN THE VLM source SHALL fall back to the deterministic mock provider and record the provider used as "mock".
9. THE image-similarity source SHALL compute a combined similarity from a 64-bit dHash and a coarse RGB colour histogram (colour weighted at 0.45) between each UPLOADED and each REFERENCE image, SHALL persist each UPLOADED image's perceptual hash, SHALL flag uploaded-image pairs whose dHash similarity is at or above 0.96 as near-duplicates, and SHALL treat a best-match combined similarity below 0.6 as rising fraud suspicion so colour/material swaps that grayscale hashing alone would miss are detected.
10. THE metadata source SHALL derive server-side width, height, and format from the stored bytes, SHALL analyze each UPLOADED image's client EXIF against the order delivery time, and SHALL raise the weighted anomaly flags stale_capture (weight 0.5, capture more than 1 day before delivery), future_capture (0.5, capture more than 1 day after the current time), software_edited (0.4), dimension_mismatch (0.4, stored dimension exceeding the claimed original by more than 5%), is_screenshot (0.35), no_capture_time (0.15), no_camera_exif (0.15), and low_resolution (0.1, original pixel count below 230,400), combining per-image weights (each clamped to [0,1]) into a metadata fraud signal of 0.6×worst + 0.4×mean.
11. THE buyer-history source SHALL summarize the buyer's prior orders excluding the current order into a return-rate-and-velocity fraud signal in [0,1], SHALL cap the signal at 0.3 when the buyer has fewer than three prior orders, and otherwise SHALL compute it as 0.6×min(return-rate, 1) + 0.4×min(returns in the last 30 days ÷ 3, 1).
12. THE Grading_Engine SHALL persist the durable VLM-derived classification (size class, fragility, category) onto the product only when the resolved VLM provider is a real provider (not "mock", "error", "unknown", or empty), merging the values so user-entered attribute keys survive and skipping the write when the attributes are already current.
13. WHEN a RETURN assessment completes, THE Grading_Engine SHALL hand off to the Rerouting_Engine; WHEN a RESALE assessment completes, THE Grading_Engine SHALL hand off to the Next Best Owner pricing-and-matching engine; IF the handoff cannot be enqueued, THEN THE Grading_Engine SHALL log the failure and complete grading without error.
14. WHEN an assessment finishes, THE Grading_Engine SHALL record the run latency in milliseconds measured from the assessment creation time.
15. WHERE a grading run uses only deterministic providers (the mock VLM and perceptual-hash similarity), THE Grading_Engine SHALL complete the run in under 2000 milliseconds as recorded by the latency in criterion 14.

### Requirement 8: AI Grading — Blended Scoring and Fraud Floor

**User Story:** As a platform operator, I want the four grading sources blended with explicit weights and a decisive fraud override, so that no single deceptive source can produce a misleading verdict.

#### Acceptance Criteria

1. THE Grading_Engine SHALL compute a quality score as the VLM's quality estimate clamped to [0,1].
2. THE Grading_Engine SHALL compute five per-source fraud signals, each clamped to [0,1]: a VLM signal (0.0 when the item matches the reference else 0.6, plus 0.15 per VLM fraud flag capped at an added 0.4), an image-similarity signal, a metadata-anomaly signal, a buyer-history signal, and a stated-reason-versus-observation mismatch signal.
3. THE Grading_Engine SHALL blend the available fraud signals using the fixed weights VLM 0.30, similarity 0.25, metadata 0.20, history 0.15, and reason-mismatch 0.10, renormalized over only the signals that are present, so that an absent signal (for example image similarity when there is no reference image) does not zero the blended score.
4. WHEN a real (non-mock) VLM reports, with confidence at or above 0.6, that the returned item does not match the listed product, THE Grading_Engine SHALL floor the blended fraud score at 0.6 regardless of weaker sources.
5. THE Grading_Engine SHALL raise a reason-mismatch signal of 0.5 when the stated reason is DEFECTIVE while VLM quality is at or above 0.8 with no reported defects, 0.4 when the stated reason is DIDNT_MATCH while the VLM reports the item matches at match-confidence at or above 0.6, and 0.4 when the stated reason is CHANGED_MIND or OTHER while VLM quality is below 0.4 or at least two defects are reported, and 0.0 otherwise.
6. THE Grading_Engine SHALL compute confidence as 0.5×VLM self-confidence (multiplied by 0.6 when the VLM is not real) + 0.25×data availability (count of available fraud signals ÷ 5) + 0.25×cross-source agreement (1 − the population standard deviation of the available signals, or 0.5 when fewer than two signals are available), clamped to [0,1].
7. THE Grading_Engine SHALL derive the suggested grade as the worse (more conservative) of the VLM's suggested grade and the quality-derived grade, where the quality-derived grade maps quality to A (≥0.85), B (≥0.6), C (≥0.35), and D (below 0.35), and where a missing or invalid VLM grade defaults to B.
8. THE Grading_Engine SHALL record an explainable breakdown including each fraud signal value, the weights applied, the reason-mismatch note, the decisive-wrong-item flag, the consolidated fraud flags, and the grade-derivation rule.

### Requirement 9: Smart Rerouting — Disposition Decision Engine

**User Story:** As a facility operator, I want each returned unit automatically routed to its most profitable disposition, so that I never have to guess what to do with an item.

#### Acceptance Criteria

1. THE Rerouting_Engine SHALL decide exactly one disposition per returned unit, selected from the set {RESELL, REFURBISH, P2P, DONATE}.
2. THE Rerouting_Engine SHALL run two strategies for each decision — a deterministic Expected-Value (EV) optimizer and an LLM strategy — in parallel as a Celery chord and SHALL blend their results in a finalize callback; WHERE no broker is available or the system is in eager mode, THE Rerouting_Engine SHALL run both strategies inline so a decision is always produced.
3. WHEN the LLM strategy returns a result containing a non-empty route, THE Rerouting_Engine SHALL adopt that route as authoritative and SHALL record its confidence and reasoning. IF the LLM strategy returns no result or a result without a route, THEN THE Rerouting_Engine SHALL adopt the EV optimizer's route and SHALL record EV-derived reasoning that lists each route with its profit.
4. THE Rerouting_Engine SHALL compute, for each of the four routes, a revenue (₹, rounded to the nearest integer), a cost (₹, rounded to the nearest integer), a realization probability in [0,1] rounded to 3 decimals, and a profit equal to revenue minus cost, and SHALL retain the input values used to produce them.
5. THE Rerouting_Engine SHALL risk-adjust resale revenue by a realization probability equal to clamp01( sell_through(quality) × (1 − clamp01(fraud) × fraud_weight) ), where fraud_weight is 1.0 for RESELL and P2P, and expected revenue equals nominal value × realization probability, so that a low-quality or suspicious item does not always win on RESELL.
6. THE Rerouting_Engine SHALL compute sell_through(quality) as 0.5 + 0.5 × clamp01(quality), yielding 0.5 at quality 0 and ramping linearly to 1.0 at quality 1.
7. THE Rerouting_Engine SHALL compute the logistics rate as RATE_PER_KM[size_class] × FRAGILITY_MULT[fragility], where RATE_PER_KM is ₹3.0/km for "small" and ₹12.0/km for "big", and FRAGILITY_MULT is 1.0 for "rigid" and 1.5 for "delicate", and SHALL charge two legs at the inter-city distance for RESELL and REFURBISH, two legs at the fixed in-city distance of 15 km for P2P, and one in-city leg of 15 km for DONATE, adding the unit's accrued storage cost (default 0 ₹) to every route's cost.
8. THE Rerouting_Engine SHALL compute the inter-city distance as the great-circle (haversine) distance in kilometres between the seller's and buyer's coordinates, and IF either party's coordinates are unknown THEN THE Rerouting_Engine SHALL substitute the central facility location for that party.
9. THE Rerouting_Engine SHALL compute the refurbish repair cost as round( min( (1 − clamp01(quality)) × MRP × 0.4, 0.6 × MRP ) ), SHALL value the refurbished unit at round(0.6 × MRP), and SHALL compute its realization probability at a restored target quality of 0.85 using a fraud weight of 0.5 (half the resale fraud weight, reflecting that inspection during refurbishment catches some fraud).
10. THE Rerouting_Engine SHALL treat DONATE as the risk-immune floor with zero revenue and a realization probability of 0, costing one in-city leg plus accrued storage, so that DONATE is selected when no other route yields a higher profit.
11. THE EV optimizer SHALL select the route with the highest profit, SHALL compute the reported loss as max(0, −best_profit), and SHALL produce a ranking of all four routes ordered by descending profit.
12. THE Rerouting_Engine SHALL source size class and fragility from the durable grader-derived product attributes when present, falling back to the current run's VLM output, then to defaults of "small" size class and "rigid" fragility.
13. WHEN the unit has no stored estimated value, THE Rerouting_Engine SHALL derive one from the deterministic pricing helper using the product's MRP and the unit's grade (the suggested grade, falling back to the unit grade, then to "B").
14. WHEN a disposition is required immediately (for example at facility intake) and no completed RouteDecision exists for the unit, THE Rerouting_Engine SHALL compute one synchronously from the latest completed grading assessment, and WHERE only a pending or running assessment exists THE Rerouting_Engine SHALL complete that assessment inline before deciding.
15. IF building the rerouting context fails, THEN THE Rerouting_Engine SHALL log the failure, SHALL NOT create a decision, and SHALL NOT interrupt the grading pipeline.

### Requirement 10: Return-Prevention "Keep-It" Offer

**User Story:** As a buyer, I want the option to keep an item I returned in exchange for a partial refund and green credits, so that I save the hassle of shipping it back when that benefits both me and the platform.

#### Acceptance Criteria

1. WHEN the EV optimizer reports a loss greater than 0 ₹ for a returned unit (every disposition route yields negative profit), THE Rerouting_Engine SHALL evaluate whether to generate a keep-it offer.
2. IF the assessed fraud score exceeds 0.3 OR the assessed quality score is below 0.4, THEN THE Rerouting_Engine SHALL NOT generate a keep-it offer, so that only genuinely usable items with low fraud risk (fraud ≤ 0.3 and quality ≥ 0.4) qualify.
3. THE Rerouting_Engine SHALL compute the make-whole amount as round( min( paid × (1 − clamp01(quality)), loss ) ), where paid is the order's listing price (falling back to the product's MRP), and IF the make-whole amount is not greater than 0 THEN THE Rerouting_Engine SHALL NOT create an offer.
4. THE Rerouting_Engine SHALL compute the cash component as round(0.6 × make_whole) and the green-credit component as max(make_whole − cash, 0), so the offer is cash-majority (60% cash, remainder credits) by default.
5. THE Rerouting_Engine SHALL record on the offer the cash refund, the green credits, the expected loss avoided, and a company cost equal to round( cash + 0.9 × credits ), and SHALL set the offer status to PENDING.
6. WHEN a buyer accepts a PENDING keep-it offer attached to one of their own orders, THE Orbit_Platform SHALL, within a single atomic transaction, award the green credits to the buyer's account, mark the offer ACCEPTED with a response timestamp, transition the order to PREVENTED, set the unit's owner to the buyer and transition the unit to SOLD, and SHALL perform these actions idempotently.
7. WHEN a buyer declines a PENDING keep-it offer attached to one of their own orders, THE Orbit_Platform SHALL mark the offer DECLINED with a response timestamp and SHALL allow the normal return to proceed without awarding credits.
8. IF a buyer acts on an offer whose status is not PENDING, THEN THE Orbit_Platform SHALL return the offer's current status without awarding credits or repeating any state transition, and SHALL include the buyer's current green-credit balance.
9. IF a buyer attempts to accept or decline an offer that is not attached to one of their own orders, THEN THE Orbit_Platform SHALL respond with HTTP 404.
10. IF creating a keep-it offer fails, THEN THE Rerouting_Engine SHALL log the failure and SHALL still persist the completed RouteDecision.

### Requirement 11: Trust Layer — Product Health Card

**User Story:** As a buyer considering a pre-loved item, I want a single trustworthy document showing condition, confidence, warranty, and full history, so that I never face uncertainty about what I am buying.

#### Acceptance Criteria

1. WHEN a Health Card is requested for an existing unit, THE Orbit_Platform SHALL respond with HTTP 200 and a document containing the unit's product, lifecycle state, AI-verified grade (A/B/C/D, or null when the unit has not yet been graded), grade confidence, untouched flag, estimated value (₹), facility arrival time, accrued storage cost (₹), current live price, remaining-warranty label, and the unit's complete event trail ordered by creation time oldest-first, where each event carries its type, payload, actor username, and creation time.
2. THE Orbit_Platform SHALL omit the internal AI disposition routing recommendation field entirely from the public buyer-facing Health Card, and SHALL include that field only when the caller is a facility-context caller.
3. WHEN an active Dutch auction exists for the unit, THE Health Card SHALL set the current live price to that auction's current descending price; IF no active Dutch auction exists but an ACTIVE listing exists for the unit, THEN THE Health Card SHALL set the current live price to that listing's price; IF neither exists, THEN THE Health Card SHALL set the current live price to null.
4. WHEN the product warranty text and the unit's original purchase anchor together yield a positive remaining duration per Requirement 4, THE Health Card SHALL include the remaining-warranty label; IF no positive remaining duration can be derived, THEN THE Health Card SHALL omit the remaining-warranty field rather than display a value.
5. IF a Health Card is requested for a unit id that does not exist, THEN THE Orbit_Platform SHALL respond with HTTP 404 and no card body.
6. THE Health Card SHALL be retrievable by an unauthenticated caller without any session and SHALL return HTTP 200, so that any prospective buyer can inspect it.

### Requirement 12: Return Prevention — Fit Guide

**User Story:** As a buyer of apparel or footwear, I want an instant size recommendation from my declared sizes, so that I do not buy the wrong size.

#### Acceptance Criteria

1. WHERE a product's attributes declare both a non-empty size type and a non-empty list of size options, THE Return_Prevention_Engine SHALL treat the product as sized; otherwise THE Return_Prevention_Engine SHALL report the product as unsized and SHALL produce no size recommendation.
2. WHEN an authenticated buyer views a sized product, THE Return_Prevention_Engine SHALL read the buyer's declared size for that size type from the buyer's profile sizes map and SHALL recommend the closest available size option.
3. THE Return_Prevention_Engine SHALL select the closest size option by nearest ordinal position on the ordered apparel-top size scale (XS, S, M, L, XL, XXL, XXXL) for the apparel-top size type, and by nearest absolute numeric value for numeric size types.
4. THE fit guide SHALL operate as a pure in-memory lookup that performs no network call and no asynchronous task, returning its recommendation synchronously within the request.
5. IF a buyer attempts to purchase a sized product without choosing a size, THEN THE Orbit_Platform SHALL reject the purchase with HTTP 400 and SHALL return the size options and the recommended size.
6. WHEN a buyer chooses a size different from the recommended size, THE Orbit_Platform SHALL surface a non-blocking warning that names the chosen size and the recommended size, and SHALL allow the purchase to proceed once the buyer acknowledges the warning.
7. IF the buyer is unauthenticated, has no declared size for the product's size type, or the declared size is not representable on the relevant size scale, THEN THE Return_Prevention_Engine SHALL return a null recommendation for that sized product.

### Requirement 13: Return Prevention — Accessory Compatibility

**User Story:** As a buyer of an accessory, I want to be warned when it does not fit a device I already own, so that I avoid an incompatible purchase, without being warned about devices I don't own.

#### Acceptance Criteria

1. WHERE a product's attributes declare a non-empty `compatible_model` value, THE Return_Prevention_Engine SHALL treat the product as an accessory subject to compatibility checking; WHERE a product declares no `compatible_model`, THE Return_Prevention_Engine SHALL treat it as compatible by definition and SHALL perform no check, no LLM call, and no caching.
2. WHEN checking an accessory's compatibility for a buyer, THE Return_Prevention_Engine SHALL collect the distinct devices the buyer owns by scanning the buyer's order history for purchased products that declare a non-empty `model` attribute.
3. WHEN computing an accessory compatibility verdict, THE Return_Prevention_Engine SHALL use the configured LLM provider; IF no LLM provider is configured, the LLM call fails, or its response cannot be parsed, THEN THE Return_Prevention_Engine SHALL compute the verdict using the deterministic rules engine.
4. THE deterministic rules engine SHALL return an incompatibility warning naming an owned conflicting device only when the buyer owns at least one device whose product line matches the accessory's target model line but whose variant differs from the target variant; otherwise THE rules engine SHALL return compatible with no warning.
5. THE Return_Prevention_Engine SHALL suppress any incompatibility warning, regardless of the LLM verdict, unless the buyer owns at least one same-line device whose variant does not match the accessory's target model, so that cross-line cases (for example owning an iPhone while buying a Galaxy case) never produce a warning.
6. WHEN a compatibility verdict is computed, THE Return_Prevention_Engine SHALL store it in the shared cache keyed by (buyer id, product id) for a configurable time-to-live defaulting to 3600 seconds, and SHALL serve the cached verdict on subsequent checks within that period unless a forced recompute is requested.
7. WHEN a user logs in or registers, THE Return_Prevention_Engine SHALL precompute and cache compatibility verdicts in parallel for every purchasable accessory (each having a `compatible_model` attribute and an ACTIVE listing) as a best-effort action, and IF the broker is unavailable THEN THE Return_Prevention_Engine SHALL log the failure and complete authentication without error.
8. IF computing a compatibility verdict raises an error, THEN THE Return_Prevention_Engine SHALL treat the purchase gate as not raising a warning and SHALL fall back to the deterministic rules verdict.

### Requirement 14: Peer-to-Peer Resale — Next Best Owner Matching

**User Story:** As a seller reselling an item, I want the platform to find the buyers most likely to want it, so that the item sells quickly at a fair price without my guessing.

#### Acceptance Criteria

1. THE NextBestOwner_Engine SHALL score every candidate buyer against a resale product as a weighted sum of five behavioural signals, each in [0,1], using configurable weights that sum to 1.0 with defaults semantic taste 0.45, category affinity 0.20, price fit 0.20, quality fit 0.10, and green propensity 0.05, yielding a score in [0,1].
2. THE NextBestOwner_Engine SHALL compute semantic taste as the cosine similarity remapped to [0,1] via (cosine + 1) ÷ 2 between the buyer's recency-weighted taste vector and the product's text embedding; IF the buyer's taste vector is empty (cold start) or its dimensionality does not match the product vector, THEN THE NextBestOwner_Engine SHALL assign a neutral semantic taste of 0.5.
3. THE NextBestOwner_Engine SHALL compute category affinity as the value for the product's normalized category in the buyer's recency-weighted, normalized category histogram (45-day recency half-life), returning 0.0 when the product's category is absent from the histogram.
4. THE NextBestOwner_Engine SHALL compute price fit as the Gaussian kernel exp(−0.5 × z²), where z = (price − spend_mean) ÷ scale and scale = spend_std when spend_std > 1 else max(1, 0.5 × spend_mean); IF the buyer's spend mean is not positive (no budget signal), THEN THE NextBestOwner_Engine SHALL return a neutral price fit of 0.5.
5. THE NextBestOwner_Engine SHALL compute quality fit from a grade-tolerance mapping (A 1.0, B 0.8, C 0.55, D 0.3), defaulting to 0.6 when the grade is missing or unrecognized.
6. THE NextBestOwner_Engine SHALL compute green propensity in [0,1] as 0.6 × pre-loved purchase ratio + 0.4 × engagement, where engagement is min(1, total credits earned ÷ 200), derived from the buyer's green-credit transaction history.
7. THE NextBestOwner_Engine SHALL build a weighted bipartite graph between the product node and the candidate-buyer nodes, rank buyers by descending score, take the top K = tier_size × max_tier buyers (default 3 × 4 = 12), and assign each a 0-based rank and an alert tier of min(rank ÷ tier_size, max_tier − 1).
8. THE NextBestOwner_Engine SHALL restrict candidate buyers to users with role BUYER, excluding the seller and the unit's current owner; WHERE same-locality demo mode is disabled, THE NextBestOwner_Engine SHALL additionally restrict candidates to buyers whose city matches the lister's city case-insensitively.
9. THE NextBestOwner_Engine SHALL cache product vectors and buyer demand profiles keyed by the name of the embedding provider that built them, and WHEN the cached entry's provider differs from the active provider THE NextBestOwner_Engine SHALL rebuild it.
10. THE NextBestOwner_Engine SHALL build a buyer's demand profile from order and green-credit history, including a recency-weighted taste vector, normalized category and brand affinity histograms, spend mean and standard deviation, green propensity, and order count, producing a neutral cold-start profile for buyers with no history.
11. THE NextBestOwner_Engine SHALL run text embedding only on the Celery worker and SHALL defer the heavy embedding-model import to construction time; IF the local embedding model cannot load, THEN THE NextBestOwner_Engine SHALL fall back to deterministic hash-based mock embeddings.
12. THE NextBestOwner_Engine SHALL precompute the product vector and every candidate buyer's demand profile in parallel via a chord before finalizing pricing and matching.
13. IF precomputing an individual buyer's demand profile or the product vector fails, THEN THE NextBestOwner_Engine SHALL log the failure and continue the matching run using the available profiles.

### Requirement 15: Peer-to-Peer Resale — Resale Pricing

**User Story:** As a seller, I want the platform to price my resold item from its condition and age, so that I never have to set a price myself.

#### Acceptance Criteria

1. THE NextBestOwner_Engine SHALL compute the estimated value as int(round(original_price × quality_realization × depreciation_factor × fraud_penalty)).
2. THE NextBestOwner_Engine SHALL compute quality_realization as rho_min + (rho_max − rho_min) × quality^gamma using configurable rho_min (0.15), rho_max (0.75), and gamma (1.2).
3. THE NextBestOwner_Engine SHALL compute depreciation_factor as (1 − category_monthly_rate)^age_months, using a category-specific monthly rate (electronics 0.05, apparel 0.03, footwear 0.035) and a configurable default (0.03) for any other or missing category, with age_months clamped to be at least 0.
4. THE NextBestOwner_Engine SHALL compute the fraud_penalty as max(0, 1 − lambda × fraud) using a configurable lambda (0.5).
5. THE NextBestOwner_Engine SHALL compute the fair-value band as estimated value × (1 ± band_width × (1 − confidence)) using a configurable band width (0.15), clamping the lower bound (band_lo) into [0, estimated value] and the upper bound (band_hi) to at least the estimated value, so that lower confidence widens the band.
6. THE NextBestOwner_Engine SHALL clamp pricing inputs to [0,1] and apply defaults of quality 0.5, fraud 0.0, and confidence 0.6 when those inputs are missing, and SHALL floor the original price at 0.
7. THE NextBestOwner_Engine SHALL retain the pricing factors (original price, quality, quality_realization, depreciation, fraud penalty, confidence, category, age in months) for audit and display.

### Requirement 16: Peer-to-Peer Resale — Dutch Auction

**User Story:** As a buyer interested in pre-loved items, I want prices to descend over time with growing rewards, so that I am nudged to buy exactly when the deal becomes good for me.

#### Acceptance Criteria

1. THE NextBestOwner_Engine SHALL open a descending-price (Dutch) auction whose opening ask (ceiling) is round(est_value × (1 + start_premium)) with a configurable start premium of 0.25 and whose reserve floor is round(est_value × (1 − reserve_discount)) with a configurable reserve discount of 0.30, with the floor clamped into [0, ceiling], deliberately wider than the fair-value band so the price visibly descends across several steps.
2. THE NextBestOwner_Engine SHALL initialize the auction at the ceiling price, at tier 0, with the configurable step percentage (12%), interval (60 seconds), and maximum tier (4).
3. WHEN the auction opens, THE NextBestOwner_Engine SHALL persist the ranked buyer matches as MatchEdges and SHALL alert tier 0 at the opening price.
4. WHEN a price step occurs, THE NextBestOwner_Engine SHALL set the new price to max(round(current_price × (1 − step_pct)), floor), SHALL advance the alert tier to min(current_tier + 1, max_tier − 1), SHALL emit a resale-alert event, and SHALL refresh the green-credit bonus on all alerted buyers to track the new price.
5. THE NextBestOwner_Engine SHALL expire the auction only once it has reached both the floor price and the last tier.
6. WHEN a price step completes and the auction is still active, THE NextBestOwner_Engine SHALL reschedule the next step using a self-scheduling worker task with a countdown equal to the interval, without relying on a periodic scheduler or cron; WHILE the system is in eager mode, THE NextBestOwner_Engine SHALL NOT auto-advance the auction.
7. THE NextBestOwner_Engine SHALL acquire a row lock on the auction during each step and SHALL skip an early or duplicate trigger by rescheduling it to the due time, unless a force flag is set, so concurrent triggers cannot corrupt auction state.
8. THE NextBestOwner_Engine SHALL compute the green-credit bonus as round( clamp((ceiling − price) ÷ (ceiling − floor), 0, 1) × max_bonus ) with a configurable maximum of 40 credits, yielding 0 at the ceiling, growing to the maximum at the floor, and 0 whenever ceiling ≤ floor.
9. WHEN a buyer buys at the current price, THE NextBestOwner_Engine SHALL acquire a row lock on the auction and listing, SHALL verify both are still active and that the buyer does not already own the unit, SHALL transfer the unit to the buyer and create the order, SHALL mark the auction SOLD, and SHALL mark the winning MatchEdge PURCHASED and the rest EXPIRED, all within one atomic transaction.
10. WHEN a buyer completes a Dutch-auction purchase, THE NextBestOwner_Engine SHALL award the buyer a base of 20 green credits plus the current price-drop bonus, SHALL award the seller 30 resale green credits, and SHALL record a payout-released event at int(0.92 × sale price).
11. IF a buyer attempts to buy an auction that is not active or a listing that is no longer available, THEN THE NextBestOwner_Engine SHALL respond with HTTP 409 and decline the purchase.
12. THE NextBestOwner_Engine SHALL provide a demo control to force a single price step and a demo control to rematch buyers, each operating only on active auctions.
13. WHEN matching is rerun for an auction, THE NextBestOwner_Engine SHALL drop existing edges, rebuild the ranked set, and re-alert all tiers up to the current tier at the current price.

### Requirement 17: Peer-to-Peer Resale — Resale Initiation and Warranty Transfer

**User Story:** As a buyer who wants to resell, I want to list either a past platform purchase or a brand-new external item, so that I can pass it to its next owner with verifiable warranty.

#### Acceptance Criteria

1. WHEN a buyer resells a past platform order, THE NextBestOwner_Engine SHALL reuse the existing unit, the price the buyer paid (the originating listing price) as the original price, and the catalog reference image for image-comparison grading.
2. WHEN a buyer resells a brand-new external item, THE NextBestOwner_Engine SHALL create an EXTERNAL product and a NEW unit owned by the buyer on the fly with no reference image, so grading runs in anomaly/quality mode.
3. WHEN reselling from an order, THE NextBestOwner_Engine SHALL anchor the unit's purchase date to the original delivery date (or the order creation date when delivery is unknown), so the Health Card can show remaining manufacturer warranty transferred to the next buyer.
4. WHEN reselling from a DELIVERED order, THE NextBestOwner_Engine SHALL transition the originating order to SETTLED so it drops off the returnable and resale-candidate lists.
5. WHEN computing item age for resale pricing from an order, THE NextBestOwner_Engine SHALL derive age in months as max(0, days since the delivery/creation anchor ÷ 30).
6. IF a resell request supplies neither an order id nor the complete external-item fields (title, category, positive MRP, positive original price), THEN THE NextBestOwner_Engine SHALL reject the request with HTTP 400.
7. IF a resell request supplies an order whose unit the buyer no longer owns, or a unit that already has an ACTIVE or RESERVED listing, THEN THE NextBestOwner_Engine SHALL reject the request with HTTP 409.
8. IF a resell request requires at least one photo and none is provided or the photos are invalid, THEN THE NextBestOwner_Engine SHALL reject the request with HTTP 400.
9. WHEN resale grading completes, THE NextBestOwner_Engine SHALL price the item, create a USER_RESALE listing at the ceiling price, transition the unit to RELISTED, match buyers, alert tier 0, and schedule the first price step.
10. WHEN a buyer requests their resale alerts, THE NextBestOwner_Engine SHALL return active-auction alerts addressed to them ordered by tier then rank (best fit first), each with the current price and green-credit bonus, and SHALL mark newly seen alerts (SENT) as VIEWED.
11. IF a resell request references an order id that does not exist or does not belong to the requesting buyer, THEN THE NextBestOwner_Engine SHALL respond with HTTP 404.
12. WHEN a resell request is accepted, THE NextBestOwner_Engine SHALL respond with HTTP 201 and the created resale request and listing context.

### Requirement 18: Green Credits — Account, Transactions, and Rewards

**User Story:** As a buyer, I want to earn green credits for sustainable behaviour and redeem them, so that I am rewarded at every touchpoint.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL maintain exactly one green-credit account per user, with a balance that never drops below 0, and an append-only transaction log in which each transaction records a signed integer amount (positive for an earn, negative for a spend), a type label of at most 30 characters, a description of at most 200 characters, and an optional positive-integer reference id.
2. WHEN credits are awarded to a user, THE Orbit_Platform SHALL create the user's account if it does not already exist, SHALL increase the balance by the awarded amount, and SHALL append one transaction recording the amount, type, description, and reference id.
3. THE Orbit_Platform SHALL award green credits at each defined touchpoint with these fixed amounts: 20 for buying a user-resale item, 25 for buying a facility-relist item, 5 for an untouched return, the keep-it offer's specified credit amount for accepting that offer, 20 as the Dutch-auction base purchase award, a Dutch-auction price-drop bonus between 0 and 40 inclusive, 30 for reselling as a seller, and 15 for a seller donation.
4. WHEN a buyer completes a Dutch-auction purchase, THE Orbit_Platform SHALL set the price-drop credit bonus to 0 when the current price equals the auction ceiling, and SHALL scale the bonus upward as the price descends, reaching its maximum of 40 credits when the current price equals the auction floor.
5. WHEN a buyer requests their credit balance, THE Orbit_Platform SHALL return the current balance, the total earned (sum of positive transactions), the total spent (absolute sum of negative transactions), and impact statistics.
6. WHEN a buyer requests their credit history, THE Orbit_Platform SHALL return at most the 50 most recent transactions, ordered newest first.
7. THE Orbit_Platform SHALL maintain a rewards-store catalog seeded idempotently with the default rewards so that repeated seeding never creates duplicates, each reward carrying a title, description, positive credit cost, icon, and an active flag.
8. WHEN a buyer claims a reward that is active and whose credit cost is less than or equal to the buyer's balance, THE Orbit_Platform SHALL, within one atomic transaction, deduct the cost from the balance, append one negative transaction, record one reward claim, and return the updated balance.
9. IF a buyer claims an active reward whose cost exceeds their balance, THEN THE Orbit_Platform SHALL reject the claim with HTTP 400, SHALL leave the balance and transaction log unchanged, and SHALL indicate the number of additional credits required (cost minus current balance).
10. IF a buyer claims a reward that does not exist or is not active, THEN THE Orbit_Platform SHALL reject the claim with HTTP 404 and SHALL leave the balance unchanged.

### Requirement 19: Seller Portal — Catalog, Rules, and Auto-Disposition

**User Story:** As a seller, I want to list products and define rules that automatically dispose of returned units, so that I get automation not another dashboard.

#### Acceptance Criteria

1. WHEN a seller creates a product supplying a title, category, MRP, optional image, and an initial stock count, THE Orbit_Platform SHALL validate the image when one is provided, SHALL create the product, and SHALL create one NEW listing priced at the product's MRP for each stock unit, clamping the stock count into the range 1 to 50 inclusive (values below 1 become 1, values above 50 become 50).
2. IF a product-creation request omits a non-empty title, omits a non-empty category, supplies an MRP that is not a positive integer, or supplies a non-numeric MRP or stock value, THEN THE Orbit_Platform SHALL reject the request with HTTP 400.
3. WHEN a seller requests their catalog, THE Orbit_Platform SHALL return only that seller's products, ordered newest first.
4. THE Orbit_Platform SHALL model a SellerRule with a minimum grade (default B), a minimum recovery percentage (default 60), an action of AUTO_RELIST, LIQUIDATE, or DONATE (default AUTO_RELIST), and an active flag (default true).
5. THE Orbit_Platform SHALL treat a SellerRule as matching a unit only when the unit has an assigned grade, a non-null estimated value, and a non-zero product MRP, AND the unit's grade is at least as good as the rule's minimum grade (ordering A above B above C above D), AND the unit's recovery percentage — computed as estimated value × 100 integer-divided by MRP — is greater than or equal to the rule's minimum recovery percentage.
6. WHEN a seller requests their returns inbox, THE Orbit_Platform SHALL return that seller's AT_FACILITY units ordered most-recently-updated first, each annotated with the action and rule id of the first active rule that matches it, or null when no active rule matches.
7. WHEN a seller applies an action to one of their AT_FACILITY units, THE Orbit_Platform SHALL execute that action, and WHEN the action is DONATE THE Orbit_Platform SHALL award the seller 15 green credits; IF the supplied action is not one of AUTO_RELIST, LIQUIDATE, or DONATE THEN THE Orbit_Platform SHALL respond with HTTP 400; IF no AT_FACILITY unit owned by the seller matches the supplied id THEN THE Orbit_Platform SHALL respond with HTTP 404.
8. WHEN a seller runs bulk apply, THE Orbit_Platform SHALL evaluate that seller's active rules in ascending rule-id order across the inbox, SHALL apply the action of the first matching rule to each matching unit, and SHALL return the count of handled units and the count of remaining unmatched units.
9. WHEN an AUTO_RELIST action runs, THE Orbit_Platform SHALL price the unit and open a Dutch auction through the Next Best Owner engine with the seller as both owner and lister.
10. THE Orbit_Platform SHALL allow a seller to create, list, update, and delete only their own rules, and SHALL restrict all seller-portal endpoints to authenticated users with role SELLER.

### Requirement 20: Facility Portal — Intake, Relist, Watchlist, and Storage Engine

**User Story:** As a facility operator, I want to receive, grade, relist, and monitor units with automatic storage accounting, so that inventory is processed efficiently without unbounded cost.

#### Acceptance Criteria

1. WHEN a facility operator requests incoming units, THE Orbit_Platform SHALL return all RETURN_PENDING units ordered oldest first (least-recently-updated first).
2. WHEN a facility operator receives a returned unit identified by unit id, THE Orbit_Platform SHALL record the untouched verification flag and the arrival time, SHALL grade the unit by preferring the most recent completed multi-source assessment that carries a suggested grade and otherwise falling back to the heuristic grader, SHALL set the estimated value from the pricing helper, SHALL transition the unit to AT_FACILITY, and SHALL transition the originating order to REFUNDED; IF no RETURN_PENDING unit matches the supplied id THEN THE Orbit_Platform SHALL respond with HTTP 404.
3. WHEN a unit is received, THE Orbit_Platform SHALL ensure a disposition recommendation exists, computing one inline when none has completed, and SHALL append a routing-recommendation event; IF computing the recommendation fails THEN THE Orbit_Platform SHALL complete intake without the recommendation rather than failing receipt.
4. WHEN a facility operator relists an AT_FACILITY unit, THE Orbit_Platform SHALL price it and open a Dutch auction through the Next Best Owner engine with the operator as owner and lister; IF the unit already has a listing in the ACTIVE or RESERVED state THEN THE Orbit_Platform SHALL respond with HTTP 409; IF no AT_FACILITY unit matches the supplied id THEN THE Orbit_Platform SHALL respond with HTTP 404.
5. WHEN a facility operator requests the watchlist, THE Orbit_Platform SHALL return AT_FACILITY and RELISTED units that have a non-null, non-zero estimated value, ranked by descending ratio of accrued storage cost to estimated value so that units closest to liquidation appear first.
6. WHEN a facility operator manually disposes a unit, THE Orbit_Platform SHALL accept only a target of LIQUIDATE or DONATED, SHALL withdraw any ACTIVE listing on the unit, and SHALL transition the unit to the target state; IF the target is any other value THEN THE Orbit_Platform SHALL respond with HTTP 400; IF the unit is not in the AT_FACILITY or RELISTED state THEN THE Orbit_Platform SHALL respond with HTTP 404.
7. WHEN the storage clock advances one day, THE Storage_Engine SHALL add the unit's category daily storage rate — 8 ₹/day for electronics, 3 ₹/day for apparel, 4 ₹/day for footwear, and 5 ₹/day for any other category — to the accrued storage cost of every unit on the facility floor (AT_FACILITY or RELISTED units with a recorded arrival time).
8. WHEN a unit's accrued storage cost reaches or exceeds its estimated value, THE Storage_Engine SHALL withdraw any ACTIVE listing on the unit and SHALL transition the unit to LIQUIDATE.
9. WHILE a unit remains listed with a defined fair-value floor, THE Storage_Engine SHALL step its listing price down by 10% every 7 accrued days, SHALL never set the price below the fair-value floor, SHALL apply the step only when it strictly lowers the current price, and SHALL append a price-stepdown event when a step occurs.
10. THE Orbit_Platform SHALL expose storage accrual both as a management command and as a demo "simulate day" endpoint executing identical accrual logic, with the endpoint restricted to authenticated users with role FACILITY.

### Requirement 21: Provider Abstraction and Graceful Degradation

**User Story:** As a platform operator, I want AI providers configured rather than coded and every AI call to degrade gracefully, so that the system runs identically offline and adds capacity without code changes.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL define OpenAI-compatible providers (gemini, openai, modal) in a settings table holding base URL, API key, model, optional reasoning effort, and a requires-key flag.
2. WHEN a VLM, rerouting LLM, return-prevention LLM, or embedding provider is needed, THE Provider_Registry SHALL resolve it from settings at runtime, cache the resolved instance per process, and SHALL never raise an exception from resolution.
3. WHEN a provider is set to "auto", THE Provider_Registry SHALL select, in the order gemini then openai then modal, the first OpenAI-compatible provider that has a model and either an API key or a keyless self-hosted base URL, and otherwise SHALL select the deterministic mock.
4. IF a configured hosted provider is missing its required API key, THEN THE Provider_Registry SHALL fall back to the deterministic mock rather than make a doomed network call.
5. WHEN any AI provider call or response parse fails, THE Orbit_Platform SHALL fall back to a deterministic mock or rules result so the operation completes without surfacing an error to the user.
6. THE VLM source SHALL call the resolved provider with the configured VLM timeout (default 30 seconds, `GRADING_VLM_TIMEOUT`) and at most one transport-level retry, and SHALL make at most three completion attempts in total across knob-degradation retries.
7. WHEN an OpenAI-compatible model rejects the `reasoning_effort` knob with an HTTP 400, THE Orbit_Platform SHALL drop that knob, remember the rejection per worker process, and retry the call without falling back to the mock.
8. WHEN an OpenAI-compatible model rejects the `json_schema` response format with an HTTP 400, THE Orbit_Platform SHALL degrade to the `json_object` response format, remember the rejection per worker process, and retry the call without falling back to the mock.
9. IF an HTTP 400 BadRequest is not a recognized knob or response-format rejection, THEN THE Orbit_Platform SHALL re-raise it so the caller falls back to the deterministic strategy.
10. WHILE zero API keys are configured, THE Orbit_Platform SHALL run fully offline with every flow functioning and every test passing using deterministic mocks.
11. THE Orbit_Platform SHALL resolve durable VLM-derived size class and fragility once and reuse them, so routing and future assessments do not re-run the model.

### Requirement 22: Frontend Single-Page Application

**User Story:** As a user, I want a responsive web app for shopping, reselling, tracking orders, and managing rewards, so that I can use every platform capability through the browser.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL provide a React 18 single-page application built with Vite and React Router using vanilla CSS, served as static assets behind Nginx.
2. THE SPA SHALL provide pages for Shop, Pre-Loved, Product detail, Orders, Resell, Next Owner, Health Card, Rewards, Profile, Seller Portal, Facility Portal, Login, and Register.
3. THE SPA SHALL provide a session-based authentication context that loads the current user on start and exposes login, register, and logout actions.
4. THE SPA fetch wrapper SHALL retry GET requests up to 6 attempts with exponential backoff starting at approximately 400 ms when a network error or an HTTP 5xx response occurs, and SHALL attach the CSRF token to unsafe (non-GET) requests, which it issues as a single attempt.
5. THE Pre-Loved page SHALL present a "Recommended for you" rail of auctions to which the signed-in buyer is an alerted match plus a general grid, and SHALL poll every 3 seconds (clearing the poll on unmount) to animate the descending Dutch price and the growing green-credit bonus.
6. WHEN a buyer views the Orders page, THE SPA SHALL allow the buyer to accept or decline a pending keep-it offer.
7. THE SPA SHALL provide reusable components including a photo picker that extracts client-side EXIF metadata, a toast, icons, a confirm modal, a product carousel, and resale alerts, plus motion utilities for count-up and scroll detection.
8. WHEN a buyer uploads return photos, THE SPA SHALL extract per-photo EXIF metadata before compression and submit it as a JSON array index-aligned with the uploaded photos so the grading pipeline can analyze it.

### Requirement 23: Infrastructure, Scalability, and Configuration

**User Story:** As a platform operator, I want a production-shaped, idempotent, configurable deployment, so that the system boots reliably, scales by configuration, and stores media flexibly.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL be deployable via Docker Compose with services for PostgreSQL 16, Redis 7 (broker, cache, and sessions), a Gunicorn backend (worker count configurable via `GUNICORN_WORKERS`, default 3), a Celery worker, and an Nginx frontend.
2. WHEN the backend boots, THE Orbit_Platform SHALL run database migrations idempotently — retrying every 2 seconds until the database is ready — then collect static files, then conditionally seed demo data when `SEED_ON_BOOT=1`, then serve.
3. THE Orbit_Platform SHALL auto-discover Celery tasks from every app's tasks module and SHALL run tasks inline when `CELERY_TASK_ALWAYS_EAGER` is enabled (tests and no-broker demos).
4. WHERE `USE_S3` is enabled, THE Orbit_Platform SHALL store media in S3 (optionally fronted by a CloudFront custom domain); otherwise it SHALL store media on a local volume served by the application, mounting a shared media volume between the backend and worker.
5. THE Orbit_Platform SHALL run text embeddings only on the worker process, baking the MiniLM model into the worker image for deterministic offline loading, and SHALL allow building the image without the embedding stack so matching falls back to the mock embedder.
6. THE Orbit_Platform SHALL expose all business knobs as configuration, including storage daily rates, return windows, rerouting rate-per-km and fragility multipliers, repair and resale factors, sell-through base, fraud-risk weights, keep-it offer thresholds and split, match weights, recency half-life, auction tier size, max tier, step percentage, interval, start premium, reserve discount, pricing rho/gamma/lambda/band-width constants, category depreciation rates, and green-credit award amounts.
7. WHEN `REDIS_URL` is configured, THE Orbit_Platform SHALL use the Redis cache backend and SHALL route sessions through it automatically; otherwise it SHALL use a local-memory cache.
8. THE Orbit_Platform SHALL surface application logs for grading, rerouting, marketplace, services, facility, core, catalog, greencredits, and nextowner at the configured level (`LOG_LEVEL`, default INFO) while keeping third-party logs at WARNING.
9. THE Orbit_Platform SHALL provide a seed command that creates demo data comprising 25 products with real photos and 5 users with size profiles and geo coordinates.
10. THE Orbit_Platform SHALL set the time zone to Asia/Kolkata and use timezone-aware datetimes throughout.

### Requirement 24: Deterministic Fallback AI Services

**User Story:** As a platform operator, I want network-free deterministic grading and pricing helpers, so that intake, relisting, and tests work without any external model.

#### Acceptance Criteria

1. THE Orbit_Platform SHALL provide deterministic, network-free helpers for grading, pricing, and fit-check that produce identical outputs for identical inputs.
2. WHEN facility intake has no completed multi-source assessment, THE Orbit_Platform SHALL grade the unit using the deterministic heuristic grader based only on the untouched claim and any return photos.
3. WHEN a unit is priced for relisting, THE Orbit_Platform SHALL derive its estimated value and fair-value band deterministically from MRP and grade.
4. THE deterministic mock VLM SHALL produce a structured grading verdict consistent with the real VLM output schema (quality, fraud flags, match decision, match confidence, suggested grade, size class, fragility, category) so that downstream blending behaves identically in offline mode.
