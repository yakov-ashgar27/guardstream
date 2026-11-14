"""Hybrid risk aggregator: rule points + weighted ML score -> 0-100 + decision."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.config import settings
from app.engine.features import FeatureVector, features_for
from app.engine.ml_model import AnomalyDetector
from app.engine.rules import evaluate_rules
from app.engine.state import CardWindowState
from app.schemas import CardholderProfile, Decision, MLResult, RiskAssessment, RuleHit, TransactionIn


def decide(score: int) -> Decision:
    """Map a 0-100 risk score to a decision band."""
    if score >= settings.block_threshold:
        return Decision.BLOCK
    if score >= settings.review_threshold:
        return Decision.REVIEW
    return Decision.APPROVE


def explain_ml(features: FeatureVector, ml: MLResult) -> str:
    """Human-readable ML reason with the most unusual feature values."""
    drivers: list[str] = []
    ratio = features["amount_ratio_to_user_avg"]
    if ratio >= 4:
        drivers.append(f"amount {ratio:.1f}x user avg")
    elif ratio <= 0.08:
        drivers.append(f"micro amount {ratio:.2f}x avg")
    if features["distance_from_home_km"] >= 500:
        drivers.append(f"{features['distance_from_home_km']:,.0f} km from home")
    if features["hour_of_day"] <= 5:
        drivers.append(f"{features['hour_of_day']:02d}:00 local")
    if features["tx_count_last_10m"] >= 6:
        drivers.append(f"{features['tx_count_last_10m']} tx in 10m")
    suffix = f" ({', '.join(drivers)})" if drivers else ""
    return f"ML Anomaly Score: {ml.normalized:.2f}{suffix}"


def combine(rule_hits: list[RuleHit], ml: MLResult, features: FeatureVector) -> RiskAssessment:
    """Combine rule points with the weighted ML risk, capped at 100."""
    rule_points = sum(h.points for h in rule_hits)
    ml_points = ml.risk * settings.ml_weight
    score = int(min(100, round(rule_points + ml_points)))
    reasons = [h.reason for h in rule_hits]
    if ml.normalized >= 0.25 or rule_hits:
        reasons.append(explain_ml(features, ml))
    return RiskAssessment(
        rule_score=rule_points,
        ml_score=ml.risk,
        risk_score=score,
        decision=decide(score),
        triggered_rules=[h.code for h in rule_hits],
        triggered_reasons=reasons,
    )


@dataclass(slots=True)
class Evaluation:
    """Full engine output for one transaction."""

    assessment: RiskAssessment
    features: FeatureVector
    ml: MLResult
    processing_ms: float


def evaluate(
    tx: TransactionIn,
    profile: CardholderProfile,
    window: CardWindowState,
    detector: AnomalyDetector,
    started: float | None = None,
) -> Evaluation:
    """Run rules + ML + aggregation. Pure CPU; window state is fetched by the caller.

    Args:
        started: ``time.perf_counter()`` value at which processing began (so that
            the Redis window round-trip is included in the latency figure).
    """
    t0 = started if started is not None else time.perf_counter()
    feats = features_for(tx, profile, window)
    hits = evaluate_rules(tx, profile, window)
    ml = detector.score(feats)
    assessment = combine(hits, ml, feats)
    return Evaluation(
        assessment=assessment,
        features=feats,
        ml=ml,
        processing_ms=round((time.perf_counter() - t0) * 1000, 2),
    )
