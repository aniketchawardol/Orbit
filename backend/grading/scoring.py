"""Blend multi-source signals into quality / fraud / confidence + a grade.

Design principle: no single source is trusted on its own. The VLM can be fooled
by a doctored photo; the buyer's stated reason can be false; history is only a
prior. We combine them with explicit weights, cross-check the stated reason
against what the VLM sees, and lower confidence when sources disagree or data is
missing. Every number is accompanied by an explainable breakdown stored on the
assessment so the (deferred) decision engine and auditors can re-reason.
"""

import statistics

# Fraud signal weights (renormalized over whichever sources are available).
FRAUD_WEIGHTS = {
    "vlm": 0.30,
    "similarity": 0.25,
    "metadata": 0.20,
    "history": 0.15,
    "reason_mismatch": 0.10,
}

# dHash similarity at/above this looks like "same item"; below ramps up suspicion.
_SIM_OK = 0.6


def _clamp(v, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return lo


def _grade_from_quality(q):
    if q >= 0.85:
        return "A"
    if q >= 0.6:
        return "B"
    if q >= 0.35:
        return "C"
    return "D"


def _worse(g1, g2):
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    return g1 if order.get(g1, 1) >= order.get(g2, 1) else g2


def _reason_mismatch(claim, vlm):
    """Cross-check the buyer's stated reason against the VLM's observations."""
    reason = str((claim or {}).get("reason", "OTHER")).upper()
    q = _clamp(vlm.get("quality_estimate"), 0.0, 1.0)
    defects = vlm.get("defects") or []
    matches = bool(vlm.get("item_matches_reference", True))
    match_conf = _clamp(vlm.get("match_confidence"), 0.0, 1.0)

    if reason == "DEFECTIVE" and q >= 0.8 and not defects:
        return 0.5, "Claimed defective but item looks intact"
    if reason == "DIDNT_MATCH" and matches and match_conf >= 0.6:
        return 0.4, "Claimed item didn't match, but it matches the listing"
    if reason in ("CHANGED_MIND", "OTHER") and (q < 0.4 or len(defects) >= 2):
        return 0.4, "Benign reason but item shows significant damage"
    return 0.0, ""


def blend(vlm, similarity, metadata, history, claim=None):
    """Return a dict with quality_score, fraud_score, confidence,
    suggested_grade and an explainable `scores` breakdown."""
    vlm = vlm or {}
    similarity = similarity or {}
    metadata = metadata or {}
    history = history or {}

    vlm_source = str(vlm.get("source", "")) or "unknown"
    vlm_is_real = vlm_source not in ("", "unknown", "mock")

    # --- quality ---
    quality_score = _clamp(vlm.get("quality_estimate"), 0.0, 1.0)

    # --- individual fraud signals (each 0..1) ---
    signals = {}

    # VLM-derived: wrong item + explicit fraud flags.
    matches = bool(vlm.get("item_matches_reference", True))
    flags = vlm.get("fraud_flags") or []
    vlm_fraud = (0.0 if matches else 0.6) + min(0.4, 0.15 * len(flags))
    signals["vlm"] = _clamp(vlm_fraud)

    # Image similarity (may be unavailable when there are no reference photos).
    overall = similarity.get("overall")
    if overall is not None:
        sim_signal = _clamp((_SIM_OK - float(overall)) / _SIM_OK)
        if similarity.get("duplicate_pairs"):
            sim_signal = _clamp(sim_signal + 0.3)
        signals["similarity"] = sim_signal

    # EXIF/metadata anomalies.
    signals["metadata"] = _clamp(metadata.get("metadata_fraud_signal", 0.0))

    # Buyer history.
    signals["history"] = _clamp(history.get("history_fraud_signal", 0.0))

    # Stated-reason vs observations.
    rm_signal, rm_note = _reason_mismatch(claim, vlm)
    signals["reason_mismatch"] = _clamp(rm_signal)

    # --- weighted fraud score over available signals ---
    active = {k: v for k, v in signals.items() if k in FRAUD_WEIGHTS}
    wsum = sum(FRAUD_WEIGHTS[k] for k in active)
    fraud_score = (
        sum(FRAUD_WEIGHTS[k] * v for k, v in active.items()) / wsum if wsum else 0.0
    )
    fraud_score = round(_clamp(fraud_score), 3)

    # --- confidence: data availability + cross-source agreement + VLM self-conf ---
    vlm_conf = _clamp(vlm.get("confidence"), 0.0, 1.0)
    base = vlm_conf * (1.0 if vlm_is_real else 0.6)
    availability = len(active) / len(FRAUD_WEIGHTS)
    if len(active) >= 2:
        spread = statistics.pstdev(list(active.values()))
        agreement = _clamp(1.0 - spread)
    else:
        agreement = 0.5
    confidence = round(_clamp(0.5 * base + 0.25 * availability + 0.25 * agreement), 3)

    # --- grade: conservative reconciliation of VLM grade and quality-derived grade ---
    vlm_grade = str(vlm.get("suggested_grade", "B")).upper()[:1] or "B"
    if vlm_grade not in ("A", "B", "C", "D"):
        vlm_grade = "B"
    quality_grade = _grade_from_quality(quality_score)
    suggested_grade = _worse(vlm_grade, quality_grade)

    all_fraud_flags = sorted(
        set(flags)
        | set(metadata.get("flags", []))
        | set(history.get("flags", []))
        | ({"reason_mismatch"} if rm_signal else set())
        | ({"low_image_similarity"} if signals.get("similarity", 0) >= 0.5 else set())
    )

    scores = {
        "quality": {"value": round(quality_score, 3), "from": "vlm.quality_estimate"},
        "fraud": {
            "value": fraud_score,
            "signals": {k: round(v, 3) for k, v in signals.items()},
            "weights": {k: FRAUD_WEIGHTS[k] for k in active},
            "reason_mismatch_note": rm_note,
        },
        "confidence": {
            "value": confidence,
            "vlm_source": vlm_source,
            "vlm_is_real": vlm_is_real,
            "availability": round(availability, 3),
            "agreement": round(agreement, 3),
        },
        "grade": {
            "value": suggested_grade,
            "vlm_grade": vlm_grade,
            "quality_grade": quality_grade,
            "rule": "conservative: worse of VLM grade and quality-derived grade",
        },
        "fraud_flags": all_fraud_flags,
    }

    return {
        "quality_score": round(quality_score, 3),
        "fraud_score": fraud_score,
        "confidence": confidence,
        "suggested_grade": suggested_grade,
        "scores": scores,
    }
