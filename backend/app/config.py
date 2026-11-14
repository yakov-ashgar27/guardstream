"""Application configuration.

All values can be overridden with environment variables (case-insensitive),
e.g. ``DATABASE_URL``, ``REDIS_URL`` or ``RULE_GEO_JUMP_POINTS``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings and detection thresholds."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Infrastructure -------------------------------------------------
    database_url: str = "postgresql+asyncpg://guardstream:guardstream@localhost:5432/guardstream"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["*"]
    log_level: str = "INFO"

    # --- Redis Streams --------------------------------------------------
    stream_key: str = "gs:transactions:incoming"
    stream_group: str = "fraud-engine"
    stream_consumer: str = "engine-1"
    stream_maxlen: int = 20_000
    stream_read_count: int = 100
    stream_block_ms: int = 1_000

    # --- Sliding windows -----------------------------------------------
    velocity_window_s: int = 60
    feature_window_s: int = 600  # tx_count_last_10m
    geo_window_s: int = 1_800  # 30 minutes

    # --- Deterministic rules -------------------------------------------
    rule_velocity_max_tx: int = 3  # more than this many in the window triggers
    rule_velocity_points: int = 45
    rule_geo_jump_points: int = 60
    rule_high_amount_threshold: float = 3_000.0
    rule_high_amount_points: int = 35

    # --- ML -------------------------------------------------------------
    ml_training_samples: int = 2_000
    ml_n_estimators: int = 100
    ml_random_state: int = 42
    ml_weight: float = 0.6  # share of the 0-100 ML score added to rule points

    # --- Decision thresholds -------------------------------------------
    review_threshold: int = 40  # 40-74 -> REVIEW
    block_threshold: int = 75  # 75-100 -> BLOCK

    # --- Simulator ------------------------------------------------------
    sim_autostart: bool = True
    sim_cardholders: int = 1_000
    sim_default_tps: float = 4.0
    sim_max_tps: float = 15.0
    sim_default_fraud_rate: float = 0.10
    sim_normal_card_cooldown_s: float = 60.0
    sim_seed: int = 7

    # --- Metrics --------------------------------------------------------
    stats_broadcast_interval_s: float = 1.0


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()


settings = get_settings()
