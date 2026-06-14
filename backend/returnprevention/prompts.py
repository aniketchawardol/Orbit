"""LLM prompt + response schema for the accessory-compatibility check.

Plain text chat (no images): the model is handed the accessory the shopper is
about to buy (its target device model) and the devices the shopper already owns
(derived from order history), and asked whether the accessory is compatible. The
schema keeps the answer to a single structured object so parsing is reliable and
the warning string stays short.
"""

import json

SYSTEM_PROMPT = (
    "You are a purchase-compatibility checker for an online marketplace. The "
    "shopper is about to buy an accessory that fits ONE specific device model. "
    "You are given the devices the shopper already owns (from their order "
    "history). Your job is to catch the narrow case where the shopper most "
    "likely intends the accessory for a device they own, but it will NOT fit.\n"
    "\n"
    "Follow these steps exactly:\n"
    "1. Identify the accessory's target device line/brand (e.g. an 'iPhone 14 "
    "case' targets Apple iPhones; a 'Galaxy S23 case' targets Samsung Galaxy "
    "phones).\n"
    "2. Look ONLY at owned devices in that SAME line/brand. Devices from a "
    "different brand or product line are IRRELEVANT — ignore them completely.\n"
    "3. Decide:\n"
    "   - INCOMPATIBLE only if the shopper owns a device in that same line whose "
    "model does NOT work with the accessory (e.g. owns an iPhone 15 but the case "
    "fits only an iPhone 14).\n"
    "   - COMPATIBLE if the shopper owns a matching device in that line, OR owns "
    "NO device in that line at all. Owning an unrelated device (e.g. owning an "
    "iPhone while buying a Galaxy case) is COMPATIBLE — never warn for that; the "
    "accessory may be a gift or for a device they will buy.\n"
    "When unsure, choose COMPATIBLE.\n"
    "Respond with ONLY a JSON object: {compatible (bool), warning (string)}. The "
    "warning MUST be empty when compatible. When incompatible, keep it to at most "
    "12 words and name the conflict, e.g. 'You own an iPhone 15 — this case fits "
    "an iPhone 14.'"
)


def build_messages(product, target_model: str, owned: list) -> list:
    owned_lines = (
        "\n".join(
            f"- {d.get('title')} (model: {d.get('model')})" for d in owned
        )
        or "- (no devices in order history)"
    )
    user = f"""ACCESSORY THE SHOPPER IS BUYING
- Product: {product.title} ({product.category})
- Fits device model: {target_model}

DEVICES THE SHOPPER ALREADY OWNS
{owned_lines}

Is this accessory compatible with what they own?"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def compat_schema() -> dict:
    """Strict JSON schema for constrained decoding of the compatibility verdict."""
    return {
        "name": "compatibility_check",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "compatible": {"type": "boolean"},
                "warning": {"type": "string"},
            },
            "required": ["compatible", "warning"],
        },
    }
