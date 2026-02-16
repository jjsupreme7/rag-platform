"""Complexity-based model routing for Claude chat models."""

import logging
import anthropic
from config import settings

logger = logging.getLogger(__name__)

# Model IDs mapped to complexity tiers
MODEL_MAP = {
    "simple": settings.CLAUDE_SIMPLE_MODEL,
    "moderate": settings.CLAUDE_MODERATE_MODEL,
    "complex": settings.CLAUDE_COMPLEX_MODEL,
}

# Anthropic client singleton
_anthropic: anthropic.Anthropic | None = None


def get_anthropic() -> anthropic.Anthropic:
    """Return singleton Anthropic client."""
    global _anthropic
    if _anthropic is None:
        _anthropic = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic


def classify_complexity(question: str, history_len: int = 0) -> str:
    """Classify question complexity using Claude Haiku.

    Returns: "simple", "moderate", or "complex"
    """
    prompt = (
        "Classify this Washington State tax law question's complexity.\n\n"
        "simple = factual lookup, single concept, yes/no, rate/threshold question\n"
        "moderate = multi-part, comparisons, exemption applicability, scenario with a few factors\n"
        "complex = novel legal analysis, multiple conflicting statutes, ambiguous facts, "
        "cross-referencing across tax types or jurisdictions\n\n"
        f"Conversation has {history_len} prior messages. "
        "Longer conversations with accumulated context should lean toward higher complexity.\n\n"
        f"Question: {question}\n\n"
        "Respond with exactly one word: simple, moderate, or complex"
    )

    try:
        client = get_anthropic()
        resp = client.messages.create(
            model=settings.CLAUDE_SIMPLE_MODEL,
            max_tokens=10,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp.content[0].text.strip().lower()
        if answer in MODEL_MAP:
            return answer
        # Fuzzy match
        for key in MODEL_MAP:
            if key in answer:
                return key
        logger.warning(f"Unexpected classification: {answer}, defaulting to moderate")
        return "moderate"
    except Exception as e:
        logger.warning(f"Classification failed: {e}, defaulting to moderate")
        return "moderate"


def route_model(question: str, history_len: int = 0) -> tuple[str, str]:
    """Classify and route to the appropriate Claude model.

    Returns: (model_id, complexity_level)
    """
    complexity = classify_complexity(question, history_len)
    model_id = MODEL_MAP[complexity]
    logger.info(f"Model routing: complexity={complexity}, model={model_id}")
    return model_id, complexity
