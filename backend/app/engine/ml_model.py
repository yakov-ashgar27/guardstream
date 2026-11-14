"""Isolation Forest anomaly detector, trained on a synthetic normal baseline at startup."""

from __future__ import annotations

import logging
import random
import time

import numpy as np
from sklearn.ensemble import IsolationForest

from app.config import settings
from app.engine.features import FEATURE_NAMES, FeatureVector, build_features
from app.schemas import MLResult
from app.simulator.catalog import generate_profiles, sample_normal_purchase, sample_prior_tx_count

logger = logging.getLogger(__name__)


def _transform(rows: np.ndarray) -> np.ndarray:
    """Log-scale skewed features so random splits are spread sensibly.

    Column order follows ``FEATURE_NAMES``.
    """
    out = rows.astype(np.float64, copy=True)
    out[:, 0] = np.log1p(out[:, 0])  # amount
    out[:, 2] = np.log1p(out[:, 2])  # distance_from_home_km
    out[:, 4] = np.log(np.clip(out[:, 4], 1e-3, None))  # amount ratio (symmetric around 1)
    return out


def _to_row(f: FeatureVector) -> list[float]:
    return [float(f[name]) for name in FEATURE_NAMES]  # type: ignore[literal-required]


def generate_baseline(n: int, seed: int) -> np.ndarray:
    """Draw ``n`` normal transactions from the shared behavioural model."""
    rng = random.Random(seed)
    profiles = generate_profiles(300, rng)
    rows: list[list[float]] = []
    for _ in range(n):
        p = rng.choice(profiles)
        d = sample_normal_purchase(p, rng)
        rows.append(
            _to_row(
                build_features(
                    amount=d.amount,
                    local_hour=d.local_hour,
                    lat=d.lat,
                    lon=d.lon,
                    profile=p,
                    prior_count_10m=sample_prior_tx_count(rng),
                )
            )
        )
    return np.asarray(rows, dtype=np.float64)


class AnomalyDetector:
    """Wraps an IsolationForest and maps its output to a 0-100 risk score.

    Two signals are computed and the larger one wins:

    1. **Isolation score.** ``s = -score_samples(x)`` (≈0.4 for typical points,
       higher for isolated ones) is mapped piecewise-linearly using percentiles
       of the training data: median normal → 0, p95 → 15, p99.5 → 35,
       p99.5 + 0.08 → 100.
    2. **Out-of-envelope guard.** Isolation Forests cannot extrapolate: a point
       far *outside* the training range follows the same splits as the boundary
       points and gets a deceptively ordinary score (e.g. a transaction 3,500 km
       from home when the baseline never exceeds 300 km). For each feature we
       measure how far the value lies beyond the training 0.5–99.5 percentile
       envelope, in IQR units, and convert it with ``100·(1 − e^(−excess/τ))``.
    """

    ENVELOPE_TAU = 0.6

    def __init__(self) -> None:
        self.model: IsolationForest | None = None
        self._anchors_x: np.ndarray | None = None
        self._anchors_y = np.array([0.0, 15.0, 35.0, 100.0])
        self._lo: np.ndarray | None = None
        self._hi: np.ndarray | None = None
        self._iqr: np.ndarray | None = None

    @property
    def ready(self) -> bool:
        """Whether the model has been trained."""
        return self.model is not None

    def train(self, n_samples: int = settings.ml_training_samples, seed: int = settings.ml_random_state) -> None:
        """Fit the forest on a synthetic baseline and compute calibration anchors."""
        t0 = time.perf_counter()
        x = _transform(generate_baseline(n_samples, seed))
        self.model = IsolationForest(
            n_estimators=settings.ml_n_estimators,
            contamination="auto",
            random_state=seed,
            n_jobs=1,
        ).fit(x)
        s = -self.model.score_samples(x)
        p50, p95, p995 = np.percentile(s, [50, 95, 99.5])
        self._anchors_x = np.array([p50, p95, p995, p995 + 0.08])
        self._lo, self._hi = np.percentile(x, [0.5, 99.5], axis=0)
        q25, q75 = np.percentile(x, [25, 75], axis=0)
        self._iqr = np.maximum(q75 - q25, 0.25)
        self._lo[1], self._hi[1] = 0.0, 23.0  # every hour is a valid hour; let the forest judge it
        logger.info(
            "IsolationForest trained on %d samples in %.0f ms (anchors=%s)",
            n_samples,
            (time.perf_counter() - t0) * 1000,
            np.round(self._anchors_x, 3).tolist(),
        )

    def score(self, features: FeatureVector) -> MLResult:
        """Score one transaction."""
        if self.model is None or self._anchors_x is None or self._iqr is None:
            raise RuntimeError("AnomalyDetector.train() must be called first")
        x = _transform(np.asarray([_to_row(features)]))
        raw = float(-self.model.score_samples(x)[0])
        iso_risk = float(np.interp(raw, self._anchors_x, self._anchors_y))
        excess = np.maximum(np.maximum(x[0] - self._hi, self._lo - x[0]), 0.0) / self._iqr
        env_risk = float(100.0 * (1.0 - np.exp(-excess.max() / self.ENVELOPE_TAU)))
        risk = max(iso_risk, env_risk)
        return MLResult(raw_score=round(raw, 4), normalized=round(risk / 100, 3), risk=round(risk, 1))


detector = AnomalyDetector()
