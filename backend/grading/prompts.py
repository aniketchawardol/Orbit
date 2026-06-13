"""VLM prompt construction + output normalization for return grading.

The model is told to *decide* the inspection criteria from the product category
itself (electronics -> scratches/dents/missing parts; clothing -> holes/stains/
cuts; etc.), and other type of anomalies for other categories. Inspect every uploaded image, compare them to the reference (listed)
photos, and emit strict JSON. We never trust the buyer's words or photos alone,
so the prompt explicitly asks the model to cross-check the stated reason against
what it actually sees and to flag manipulation.
"""

import base64

GRADES = ("A", "B", "C", "D")

SYSTEM_PROMPT = (
    "You are a meticulous product-returns inspector for a circular marketplace. "
    "You receive a product's catalog details, the buyer's stated return reason, "
    "buyer-uploaded photos of the returned item, and the original listing "
    "(reference) photos. Your job is to assess physical condition and detect "
    "fraud or misrepresentation. You DECIDE which inspection criteria apply based "
    "on the product category (for electronics look for scratches, dents, cracks, "
    "missing parts/accessories; for clothing look for holes, stains, tears, "
    "stretching, missing tags; adapt for other categories). Never assume the "
    "buyer's reason or photos are truthful — verify against the reference images "
    "and look for signs of edited/screenshotted/reused images. "
    "Respond with ONLY a single JSON object, no prose."
)

# Shape we ask the model to return (described in-prompt; we also hard-normalize).
_OUTPUT_SHAPE = """Return JSON with EXACTLY these keys:
{
  "criteria": [string],              // inspection criteria you chose for this category
  "per_image": [                     // one entry per uploaded image, in order
    {"index": int, "visible_defects": [string], "quality": float, "notes": string}
  ],
  "defects": [string],               // distinct defects seen across all images
  "item_matches_reference": boolean, // does the returned item match the listed product?
  "match_confidence": float,         // 0..1
  "condition_summary": string,       // one or two sentences
  "suggested_grade": "A"|"B"|"C"|"D",// A=like new, B=good, C=worn, D=poor
  "quality_estimate": float,         // 0..1 overall physical condition (1=perfect)
  "fraud_flags": [string],           // e.g. "reason_mismatch","image_edited","wrong_item","reused_image"
  "confidence": float                // 0..1 your confidence in this assessment
}
All floats in [0,1]. If you cannot see something, say so in notes and lower confidence."""


def _data_uri(img):
    b64 = base64.b64encode(img.data).decode()
    return f"data:{img.mime};base64,{b64}"


def _context_text(req):
    p = req.product or {}
    c = req.claim or {}
    attrs = p.get("attributes") or {}
    lines = [
        "PRODUCT UNDER RETURN",
        f"- Title: {p.get('title', 'Unknown')}",
        f"- Category: {p.get('category', 'unknown')}",
        f"- MRP: {p.get('mrp', 'n/a')}",
    ]
    if p.get("description"):
        lines.append(f"- Description: {p['description']}")
    if attrs:
        attr_str = ", ".join(f"{k}={v}" for k, v in attrs.items())
        lines.append(f"- Attributes: {attr_str}")
    lines += [
        "",
        "BUYER CLAIM (treat as unverified)",
        f"- Stated reason: {c.get('reason', 'OTHER')}",
        f"- Claims unopened/untouched: {bool(c.get('claimed_untouched'))}",
    ]
    if c.get("comment"):
        lines.append(f"- Buyer comment: {c['comment']}")
    n_up = len(req.uploaded or [])
    n_ref = len(req.reference or [])
    lines += [
        "",
        f"You are given {n_up} buyer-uploaded image(s) followed by {n_ref} "
        "reference (listed) image(s). Inspect the uploaded images, compare them "
        "to the reference images, decide the category-appropriate criteria, and "
        "verify the stated reason against what you actually see.",
        "",
        _OUTPUT_SHAPE,
    ]
    return "\n".join(lines)


def build_vlm_messages(req):
    """Build OpenAI-style chat messages with text + inline image parts."""
    content = [{"type": "text", "text": _context_text(req)}]
    for i, img in enumerate(req.uploaded or []):
        content.append({"type": "text", "text": f"[uploaded image {i}]"})
        content.append({"type": "image_url", "image_url": {"url": _data_uri(img)}})
    for i, img in enumerate(req.reference or []):
        content.append({"type": "text", "text": f"[reference image {i}]"})
        content.append({"type": "image_url", "image_url": {"url": _data_uri(img)}})
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def _clamp01(v, default=0.0):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default


def _str_list(v):
    if not isinstance(v, list):
        return []
    return [str(x) for x in v if x is not None]


def normalize_vlm_output(data, n_uploaded=0):
    """Coerce raw model JSON into our stable schema; tolerate missing/odd keys."""
    data = data if isinstance(data, dict) else {}

    # Accept a leading grade letter only when it stands alone (e.g. "A",
    # "A (like new)", "B - good"); reject words that merely start with one
    # ("amazing" must not be read as grade A).
    raw_grade = str(data.get("suggested_grade", "")).strip().upper()
    grade = raw_grade[:1]
    if grade not in GRADES or (len(raw_grade) > 1 and raw_grade[1].isalpha()):
        grade = "B"

    per_image = []
    raw_pi = data.get("per_image")
    if isinstance(raw_pi, list):
        for idx, entry in enumerate(raw_pi):
            entry = entry if isinstance(entry, dict) else {}
            per_image.append(
                {
                    "index": int(entry.get("index", idx) or idx),
                    "visible_defects": _str_list(entry.get("visible_defects")),
                    "quality": _clamp01(entry.get("quality"), 0.5),
                    "notes": str(entry.get("notes", "")),
                }
            )

    return {
        "criteria": _str_list(data.get("criteria")),
        "per_image": per_image,
        "defects": _str_list(data.get("defects")),
        "item_matches_reference": bool(data.get("item_matches_reference", True)),
        "match_confidence": _clamp01(data.get("match_confidence"), 0.5),
        "condition_summary": str(data.get("condition_summary", "")),
        "suggested_grade": grade,
        "quality_estimate": _clamp01(data.get("quality_estimate"), 0.5),
        "fraud_flags": _str_list(data.get("fraud_flags")),
        "confidence": _clamp01(data.get("confidence"), 0.5),
        "source": str(data.get("source", "")),
    }
