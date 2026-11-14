"""Deterministic business rules evaluated against Redis sliding-window state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.config import settings
from app.engine.state import CardWindowState
from app.schemas import CardholderProfile, RuleHit, TransactionIn
from app.simulator.catalog import COUNTRY_LABEL, haversine_km


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything a rule may look at."""

    tx: TransactionIn
    profile: CardholderProfile
    window: CardWindowState

    @property
    def now_ms(self) -> int:
        """Transaction time in epoch milliseconds."""
        return int(self.tx.timestamp.timestamp() * 1000)


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    return f"{minutes}m" if sec == 0 or minutes >= 5 else f"{minutes}m {sec}s"


def rule_velocity(ctx: RuleContext) -> RuleHit | None:
    """RULE_VELOCITY: more than N transactions on one card inside the velocity window."""
    count = ctx.window.prior_count_velocity + 1  # include the current transaction
    if count > settings.rule_velocity_max_tx:
        return RuleHit(
            code="RULE_VELOCITY",
            points=settings.rule_velocity_points,
            reason=f"Velocity Attack ({count} tx in {settings.velocity_window_s}s, limit {settings.rule_velocity_max_tx})",
        )
    return None


def rule_geo_jump(ctx: RuleContext) -> RuleHit | None:
    """RULE_GEO_JUMP: different country than the previous transaction within 30 minutes."""
    w = ctx.window
    if not w.last_country or w.last_ts_ms is None or w.last_country == ctx.tx.country:
        return None
    elapsed_s = (ctx.now_ms - w.last_ts_ms) / 1000
    if elapsed_s > settings.geo_window_s:
        return None
    src = COUNTRY_LABEL.get(w.last_country, w.last_country)
    dst = COUNTRY_LABEL.get(ctx.tx.country, ctx.tx.country)
    detail = ""
    if w.last_lat is not None and w.last_lon is not None:
        km = haversine_km(w.last_lat, w.last_lon, ctx.tx.lat, ctx.tx.lon)
        detail = f", {km:,.0f} km"
    return RuleHit(
        code="RULE_GEO_JUMP",
        points=settings.rule_geo_jump_points,
        reason=f"Impossible Travel ({src} -> {dst} in {_fmt_duration(elapsed_s)}{detail})",
    )


def rule_high_amount(ctx: RuleContext) -> RuleHit | None:
    """RULE_HIGH_AMOUNT: amount above the limit on a standard-tier card."""
    if ctx.profile.tier == "standard" and ctx.tx.amount > settings.rule_high_amount_threshold:
        return RuleHit(
            code="RULE_HIGH_AMOUNT",
            points=settings.rule_high_amount_points,
            reason=f"High Amount (${ctx.tx.amount:,.2f} > ${settings.rule_high_amount_threshold:,.0f} on standard card)",
        )
    return None


RULES: tuple[Callable[[RuleContext], RuleHit | None], ...] = (rule_velocity, rule_geo_jump, rule_high_amount)


def evaluate_rules(tx: TransactionIn, profile: CardholderProfile, window: CardWindowState) -> list[RuleHit]:
    """Run every rule and return the ones that fired."""
    ctx = RuleContext(tx=tx, profile=profile, window=window)
    return [hit for rule in RULES if (hit := rule(ctx)) is not None]
