"""Unit tests for the detection engine (no Redis/PostgreSQL required).

Run with:  docker compose exec backend pytest -q
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest

from app.engine.ml_model import AnomalyDetector
from app.engine.rules import evaluate_rules
from app.engine.scorer import decide, evaluate
from app.engine.state import CardWindowState
from app.schemas import CardholderProfile, Decision, TransactionIn
from app.simulator.catalog import generate_profiles, sample_normal_purchase

NOW = datetime.now(UTC)
NOW_MS = int(NOW.timestamp() * 1000)

PROFILE = CardholderProfile(
    card_id="4580-****-****-0001",
    name="Noa Cohen",
    tier="standard",
    home_city="Tel Aviv",
    home_country="IL",
    home_lat=32.0853,
    home_lon=34.7818,
    avg_amount=80.0,
    categories=["grocery", "restaurant", "fuel"],
)


def make_tx(**kw: object) -> TransactionIn:
    base: dict[str, object] = {
        "id": "tx-1",
        "card_id": PROFILE.card_id,
        "amount": 75.0,
        "merchant": "GreenLeaf Market",
        "merchant_category": "grocery",
        "city": "Tel Aviv",
        "country": "IL",
        "lat": 32.08,
        "lon": 34.78,
        "local_hour": 14,
        "timestamp": NOW,
    }
    base.update(kw)
    return TransactionIn(**base)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def detector() -> AnomalyDetector:
    d = AnomalyDetector()
    d.train()
    return d


def test_decision_bands() -> None:
    assert decide(0) == decide(39) == Decision.APPROVE
    assert decide(40) == decide(74) == Decision.REVIEW
    assert decide(75) == decide(100) == Decision.BLOCK


def test_velocity_rule_fires_on_fourth_tx() -> None:
    assert evaluate_rules(make_tx(), PROFILE, CardWindowState(prior_count_velocity=2)) == []
    hits = evaluate_rules(make_tx(), PROFILE, CardWindowState(prior_count_velocity=3))
    assert [h.code for h in hits] == ["RULE_VELOCITY"]
    assert hits[0].points == 45


def test_geo_jump_rule() -> None:
    window = CardWindowState(
        last_country="IL", last_city="Tel Aviv", last_lat=32.08, last_lon=34.78, last_ts_ms=NOW_MS - 240_000
    )
    tx = make_tx(city="London", country="GB", lat=51.5, lon=-0.12)
    hits = evaluate_rules(tx, PROFILE, window)
    assert [h.code for h in hits] == ["RULE_GEO_JUMP"]
    assert hits[0].reason.startswith("Impossible Travel (IL -> UK in 4m")

    stale = CardWindowState(last_country="IL", last_ts_ms=NOW_MS - 31 * 60_000)
    assert evaluate_rules(tx, PROFILE, stale) == []


def test_high_amount_only_for_standard_tier() -> None:
    tx = make_tx(amount=3_500.0)
    assert [h.code for h in evaluate_rules(tx, PROFILE, CardWindowState())] == ["RULE_HIGH_AMOUNT"]
    premium = PROFILE.model_copy(update={"tier": "premium"})
    assert evaluate_rules(tx, premium, CardWindowState()) == []


def test_normal_traffic_mostly_approved(detector: AnomalyDetector) -> None:
    rng = random.Random(99)
    profiles = generate_profiles(200, rng)
    approved = 0
    for i in range(500):
        p = rng.choice(profiles)
        d = sample_normal_purchase(p, rng)
        tx = make_tx(id=f"n{i}", card_id=p.card_id, amount=d.amount, city=d.city, country=d.country,
                     lat=d.lat, lon=d.lon, local_hour=d.local_hour)
        ev = evaluate(tx, p, CardWindowState(), detector)
        approved += ev.assessment.decision == Decision.APPROVE
    assert approved / 500 >= 0.97


def test_impossible_travel_is_blocked(detector: AnomalyDetector) -> None:
    window = CardWindowState(
        prior_count_velocity=1, prior_count_10m=1, last_country="IL", last_city="Tel Aviv",
        last_lat=32.08, last_lon=34.78, last_ts_ms=NOW_MS - 30_000,
    )
    tx = make_tx(amount=240.0, city="New York", country="US", lat=40.71, lon=-74.0)
    ev = evaluate(tx, PROFILE, window, detector)
    assert ev.assessment.decision == Decision.BLOCK
    assert any(r.startswith("ML Anomaly Score") for r in ev.assessment.triggered_reasons)


def test_high_value_night_purchase_is_flagged(detector: AnomalyDetector) -> None:
    ev = evaluate(make_tx(amount=1_000.0, local_hour=3), PROFILE, CardWindowState(), detector)
    assert ev.assessment.decision in {Decision.REVIEW, Decision.BLOCK}


def test_latency_budget(detector: AnomalyDetector) -> None:
    ev = evaluate(make_tx(), PROFILE, CardWindowState(), detector)
    assert ev.processing_ms < 50
