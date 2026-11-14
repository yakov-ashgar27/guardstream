"""Redis Stream consumer: evaluate -> persist -> broadcast."""

from __future__ import annotations

import asyncio
import logging
import time

from app.database import SessionLocal
from app.engine.features import default_profile
from app.engine.ml_model import AnomalyDetector
from app.engine.scorer import evaluate
from app.models import Transaction
from app.realtime import ConnectionManager, Metrics
from app.redis_client import RedisClient
from app.schemas import CardholderProfile, Decision, ReviewStatus, TransactionIn, TransactionOut, WSMessage

logger = logging.getLogger(__name__)


class StreamProcessor:
    """Consumes the ingestion stream through a consumer group."""

    def __init__(self, redis: RedisClient, detector: AnomalyDetector, ws: ConnectionManager, metrics: Metrics) -> None:
        self.redis = redis
        self.detector = detector
        self.ws = ws
        self.metrics = metrics
        self._profiles: dict[str, CardholderProfile] = {}
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Launch the consumer loop."""
        self._task = asyncio.create_task(self._run(), name="stream-processor")

    async def stop(self) -> None:
        """Cancel the consumer loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _profile(self, tx: TransactionIn) -> CardholderProfile:
        if (p := self._profiles.get(tx.card_id)) is None:
            p = await self.redis.get_profile(tx.card_id) or default_profile(tx)
            self._profiles[tx.card_id] = p
        return p

    async def _run(self) -> None:
        await self.redis.ensure_group()
        # Crash recovery: finish anything this consumer read but never acked.
        pending = await self.redis.read_batch(pending=True)
        if pending:
            logger.info("Re-processing %d pending messages", len(pending))
            await self._handle(pending)
        while True:
            try:
                batch = await self.redis.read_batch()
                if batch:
                    await self._handle(batch)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Stream processing error; retrying")
                await asyncio.sleep(1)

    async def _handle(self, batch: list[tuple[str, TransactionIn | None]]) -> None:
        rows: list[Transaction] = []
        for _msg_id, tx in batch:
            if tx is None:
                continue
            try:
                rows.append(await self.process(tx))
            except Exception:
                logger.exception("Failed to evaluate transaction %s", tx.id)

        if rows:
            async with SessionLocal() as session:
                for row in rows:
                    await session.merge(row)  # merge => idempotent on re-delivery
                await session.commit()

        await self.redis.ack(*(msg_id for msg_id, _ in batch))

        for row in rows:
            self.metrics.record(row)
            await self.ws.broadcast(
                WSMessage(type="transaction", data=TransactionOut.model_validate(row).model_dump(mode="json"))
            )

    async def process(self, tx: TransactionIn) -> Transaction:
        """Evaluate one transaction and build its ORM row (not yet persisted)."""
        t0 = time.perf_counter()
        profile = await self._profile(tx)
        window = await self.redis.record_and_get_window(tx)
        ev = evaluate(tx, profile, window, self.detector, started=t0)
        a = ev.assessment
        if ev.processing_ms > 50:
            logger.warning("Slow evaluation: %.1f ms for %s", ev.processing_ms, tx.id)
        return Transaction(
            id=tx.id,
            card_id=tx.card_id,
            cardholder_name=profile.name,
            card_tier=profile.tier,
            amount=tx.amount,
            currency=tx.currency,
            merchant=tx.merchant,
            merchant_category=tx.merchant_category,
            city=tx.city,
            country=tx.country,
            lat=tx.lat,
            lon=tx.lon,
            local_hour=tx.local_hour,
            timestamp=tx.timestamp,
            rule_score=a.rule_score,
            ml_score=a.ml_score,
            risk_score=a.risk_score,
            decision=a.decision.value,
            triggered_rules=a.triggered_rules,
            triggered_reasons=a.triggered_reasons,
            features={**ev.features, "ml_raw_score": ev.ml.raw_score},
            user_baseline={
                "avg_amount": profile.avg_amount,
                "home_city": profile.home_city,
                "home_country": profile.home_country,
                "tier": profile.tier,
                "typical_categories": profile.categories,
                "prior_tx_last_60s": window.prior_count_velocity,
                "previous_location": f"{window.last_city}, {window.last_country}" if window.last_city else None,
            },
            processing_ms=ev.processing_ms,
            review_status=ReviewStatus.PENDING.value if a.decision == Decision.REVIEW else None,
            final_decision=a.decision.value,
            sim_pattern=tx.sim_pattern,
        )
