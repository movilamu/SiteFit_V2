"""Groq integration for the requirement builder and the explanation writer.

Two capabilities live here, and both are strictly bounded:

* :func:`parse_requirements` turns a natural-language brief into a
  **draft** of structured requirements.  The draft is validated against a
  fixed schema, shown to the user as "AI interpreted your requirements as:",
  and only applied after the user confirms it.  Groq never writes to the
  database and never changes a score, a weight or a cost.

* :func:`write_explanation` turns **deterministic results** into a short
  paragraph.  It receives the facts and may only restate them.  The facts
  are also returned so that the interface can show the underlying numbers
  next to the sentence.

Every failure mode -- a missing key, a timeout, a rate limit, malformed
JSON, a provider error -- is reported as a typed error so the caller can
fall back to the manual workflow rather than failing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AIServiceError(RuntimeError):
    """Base class for the AI service's failure modes."""

    code = "ai_unavailable"


class AINotConfiguredError(AIServiceError):
    """The provider is not configured."""

    code = "not_configured"


class AITimeoutError(AIServiceError):
    """The provider did not answer in time."""

    code = "timeout"


class AIRateLimitError(AIServiceError):
    """The provider's rate limit was reached."""

    code = "rate_limited"


class AIProviderError(AIServiceError):
    """The provider returned an error."""

    code = "provider_error"


class AIInvalidResponseError(AIServiceError):
    """The provider's answer did not satisfy the schema."""

    code = "invalid_response"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ParsedRequirement(BaseModel):
    """One requirement extracted from the brief."""

    key: str
    importance: str = "preferred"
    value: Any = None
    source_quote: str = ""

    @field_validator("importance")
    @classmethod
    def _validate_importance(cls, value: str) -> str:
        normalised = str(value).strip().lower()
        if normalised not in {"required", "preferred", "not_important"}:
            return "preferred"
        return normalised


class ParsedBrief(BaseModel):
    """The structured draft produced from a natural-language brief."""

    interpretation_summary: str = ""
    business_type: Optional[str] = None
    acquisition_mode: str = "either"
    requirements: list[ParsedRequirement] = Field(default_factory=list)
    parking: dict[str, Any] = Field(default_factory=dict)
    facilities: list[dict[str, Any]] = Field(default_factory=list)
    financial: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("acquisition_mode")
    @classmethod
    def _validate_acquisition(cls, value: str) -> str:
        normalised = str(value).strip().lower()
        return normalised if normalised in {"buy", "lease", "either"} else "either"


# ---------------------------------------------------------------------------
# The Groq client
# ---------------------------------------------------------------------------

@dataclass
class GroqResponse:
    """The raw answer from Groq."""

    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)


def _post_chat(
    messages: list[dict[str, str]],
    model: str,
    json_mode: bool = True,
) -> GroqResponse:
    """Send a chat completion request to Groq and return the answer."""

    settings = get_settings()
    if not settings.groq_api_key:
        raise AINotConfiguredError(
            "The AI requirement builder is not available because no "
            "language-model provider is configured. Set GROQ_API_KEY, or "
            "complete the requirement form manually."
        )

    try:
        import httpx
    except ImportError:  # pragma: no cover - optional dependency
        raise AIProviderError(
            "httpx is not installed on the server, so the AI service is unavailable."
        )

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 2000,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = httpx.post(
            f"{settings.groq_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.groq_timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise AITimeoutError(
            "The language-model provider did not answer in time. Please try again."
        ) from exc
    except Exception as exc:
        raise AIProviderError(
            f"The language-model provider could not be reached: {exc}"
        ) from exc

    if response.status_code == 429:
        raise AIRateLimitError(
            "The language-model provider is rate limiting this client. Please "
            "try again shortly."
        )
    if response.status_code == 401:
        raise AIProviderError(
            "The language-model provider rejected the configured API key."
        )
    if response.status_code >= 400:
        raise AIProviderError(
            f"The language-model provider returned HTTP {response.status_code}."
        )

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIInvalidResponseError(
            f"The language-model provider returned an unusable response: {exc}"
        ) from exc

    return GroqResponse(
        content=str(content),
        model=str(body.get("model") or model),
        usage=body.get("usage") or {},
    )


def _parse_json(content: str) -> dict[str, Any]:
    """Parse a JSON answer, tolerating a fenced code block."""

    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.lower().startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIInvalidResponseError(
            f"The language-model provider returned a response that could not "
            f"be parsed: {exc}"
        ) from exc
    if not isinstance(decoded, dict):
        raise AIInvalidResponseError(
            "The language-model provider returned a response that was not a JSON object."
        )
    return decoded


# ---------------------------------------------------------------------------
# Requirement parsing
# ---------------------------------------------------------------------------

PARSE_SYSTEM_PROMPT = """You convert a business owner's natural-language description of a
retail site into structured site-selection requirements.

Rules:
- Return ONLY a JSON object. No prose, no markdown fences.
- Never invent facts about specific properties, prices or rents.
- Only extract what the user actually stated. If a value is not stated, omit it.
- Map extracted values onto the supplied catalogue keys only.
- Mark every requirement's importance as one of: required, preferred, not_important.
- Where the user is ambiguous, choose the reading that best matches the stated
  business type and note the ambiguity in "warnings".
- If the user asks for a business type that is not in the catalogue, set
  "business_type" to null and say so in "warnings".

Output shape:
{
  "interpretation_summary": "one sentence restating what you understood",
  "business_type": "<catalogue business type key or null>",
  "acquisition_mode": "buy" | "lease" | "either",
  "requirements": [
    {"key": "<catalogue requirement key>", "importance": "required|preferred|not_important",
     "value": <number|boolean|string>, "source_quote": "<the words that imply this>"}
  ],
  "parking": {"min_car_spaces": <int>, "min_two_wheeler_spaces": <int>,
              "min_parking_area_sqft": <int>, "behaviour": "hard|preference|flexible"},
  "facilities": [{"key": "<catalogue facility key>", "importance": "required|preferred"}],
  "financial": {"purchase_budget": <number>, "monthly_rent_budget": <number>,
                "renovation_budget": <number>, "brokerage_budget": <number>,
                "initial_investment_budget": <number>, "monthly_operating_budget": <number>},
  "warnings": ["..."]
}"""


def _build_parse_prompt(description: str, business_type: Optional[str]) -> str:
    from app.domain.catalog import (
        business_type_catalog,
        facility_catalog,
        requirement_catalog,
    )

    catalogue = {
        "business_types": business_type_catalog(),
        "requirements": requirement_catalog(),
        "facilities": facility_catalog(),
    }
    return (
        f"Business type hint: {business_type or 'not specified'}\n\n"
        f"Catalogue:\n{json.dumps(catalogue, indent=2)}\n\n"
        f"User description:\n{description}\n"
    )


def parse_requirements(
    description: str,
    business_type: Optional[str] = None,
) -> tuple[ParsedBrief, GroqResponse]:
    """Interpret a natural-language brief into a validated draft.

    Returns:
        The validated draft and the raw provider response, for logging and
        for the "how this was interpreted" audit.

    Raises:
        AIServiceError: for any provider or validation failure.
    """

    settings = get_settings()
    response = _post_chat(
        [
            {"role": "system", "content": PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": _build_parse_prompt(description, business_type)},
        ],
        model=settings.groq_model,
        json_mode=True,
    )

    decoded = _parse_json(response.content)
    try:
        brief = ParsedBrief.model_validate(decoded)
    except ValidationError as exc:
        raise AIInvalidResponseError(
            f"The language-model provider returned a response that does not "
            f"match the expected structure: {exc}"
        ) from exc

    return brief, response


# ---------------------------------------------------------------------------
# Explanation writing
# ---------------------------------------------------------------------------

EXPLANATION_SYSTEM_PROMPT = """You write one short paragraph explaining why a site ranks where
it does, for a business decision maker.

Rules:
- Use ONLY the facts given to you. Do not add, infer or embellish any fact.
- Do not mention the word "score" in a way that suggests certainty. A score
  expresses relative fit against stated criteria, not a prediction of success.
- Keep it to two or three sentences. Plain language, no jargon.
- If the facts include caveats or limitations, reflect them.
- Return ONLY a JSON object: {"paragraph": "..."}"""


def write_explanation(
    facts: dict[str, Any],
    fallback: str,
) -> tuple[str, Optional[GroqResponse]]:
    """Turn deterministic facts into a paragraph.

    Args:
        facts: The deterministic results.  These are the only facts the
            model may use.
        fallback: The deterministic narrative, returned when the provider is
            unavailable so the interface always has an explanation.

    Returns:
        The paragraph and the provider response, or ``(fallback, None)`` when
        the provider could not be used.
    """

    settings = get_settings()
    if not settings.groq_api_key:
        return fallback, None

    try:
        response = _post_chat(
            [
                {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Write the explanation for this site using only these facts:\n"
                        + json.dumps(facts, indent=2, default=str)
                    ),
                },
            ],
            model=settings.groq_explanation_model,
            json_mode=True,
        )
        decoded = _parse_json(response.content)
        paragraph = str(decoded.get("paragraph") or "").strip()
        if not paragraph:
            return fallback, None
        return paragraph, response
    except AIServiceError as exc:
        logger.info("Falling back to the deterministic explanation: %s", exc)
        return fallback, None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("The explanation writer failed unexpectedly: %s", exc)
        return fallback, None


__all__ = [
    "AIInvalidResponseError",
    "AINotConfiguredError",
    "AIProviderError",
    "AIRateLimitError",
    "AIServiceError",
    "AITimeoutError",
    "GroqResponse",
    "ParsedBrief",
    "ParsedRequirement",
    "parse_requirements",
    "write_explanation",
]

