"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transaction(Base):
    """A processed card transaction with its risk evaluation."""

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    card_id: Mapped[str] = mapped_column(String(32), index=True)
    cardholder_name: Mapped[str] = mapped_column(String(80))
    card_tier: Mapped[str] = mapped_column(String(16))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    merchant: Mapped[str] = mapped_column(String(120))
    merchant_category: Mapped[str] = mapped_column(String(40))
    city: Mapped[str] = mapped_column(String(60))
    country: Mapped[str] = mapped_column(String(2))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    local_hour: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Evaluation
    rule_score: Mapped[int] = mapped_column(Integer)
    ml_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[int] = mapped_column(Integer, index=True)
    decision: Mapped[str] = mapped_column(String(10), index=True)
    triggered_rules: Mapped[list[str]] = mapped_column(JSONB, default=list)
    triggered_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    user_baseline: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    processing_ms: Mapped[float] = mapped_column(Float)

    # Analyst workflow
    review_status: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    final_decision: Mapped[str] = mapped_column(String(10))
    reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Ground-truth label from the simulator (never used by the engine).
    sim_pattern: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    audits: Mapped[list[AlertAudit]] = relationship(back_populates="transaction", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_transactions_review_pending", "review_status", "timestamp"),)


class AlertAudit(Base):
    """Immutable audit trail of analyst decisions."""

    __tablename__ = "alert_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    previous_decision: Mapped[str] = mapped_column(String(10))
    new_decision: Mapped[str] = mapped_column(String(10))
    analyst: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transaction: Mapped[Transaction] = relationship(back_populates="audits")
