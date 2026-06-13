"""VLM provider backed by any OpenAI-compatible endpoint.

One client serves Gemini (Google's OpenAI-compatibility endpoint), OpenAI, and
self-hosted Modal/vLLM — the difference is only base_url + api_key + model, which
the registry pulls from settings.LLM_PROVIDERS. Images are sent as standard
`image_url` base64 data URIs and we request a JSON object response.

The caller is responsible for falling back to the mock on failure (see
orchestrator.run_vlm); we keep this provider thin.
"""

import json
import logging

from openai import OpenAI

from . import base
from .. import prompts

log = logging.getLogger(__name__)


class OpenAICompatVLM(base.VLMProvider):
    def __init__(self, name, base_url, api_key, model, timeout=30.0):
        self.name = name
        self.model = model
        self._client = OpenAI(
            base_url=base_url or None,
            api_key=api_key or "missing",
            timeout=timeout,
            max_retries=1,
        )

    def grade(self, req: base.VLMRequest) -> dict:
        messages = prompts.build_vlm_messages(req)
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = (resp.choices[0].message.content or "").strip()
        data = _loads(content)
        data["source"] = self.name
        return prompts.normalize_vlm_output(data, n_uploaded=len(req.uploaded or []))


def _loads(content: str) -> dict:
    """Parse model JSON; tolerate ```json fenced blocks some models still emit."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    if "```" in content:
        inner = content.split("```", 2)
        if len(inner) >= 2:
            body = inner[1]
            if body.startswith("json"):
                body = body[4:]
            try:
                return json.loads(body.strip())
            except json.JSONDecodeError:
                pass
    # Last resort: grab the outermost {...}.
    start, end = content.find("{"), content.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("VLM did not return valid JSON")
