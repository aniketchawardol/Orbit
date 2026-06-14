"""Deterministic accessory-compatibility fallback (no network).

Mirrors the LLM verdict shape so the demo works fully offline. An accessory
declares the device model it fits (``compatible_model``); a device declares its
own ``model``. We compare the accessory's target model against the models the
shopper owns: same product family (e.g. both "iphone") but a different variant
(15 vs 14) means it will not fit — warn. If the shopper owns no device in that
family, we stay silent (it may be a gift or a new device).
"""

import re


def _split(model: str):
    """Split a model name into (family, variant), e.g. "iPhone 15" -> ("iphone", "15")."""
    tokens = re.findall(r"[a-z]+|\d+", (model or "").lower())
    if not tokens:
        return "", ""
    family = tokens[0]
    variant = "".join(tokens[1:])
    return family, variant


def check_compat(target_model: str, owned: list):
    """Compare the accessory's target model against owned devices.

    Returns {"compatible": bool, "warning": str}. Only warns when the shopper
    owns one or more devices in the accessory's product line (same family) and
    NONE of them matches the target model's variant. Owning devices from a
    different line (e.g. an iPhone while buying a Galaxy case) is irrelevant.
    """
    conflict = _family_conflict(target_model, owned)
    if conflict is None:
        return {"compatible": True, "warning": ""}
    return {
        "compatible": False,
        "warning": f"You own a {conflict.get('model')} — this fits {target_model}.",
    }


def _family_conflict(target_model: str, owned: list):
    """Return an owned device that conflicts with ``target_model`` (same product
    line, no variant match), or None when there is no conflict.

    No conflict means either: the shopper owns nothing in this line, or they own
    a device in this line whose variant matches the accessory's target.
    """
    target_family, target_variant = _split(target_model)
    if not target_family:
        return None
    same_family = [
        d for d in owned if _split(d.get("model", ""))[0] == target_family
    ]
    if not same_family:
        return None
    if any(_split(d.get("model", ""))[1] == target_variant for d in same_family):
        return None
    return same_family[0]


def has_family_conflict(target_model: str, owned: list) -> bool:
    """True only when the shopper owns a same-line device that does not fit the
    accessory. Used as a deterministic guard against false-positive warnings."""
    return _family_conflict(target_model, owned) is not None
