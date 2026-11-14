"""GuardStream FastAPI application: lifespan wiring, REST and WebSocket endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal, close_db, get_session, init_db
from app.engine.ml_model import detector
from app.engine.processor import StreamProcessor
from app.models import AlertAudit, Transaction
from app.realtime import ConnectionManager, Metrics
from app.redis_client import RedisClient
from app.schemas import (
    BurstRequest,
    Decision,
    ReviewRequest,
    ReviewStatus,
    SimulatorState,
    SimulatorUpdate,
    Stats,
    TransactionOut,
    WSMessage,
)
from app.simulator.generator import TransactionSimulator

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
logger = logging.getLogger("guardstream")

ws_manager = ConnectionManager()
metrics = Metrics()


class AppState:
    """Holds long-lived services created during lifespan startup."""

    redis: RedisClient
    simulator: TransactionSimulator
    processor: StreamProcessor
    stats_task: asyncio.Task[None]


state = AppState()


async def _stats_loop() -> None:
    """Broadcast KPI snapshots to every dashboard once per interval."""
    while True:
        await asyncio.sleep(settings.stats_broadcast_interval_s)
        try:
            await ws_manager.broadcast(WSMessage(type="stats", data=metrics.snapshot().model_dump()))
        except Exception:
            logger.exception("Stats broadcast failed")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start DB, Redis, the ML model, the stream processor and the simulator."""
    await init_db()
    async with SessionLocal() as session:
        await metrics.load(session)

    state.redis = RedisClient()
    for attempt in range(1, 21):
        try:
            await state.redis.ping()
            break
        except Exception as exc:  # pragma: no cover - startup race
            logger.warning("Redis not ready (attempt %d/20): %s", attempt, exc)
            await asyncio.sleep(1.5)
    else:
        raise RuntimeError("Could not connect to Redis")

    await asyncio.to_thread(detector.train)

    state.processor = StreamProcessor(state.redis, detector, ws_manager, metrics)
    state.processor.start()

    state.simulator = TransactionSimulator(state.redis)

    async def _on_sim_change(s: SimulatorState) -> None:
        await ws_manager.broadcast(WSMessage(type="simulator", data=s.model_dump()))

    state.simulator.on_state_change = _on_sim_change
    await state.simulator.start()
    state.stats_task = asyncio.create_task(_stats_loop(), name="stats-loop")
    logger.info("GuardStream is live")

    yield

    state.stats_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await state.stats_task
    await state.simulator.stop()
    await state.processor.stop()
    await state.redis.close()
    await close_db()


app = FastAPI(
    title="GuardStream",
    description="Real-time financial fraud & anomaly detection",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

Session = Annotated[AsyncSession, Depends(get_session)]


# --------------------------------------------------------------------- health
@app.get("/api/health", tags=["system"])
async def health() -> dict[str, object]:
    """Liveness/readiness probe."""
    redis_ok = False
    with contextlib.suppress(Exception):
        redis_ok = await state.redis.ping()
    return {"status": "ok" if redis_ok and detector.ready else "degraded", "redis": redis_ok, "model": detector.ready,
            "ws_clients": ws_manager.count}


# --------------------------------------------------------------- transactions
@app.get("/api/transactions", response_model=list[TransactionOut], tags=["transactions"])
async def list_transactions(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    decision: Decision | None = None,
    card_id: str | None = None,
) -> list[Transaction]:
    """Most recent processed transactions, optionally filtered."""
    q = select(Transaction).order_by(Transaction.timestamp.desc()).limit(limit)
    if decision:
        q = q.where(Transaction.decision == decision.value)
    if card_id:
        q = q.where(Transaction.card_id == card_id)
    return list((await session.scalars(q)).all())


@app.get("/api/transactions/review-queue", response_model=list[TransactionOut], tags=["transactions"])
async def review_queue(session: Session, limit: Annotated[int, Query(ge=1, le=500)] = 200) -> list[Transaction]:
    """Transactions awaiting an analyst verdict, highest risk first."""
    q = (
        select(Transaction)
        .where(Transaction.review_status == ReviewStatus.PENDING.value)
        .order_by(Transaction.risk_score.desc(), Transaction.timestamp.desc())
        .limit(limit)
    )
    return list((await session.scalars(q)).all())


@app.get("/api/transactions/{tx_id}", response_model=TransactionOut, tags=["transactions"])
async def get_transaction(tx_id: str, session: Session) -> Transaction:
    """One transaction with its full risk breakdown."""
    tx = await session.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")
    return tx


@app.patch("/api/transactions/{tx_id}/review", response_model=TransactionOut, tags=["transactions"])
async def review_transaction(tx_id: str, body: ReviewRequest, session: Session) -> Transaction:
    """Record an analyst verdict on a REVIEW transaction and audit it."""
    tx = await session.get(Transaction, tx_id, with_for_update=True)
    if tx is None:
        raise HTTPException(404, "Transaction not found")
    if tx.review_status != ReviewStatus.PENDING.value:
        raise HTTPException(409, f"Transaction is not pending review (status={tx.review_status})")

    previous = tx.final_decision
    tx.final_decision = body.action
    tx.review_status = (
        ReviewStatus.CONFIRMED_FRAUD.value if body.action == "BLOCK" else ReviewStatus.CONFIRMED_LEGIT.value
    )
    tx.reviewed_by = body.analyst
    tx.reviewed_at = datetime.now(UTC)
    session.add(
        AlertAudit(
            transaction_id=tx.id,
            action=tx.review_status,
            previous_decision=previous,
            new_decision=body.action,
            analyst=body.analyst,
            notes=body.notes,
        )
    )
    await session.commit()
    await session.refresh(tx)

    metrics.record_review(tx)
    await ws_manager.broadcast(
        WSMessage(type="review_update", data=TransactionOut.model_validate(tx).model_dump(mode="json"))
    )
    return tx


# ---------------------------------------------------------------------- stats
@app.get("/api/stats", response_model=Stats, tags=["system"])
async def get_stats() -> Stats:
    """Current KPI snapshot."""
    return metrics.snapshot()


# ------------------------------------------------------------------ simulator
@app.get("/api/simulator", response_model=SimulatorState, tags=["simulator"])
async def get_simulator() -> SimulatorState:
    """Simulator settings and counters."""
    return state.simulator.state()


@app.patch("/api/simulator", response_model=SimulatorState, tags=["simulator"])
async def update_simulator(body: SimulatorUpdate) -> SimulatorState:
    """Start/stop the stream or change its speed and fraud rate."""
    return await state.simulator.update(body)


@app.post("/api/simulator/burst", tags=["simulator"])
async def fraud_burst(body: BurstRequest | None = None) -> dict[str, object]:
    """Inject a wave of attack scenarios right now (demo button)."""
    patterns = await state.simulator.trigger_burst((body or BurstRequest()).size)
    return {"injected": len(patterns), "patterns": patterns}


# ------------------------------------------------------------------ websocket
@app.websocket("/ws/transactions")
async def ws_transactions(ws: WebSocket) -> None:
    """Live feed. Sends a snapshot on connect, then transactions/stats/review updates."""
    await ws_manager.connect(ws)
    try:
        async with SessionLocal() as session:
            recent = (
                await session.scalars(select(Transaction).order_by(Transaction.timestamp.desc()).limit(60))
            ).all()
            queue = (
                await session.scalars(
                    select(Transaction)
                    .where(Transaction.review_status == ReviewStatus.PENDING.value)
                    .order_by(Transaction.risk_score.desc())
                    .limit(200)
                )
            ).all()
        await ws_manager.send(
            ws,
            WSMessage(
                type="snapshot",
                data={
                    "recent": [TransactionOut.model_validate(t).model_dump(mode="json") for t in recent],
                    "review_queue": [TransactionOut.model_validate(t).model_dump(mode="json") for t in queue],
                    "stats": metrics.snapshot().model_dump(),
                    "simulator": state.simulator.state().model_dump(),
                },
            ),
        )
        while True:
            await ws.receive_text()  # keep-alive; clients may send pings
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(ws)
