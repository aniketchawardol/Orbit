"""AWS Bedrock VLM stub (future work).

Bedrock does not speak the OpenAI Chat Completions protocol natively, so a real
implementation would adapt `prompts.build_vlm_messages` output to the Bedrock
Converse API. Left as a stub until needed.
"""

from . import base


class BedrockVLM(base.VLMProvider):
    name = "bedrock"

    def grade(self, req: base.VLMRequest) -> dict:
        raise NotImplementedError("Bedrock provider is not implemented yet.")
