"""WebSocket fan-out and live KPI metrics."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque

from fastapi import WebSocket
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction
from app.schemas import Decision, ReviewStatus, Stats, WSMessage

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks dashboard WebSocket clients and broadcasts JSON messages."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    @property
    def count(self) -> int:
        """Number of connected clients."""
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a client."""
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """Forget a client."""
        self._clients.discard(ws)

    async def send(self, ws: WebSocket, msg: WSMessage) -> None:
        """Send one message to one client."""
        await ws.send_text(msg.model_dump_json())

    async def broadcast(self, msg: WSMessage) -> None:
        """Send to every client; drop clients that are slow or gone."""
        if not self._clients:
            return
        text = msg.model_dump_json()

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(ws.send_text(text), timeout=2)
                return None
            except Exception:
                return ws

        dead = [ws for ws in await asyncio.gather(*(_send(c) for c in list(self._clients))) if ws]
        for ws in dead:
            self.disconnect(ws)
            with contextlib.suppress(Exception):
                await ws.close()


class Metrics:
    """In-memory KPI counters, seeded from PostgreSQL on startup."""

    def __init__(self) -> None:
        self._events: deque[float] = deque(maxlen=10_000)
        self._latency: deque[float] = deque(maxlen=500)
        self.total_processed = 0
        self.total_blocked = 0
        self.total_review = 0
        self.pending_reviews = 0
        self.blocked_amount = 0.0
        self.fraud_total = 0
        self.fraud_flagged = 0
        self.normal_total = 0
        self.normal_flagged = 0

    async def load(self, session: AsyncSession) -> None:
        """Rebuild counters from persisted data."""
        flagged = Transaction.decision != Decision.APPROVE.value
        row = (
            await session.execute(
                select(
                    func.count(),
                    func.count().filter(Transaction.final_decision == Decision.BLOCK.value),
                    func.count().filter(Transaction.decision == Decision.REVIEW.value),
                    func.count().filter(Transaction.review_status == ReviewStatus.PENDING.value),
                    func.coalesce(
                        func.sum(case((Transaction.final_decision == Decision.BLOCK.value, Transaction.amount), else_=0)),
                        0,
                    ),
                    func.count().filter(Transaction.sim_pattern.is_not(None)),
                    func.count().filter(Transaction.sim_pattern.is_not(None), flagged),
                    func.count().filter(Transaction.sim_pattern.is_(None)),
                    func.count().filter(Transaction.sim_pattern.is_(None), flagged),
                )
            )
        ).one()
        (
            self.total_processed,
            self.total_blocked,
            self.total_review,
            self.pending_reviews,
            blocked_amount,
            self.fraud_total,
            self.fraud_flagged,
            self.normal_total,
            self.normal_flagged,
        ) = row
        self.blocked_amount = float(blocked_amount)

    def record(self, tx: Transaction) -> None:
        """Update counters for a freshly processed transaction."""
        self._events.append(time.monotonic())
        self._latency.append(tx.processing_ms)
        self.total_processed += 1
        flagged = tx.decision != Decision.APPROVE.value
        if tx.decision == Decision.BLOCK.value:
            self.total_blocked += 1
            self.blocked_amount += tx.amount
        elif tx.decision == Decision.REVIEW.value:
            self.total_review += 1
            self.pending_reviews += 1
        if tx.sim_pattern:
            self.fraud_total += 1
            self.fraud_flagged += flagged
        else:
            self.normal_total += 1
            self.normal_flagged += flagged

    def record_review(self, tx: Transaction) -> None:
        """Update counters after an analyst verdict."""
        self.pending_reviews = max(0, self.pending_reviews - 1)
        if tx.final_decision == Decision.BLOCK.value:
            self.total_blocked += 1
            self.blocked_amount += tx.amount

    def snapshot(self) -> Stats:
        """Current KPI values."""
        now = time.monotonic()
        window = 5.0
        recent = sum(1 for t in reversed(self._events) if now - t <= window) if self._events else 0
        lat = sorted(self._latency)
        flagged = self.total_blocked + self.total_review
        return Stats(
            tps=round(recent / window, 2),
            total_processed=self.total_processed,
            total_blocked=self.total_blocked,
            total_review=self.total_review,
            pending_reviews=self.pending_reviews,
            blocked_amount=round(self.blocked_amount, 2),
            flagged_rate=round(flagged / self.total_processed, 4) if self.total_processed else 0.0,
            avg_latency_ms=round(sum(lat) / len(lat), 2) if lat else 0.0,
            p95_latency_ms=round(lat[int(0.95 * (len(lat) - 1))], 2) if lat else 0.0,
            detection_rate=round(self.fraud_flagged / self.fraud_total, 4) if self.fraud_total else None,
            false_positive_rate=round(self.normal_flagged / self.normal_total, 4) if self.normal_total else None,
        )
