from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import GeminiSettings

logger = logging.getLogger(__name__)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, errors.ServerError):
        return True
    # 429 RESOURCE_EXHAUSTED comes back as ClientError
    if isinstance(exc, errors.ClientError):
        return "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
    return False


class GeminiClient:
    def __init__(self, settings: GeminiSettings) -> None:
        self._client = genai.Client(api_key=settings.api_key.get_secret_value())
        self._model = settings.chat_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_transient),
        reraise=True,
    )
    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        contents = _to_contents(messages)

        # Disable Automatic Function Calling — it can silently consume responses
        # when multiple genai.Client instances run concurrently in asyncio.gather.
        no_afc = types.AutomaticFunctionCallingConfig(disable=True)

        # Disable thinking — this client is used for grounded RAG synthesis where
        # the context is provided explicitly. Thinking tokens consume from the
        # max_output_tokens budget; leaving thinking enabled causes the model to
        # spend ~3700 tokens on internal reasoning and truncate the JSON output.
        no_think = types.ThinkingConfig(thinking_budget=0)

        if response_schema is not None:
            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
                response_schema=response_schema,
                automatic_function_calling=no_afc,
                thinking_config=no_think,
            )
        else:
            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                automatic_function_calling=no_afc,
                thinking_config=no_think,
            )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )

        # Type guard: Ensure candidate and content are fully present
        if not response.candidates or response.candidates[0].content is None:
            raise ValueError("Gemini returned an empty response (no candidates or content)")

        content = response.candidates[0].content
        if not content.parts:
            raise ValueError("Gemini returned an empty response (no parts present)")

        # Gather text content while safely ignoring thinking/thought process blocks
        text_parts = []
        for p in content.parts:
            if getattr(p, "text", None) and not getattr(p, "thought", False):
                text_parts.append(p.text)

        text = "".join(text_parts).strip()

        if not text:
            raise ValueError("Gemini returned an empty response")

        if response_schema is not None:
            return json.loads(text)
        return {"content": text}


def _to_contents(messages: list[dict[str, Any]]) -> list[types.Content]:
    _role = {"assistant": "model"}
    return [
        types.Content(
            role=_role.get(msg["role"], msg["role"]),
            parts=[types.Part.from_text(text=msg["content"])],
        )
        for msg in messages
    ]