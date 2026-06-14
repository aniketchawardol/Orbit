# Product — Orbit

Orbit is a full-stack platform that closes the loop on returned, unused, and outgrown products. Every physical item that enters the system is automatically graded for condition, priced, routed to its optimal disposition, and matched to the buyer who wants it most — with sustainability incentives (green credits) at every touchpoint.

## Roles

- **Buyer** (`BUYER`): shops, returns, and resells items. Buyers double as P2P sellers; no separate role needed.
- **Seller** (`SELLER`): lists catalog products, manages a returned-unit inbox, and defines auto-disposition rules.
- **Facility operator** (`FACILITY`, admin-created only): receives, grades, relists, and monitors returned units; manages storage.
- **Platform/Admin**: configures business knobs, providers, and seed data via Django admin.

## Six interconnected capabilities

1. **AI condition grading** — multi-source verdict from buyer photos (VLM + perceptual-hash/colour similarity + EXIF metadata + buyer history + reason-mismatch cross-check), blended with explicit weights and a decisive "wrong item" fraud floor. Five fraud signals renormalized over available data. LLM output parsed through a deterministic JSON recovery layer (`jsonio`). Target < 2s.
2. **Smart rerouting** — chooses RESELL / REFURBISH / P2P / DONATE per unit using a risk-adjusted expected-value model plus an LLM strategy (running in parallel); includes a "keep-it" return-prevention offer (partial cash + credits). LLM is authoritative, EV is fallback.
3. **Trust layer (Product Health Card)** — AI grade, confidence, remaining warranty (calendar-accurate), full append-only event trail, and live price.
4. **Return prevention** — pre-purchase fit guide (declared sizes vs options) and accessory compatibility (LLM + deterministic rules guard), precomputed on login for zero buy-path latency. Warnings surface via a confirmation modal (`ConfirmModal`).
5. **Peer-to-peer resale** — Next Best Owner 5-signal buyer matching (semantic taste, category affinity, budget fit, quality tolerance, green propensity) using a networkx bipartite graph + a self-rescheduling descending-price (Dutch) auction with tiered alert rollout.
6. **Green credits** — earn/redeem currency awarded at every sustainable touchpoint; resale bonus grows as the Dutch price drops. Rewards store with redeemable items.

## Governing principles (non-negotiable)

1. **No single source trusted.** Grading blends five independent fraud signals with cross-source agreement and a fraud floor.
2. **Graceful degradation everywhere.** Every AI call has a deterministic fallback; the system runs identically with zero API keys.
3. **Configuration over code.** Providers, match weights, auction tuning, fraud-risk discounts — all are settings, not code changes.
4. **The unit is the atom.** One physical `ItemUnit` carries its entire lifecycle and an immutable event trail (via `StatefulItem.transition()`).
5. **Economics are explicit.** Every routing decision carries a per-route profit breakdown, inputs, realization probability, and decision source (EV or LLM).

## Authoritative spec

The exhaustive, rebuild-from-scratch specification lives in `.kiro/specs/orbit-platform/`. Treat `requirements.md` there as the source of truth for behavior, thresholds, and formulas.
