"""Cost estimation from explicitly configured provider pricing.

Requirements are deliberately strict:

* no price is invented, defaulted to a vendor's public list, or inferred;
* a cost is only produced when both token counts came from the provider and a
  matching price entry exists in ``EXECUTION_PRICING``;
* the result always states whether it is an estimate or why it is unavailable.

``EXECUTION_PRICING`` is a JSON object keyed by ``"<provider kind>:<model id>"``::

    {
      "zai:glm-5.3": {
        "input_per_million": "0.60",
        "output_per_million": "2.20",
        "currency": "USD"
      }
    }

Local models have no reliable hosted price, so they normally stay unconfigured
and therefore unavailable rather than free.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json

from django.conf import settings

_COST_PLACES = Decimal("0.000001")


@dataclass(frozen=True)
class CostEstimate:
    amount: Decimal | None
    currency: str
    status: str  # "estimated" | "unavailable"
    detail: str


def _pricing_config() -> dict:
    raw = getattr(settings, "EXECUTION_PRICING", "") or {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _price_for(kind: str, model_id: str) -> dict | None:
    config = _pricing_config()
    entry = config.get(f"{kind}:{model_id}")
    if isinstance(entry, dict):
        return entry
    # Allow a provider-level default while still requiring an explicit entry.
    entry = config.get(kind)
    return entry if isinstance(entry, dict) else None


def _decimal(value) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def estimate_cost(
    *, provider_kind: str, model_id: str, input_tokens, output_tokens
) -> CostEstimate:
    """Return an estimate only when pricing and both token counts are known."""
    if input_tokens is None or output_tokens is None:
        return CostEstimate(
            None,
            "",
            "unavailable",
            "Token usage was not reported by the provider.",
        )

    price = _price_for(provider_kind, model_id)
    if price is None:
        return CostEstimate(
            None,
            "",
            "unavailable",
            f"No pricing is configured for {provider_kind}:{model_id}.",
        )

    input_price = _decimal(price.get("input_per_million"))
    output_price = _decimal(price.get("output_per_million"))
    currency = str(price.get("currency") or "").strip().upper()
    if input_price is None or output_price is None or not currency:
        return CostEstimate(
            None,
            "",
            "unavailable",
            f"Pricing for {provider_kind}:{model_id} is incomplete.",
        )

    amount = (
        Decimal(int(input_tokens)) / Decimal(1_000_000) * input_price
        + Decimal(int(output_tokens)) / Decimal(1_000_000) * output_price
    ).quantize(_COST_PLACES, rounding=ROUND_HALF_UP)
    return CostEstimate(
        amount,
        currency,
        "estimated",
        "Estimated from configured per-million token pricing and provider-reported usage.",
    )
