"""Feature extraction shared by the rules engine and the ML model."""

from __future__ import annotations

from typing import TypedDict

from app.engine.state import CardWindowState
from app.schemas import CardholderProfile, TransactionIn
from app.simulator.catalog import haversine_km

FEATURE_NAMES: tuple[str, ...] = (
    "amount",
    "hour_of_day",
    "distance_from_home_km",
    "tx_count_last_10m",
    "amount_ratio_to_user_avg",
)


class FeatureVector(TypedDict):
    """Model input features (raw, human-readable units)."""

    amount: float
    hour_of_day: int
    distance_from_home_km: float
    tx_count_last_10m: int
    amount_ratio_to_user_avg: float


def build_features(
    *,
    amount: float,
    local_hour: int,
    lat: float,
    lon: float,
    profile: CardholderProfile,
    prior_count_10m: int,
) -> FeatureVector:
    """Compute the five model features from primitive inputs."""
    return FeatureVector(
        amount=round(amount, 2),
        hour_of_day=local_hour,
        distance_from_home_km=round(haversine_km(lat, lon, profile.home_lat, profile.home_lon), 1),
        tx_count_last_10m=prior_count_10m,
        amount_ratio_to_user_avg=round(amount / max(profile.avg_amount, 1.0), 3),
    )


def features_for(tx: TransactionIn, profile: CardholderProfile, window: CardWindowState) -> FeatureVector:
    """Compute features for a live transaction."""
    return build_features(
        amount=tx.amount,
        local_hour=tx.local_hour,
        lat=tx.lat,
        lon=tx.lon,
        profile=profile,
        prior_count_10m=window.prior_count_10m,
    )


def default_profile(tx: TransactionIn) -> CardholderProfile:
    """Fallback baseline for cards missing from the customer master."""
    return CardholderProfile(
        card_id=tx.card_id,
        name="Unknown Cardholder",
        tier="standard",
        home_city=tx.city,
        home_country=tx.country,
        home_lat=tx.lat,
        home_lon=tx.lon,
        avg_amount=100.0,
        categories=[],
    )
