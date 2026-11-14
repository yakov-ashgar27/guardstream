"""Pydantic v2 schemas for transactions, scores, API bodies and WS payloads."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Decision(StrEnum):
    """Engine decision for a transaction."""

    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class ReviewStatus(StrEnum):
    """Analyst workflow status for REVIEW transactions."""

    PENDING = "PENDING"
    CONFIRMED_LEGIT = "CONFIRMED_LEGIT"
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"


class CardholderProfile(BaseModel):
    """Baseline behaviour of a cardholder (the 'customer master' record)."""

    card_id: str
    name: str
    tier: Literal["standard", "premium"]
    home_city: str
    home_country: str
    home_lat: float
    home_lon: float
    avg_amount: float
    categories: list[str]


class TransactionIn(BaseModel):
    """Raw authorization request as published onto the Redis Stream."""

    id: str
    card_id: str
    amount: float = Field(gt=0)
    currency: str = "USD"
    merchant: str
    merchant_category: str
    city: str
    country: str = Field(min_length=2, max_length=2)
    lat: float
    lon: float
    local_hour: int = Field(ge=0, le=23, description="Merchant-local transaction hour (ISO 8583 DE 12)")
    timestamp: datetime
    # Ground truth from the simulator, stored for evaluation only.
    sim_pattern: str | None = None


class RuleHit(BaseModel):
    """A single deterministic rule that fired."""

    code: str
    points: int
    reason: str


class MLResult(BaseModel):
    """Output of the anomaly model."""

    raw_score: float  # IsolationForest anomaly score (higher = more anomalous)
    normalized: float  # 0-1
    risk: float  # 0-100


class RiskAssessment(BaseModel):
    """Final hybrid evaluation."""

    rule_score: int
    ml_score: float
    risk_score: int
    decision: Decision
    triggered_rules: list[str]
    triggered_reasons: list[str]


class TransactionOut(BaseModel):
    """Processed transaction returned by the API and pushed over WebSocket."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    card_id: str
    cardholder_name: str
    card_tier: str
    amount: float
    currency: str
    merchant: str
    merchant_category: str
    city: str
    country: str
    lat: float
    lon: float
    local_hour: int
    timestamp: datetime
    rule_score: int
    ml_score: float
    risk_score: int
    decision: Decision
    triggered_rules: list[str]
    triggered_reasons: list[str]
    features: dict[str, Any]
    user_baseline: dict[str, Any]
    processing_ms: float
    review_status: ReviewStatus | None
    final_decision: Decision
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    sim_pattern: str | None = None


class ReviewRequest(BaseModel):
    """Analyst verdict on a REVIEW transaction."""

    action: Literal["APPROVE", "BLOCK"]
    analyst: str = Field(default="soc-analyst", max_length=80)
    notes: str | None = Field(default=None, max_length=2_000)


class SimulatorState(BaseModel):
    """Current simulator configuration."""

    running: bool
    tps: float
    fraud_rate: float
    max_tps: float
    generated: int
    fraud_injected: int


class SimulatorUpdate(BaseModel):
    """Partial update of simulator settings."""

    running: bool | None = None
    tps: float | None = Field(default=None, gt=0)
    fraud_rate: float | None = Field(default=None, ge=0, le=1)


class BurstRequest(BaseModel):
    """Fraud burst size."""

    size: int = Field(default=8, ge=1, le=50)


class Stats(BaseModel):
    """Live KPI snapshot."""

    tps: float
    total_processed: int
    total_blocked: int
    total_review: int
    pending_reviews: int
    blocked_amount: float
    flagged_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    detection_rate: float | None  # share of simulated fraud that was flagged
    false_positive_rate: float | None  # share of normal traffic flagged


class WSMessage(BaseModel):
    """Envelope for every WebSocket message."""

    type: Literal["transaction", "stats", "review_update", "simulator", "snapshot"]
    data: Any
