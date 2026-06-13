"""Image metadata extraction + fraud anomaly detection.

We combine two views of each image and never trust either alone:
- client_metadata: EXIF the frontend read from the ORIGINAL file *before* it was
  compressed for upload (camera make/model, capture time, software, dimensions).
- server_metadata: what we can derive from the stored bytes (dimensions/format).

From these we raise weighted anomaly flags (edited/screenshot/stale capture/etc.)
that feed the fraud score. Signals are intentionally soft — any one is weak, but
several together are meaningful.
"""

import logging
from datetime import datetime, timedelta
from io import BytesIO

log = logging.getLogger(__name__)

# Flag -> contribution toward an image's fraud weight (0..1, summed then clamped).
WEIGHTS = {
    "stale_capture": 0.5,      # photo predates the delivery — likely not the item
    "future_capture": 0.5,     # capture timestamp in the future — clock/forgery
    "software_edited": 0.4,    # EXIF Software shows an image editor
    "dimension_mismatch": 0.4,  # client-declared vs stored dimensions inconsistent
    "is_screenshot": 0.35,     # looks like a screenshot, not a photo
    "no_capture_time": 0.15,   # no capture timestamp at all
    "no_camera_exif": 0.15,    # no camera make/model (downloaded image?)
    "low_resolution": 0.1,     # too small to inspect reliably
}

_EDITOR_HINTS = ("photoshop", "gimp", "lightroom", "snapseed", "pixlr", "paint", "canva")
_MIN_PIXELS = 480 * 480


def _get(meta: dict, *keys):
    for k in keys:
        if k in meta and meta[k] not in (None, ""):
            return meta[k]
        low = {str(mk).lower(): mv for mk, mv in meta.items()}
        if k.lower() in low and low[k.lower()] not in (None, ""):
            return low[k.lower()]
    return None


def _parse_exif_dt(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value))
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def server_metadata_from_bytes(data: bytes) -> dict:
    """Derive basic facts from stored bytes (dimensions, format, EXIF presence)."""
    out = {"width": None, "height": None, "format": None, "has_exif": False}
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as im:
            out["width"], out["height"] = im.size
            out["format"] = im.format
            exif = getattr(im, "getexif", lambda: None)()
            out["has_exif"] = bool(exif)
    except Exception:  # noqa: BLE001
        log.warning("server metadata extraction failed", exc_info=True)
    return out


def analyze_image(client_meta: dict, server_meta: dict, reference_time=None) -> dict:
    """Return {flags: [...], weight: float, details: {...}} for one image."""
    client_meta = client_meta or {}
    server_meta = server_meta or {}
    flags = []
    details = {}

    make = _get(client_meta, "Make", "make")
    model = _get(client_meta, "Model", "model")
    software = _get(client_meta, "Software", "software")
    capture = _parse_exif_dt(_get(client_meta, "DateTimeOriginal", "CreateDate", "DateTime"))

    if software and any(h in str(software).lower() for h in _EDITOR_HINTS):
        flags.append("software_edited")
        details["software"] = str(software)

    if not make and not model:
        flags.append("no_camera_exif")
    if capture is None:
        flags.append("no_capture_time")

    # Screenshot heuristic: explicitly typed, or no camera EXIF + PNG.
    declared_type = str(_get(client_meta, "type", "mime") or "").lower()
    if "screenshot" in str(software or "").lower() or (
        not make and not model and (server_meta.get("format") == "PNG")
    ):
        if "screenshot" not in flags:
            flags.append("is_screenshot")

    # Capture-time sanity against the delivery time.
    if capture is not None:
        details["capture_time"] = capture.isoformat()
        now = datetime.now()
        if capture > now + timedelta(days=1):
            flags.append("future_capture")
        if reference_time is not None:
            ref = reference_time
            if ref.tzinfo is not None:
                ref = ref.replace(tzinfo=None)
            if capture < ref - timedelta(days=1):
                flags.append("stale_capture")
                details["delivered_at"] = ref.isoformat()

    # Resolution: prefer original (pre-compression) dimensions from the client.
    ow = _get(client_meta, "originalWidth", "ExifImageWidth", "ImageWidth", "width")
    oh = _get(client_meta, "originalHeight", "ExifImageHeight", "ImageHeight", "height")
    try:
        if ow and oh and int(ow) * int(oh) < _MIN_PIXELS:
            flags.append("low_resolution")
    except (TypeError, ValueError):
        pass

    # Dimension mismatch: stored image larger than the claimed original means the
    # "original" was fabricated/shrunk (compression only ever reduces size here).
    sw, sh = server_meta.get("width"), server_meta.get("height")
    try:
        if ow and oh and sw and sh and (sw > int(ow) * 1.05 or sh > int(oh) * 1.05):
            flags.append("dimension_mismatch")
    except (TypeError, ValueError):
        pass

    weight = min(1.0, sum(WEIGHTS.get(f, 0.0) for f in flags))
    return {"flags": flags, "weight": round(weight, 3), "details": details}


def summarize(per_image: list) -> dict:
    """Blend per-image findings into a single metadata fraud signal (0..1)."""
    weights = [img.get("weight", 0.0) for img in per_image]
    all_flags = sorted({f for img in per_image for f in img.get("flags", [])})
    if weights:
        worst = max(weights)
        mean = sum(weights) / len(weights)
        signal = round(min(1.0, 0.6 * worst + 0.4 * mean), 3)
    else:
        signal = 0.0
    return {
        "metadata_fraud_signal": signal,
        "flags": all_flags,
        "per_image": per_image,
    }
