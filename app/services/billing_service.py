from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.core.config import settings

MONEY_Q = Decimal("0.0001")

MODEL_PRICING_PER_MILLION: dict[str, dict[str, Decimal]] = {
    # https://ai.google.dev/gemini-api/docs/pricing
    "gemini-2.5-flash": {"input": Decimal("0.30"), "output": Decimal("2.50")},
    "gemini-2.5-pro": {"input": Decimal("1.25"), "output": Decimal("10.00")},
}


@dataclass(frozen=True)
class PlanLimits:
    max_documents: Optional[int]
    allowed_models: Optional[set[str]]
    max_bots: Optional[int]
    max_messages: Optional[int]


PLAN_LIMITS: dict[str, PlanLimits] = {
    "trial": PlanLimits(
        max_documents=3,
        allowed_models={"gemini-2.5-flash"},
        max_bots=1,
        max_messages=100,
    ),
    "lite": PlanLimits(
        max_documents=10,
        allowed_models={"gemini-2.5-flash", "gemini-2.5-pro"},
        max_bots=3,
        max_messages=None,
    ),
    "full": PlanLimits(
        max_documents=None,
        allowed_models=None,
        max_bots=None,
        max_messages=None,
    ),
}


def normalize_model_name(model: Optional[str]) -> str:
    if not model:
        return "gemini-2.5-flash"
    value = model.strip().lower()
    if value.startswith("models/"):
        value = value.split("/", 1)[1]
    return value


def get_plan_limits(plan: str) -> PlanLimits:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["trial"])


def calculate_llm_cost_usd(
    *,
    model_name: Optional[str],
    input_tokens: int,
    output_tokens: int,
) -> Decimal:
    normalized = normalize_model_name(model_name)
    pricing = MODEL_PRICING_PER_MILLION.get(normalized)
    if not pricing:
        return Decimal("0.0000")
    input_cost = (Decimal(input_tokens) / Decimal(1_000_000)) * pricing["input"]
    output_cost = (Decimal(output_tokens) / Decimal(1_000_000)) * pricing["output"]
    return (input_cost + output_cost).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def is_workspace_subscription_active(billing: dict) -> bool:
    plan = billing.get("plan", "trial")
    status = (billing.get("subscription_status") or "").lower()
    if plan == "trial":
        trial_ends = billing.get("trial_ends_at")
        if not trial_ends:
            return True
        if trial_ends.tzinfo is None:
            trial_ends = trial_ends.replace(tzinfo=timezone.utc)
        return trial_ends > datetime.now(timezone.utc)
    return status in {"active", "trialing"}


def trial_end_datetime() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=settings.TRIAL_DAYS)
