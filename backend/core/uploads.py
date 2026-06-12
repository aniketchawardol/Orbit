"""Shared photo-upload helper: validates, stores to MEDIA_ROOT, returns paths."""

import uuid
from pathlib import Path

from django.core.files.storage import default_storage

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 8 * 1024 * 1024  # 8 MB per photo
MAX_PHOTOS = 6


def validate_image(f):
    """Single-image validation (e.g. product catalog shot). Raises ValueError."""
    ext = Path(f.name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}.")
    if f.size > MAX_BYTES:
        raise ValueError(f"{f.name} exceeds 8 MB.")
    return f


def save_photos(files, subdir):
    """Persist uploaded files under media/<subdir>/. Returns list of relative paths.

    Raises ValueError with a user-facing message on any validation failure.
    """
    if len(files) > MAX_PHOTOS:
        raise ValueError(f"Max {MAX_PHOTOS} photos allowed.")
    paths = []
    for f in files:
        ext = Path(f.name).suffix.lower()
        if ext not in ALLOWED_EXT:
            raise ValueError(f"Unsupported file type: {ext or 'unknown'}.")
        if f.size > MAX_BYTES:
            raise ValueError(f"{f.name} exceeds 8 MB.")
        rel = f"{subdir}/{uuid.uuid4().hex}{ext}"
        default_storage.save(rel, f)
        paths.append(rel)
    return paths
