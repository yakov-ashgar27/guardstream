"""Controllable background traffic generator publishing to the Redis Stream.

Normal traffic (~90%) follows each cardholder's habits. Fraud scenarios
(~10% of events) run as their own asyncio tasks because they unfold over
several seconds:

* ``GEO_JUMP``      — a purchase at home, then one abroad seconds later.
* ``CARD_TESTING``  — 4-6 micro charges ($1-$3) within 60 seconds.
* ``HIGH_VALUE``    — 10-15x the user's average, at 01:00-04:00 local time.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.config import settings
from app.redis_client import RedisClient
from app.schemas import CardholderProfile, SimulatorState, SimulatorUpdate, TransactionIn
from app.simulator.catalog import (
    CARD_TESTING_MERCHANTS,
    CATEGORIES,
    CITIES,
    PurchaseDraft,
    generate_profiles,
    sample_normal_purchase,
)

logger = logging.getLogger(__name__)

FRAUD_PATTERNS: tuple[str, ...] = ("GEO_JUMP", "CARD_TESTING", "HIGH_VALUE")


class TransactionSimulator:
    """Generates realistic and fraudulent traffic at a configurable rate."""

    def __init__(self, redis: RedisClient, *, seed: int = settings.sim_seed) -> None:
        self.redis = redis
        self.rng = random.Random(seed)
        self.profiles: list[CardholderProfile] = generate_profiles(settings.sim_cardholders, self.rng)
        self.tps: float = settings.sim_default_tps
        self.fraud_rate: float = settings.sim_default_fraud_rate
        self.generated = 0
        self.fraud_injected = 0
        self._running = asyncio.Event()
        self._busy_until: dict[str, float] = {}
        self._loop_task: asyncio.Task[None] | None = None
        self._scenarios: set[asyncio.Task[None]] = set()
        self.on_state_change: Callable[[SimulatorState], Awaitable[None]] | None = None

    # ------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        """Publish cardholder baselines and launch the generator loop."""
        await self.redis.save_profiles(self.profiles)
        if settings.sim_autostart:
            self._running.set()
        self._loop_task = asyncio.create_task(self._loop(), name="simulator-loop")
        logger.info("Simulator ready with %d cardholders (running=%s)", len(self.profiles), self.running)

    async def stop(self) -> None:
        """Cancel the loop and any in-flight scenarios."""
        tasks = [t for t in (self._loop_task, *self._scenarios) if t]
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t

    @property
    def running(self) -> bool:
        """Whether traffic is flowing."""
        return self._running.is_set()

    def state(self) -> SimulatorState:
        """Snapshot of the simulator settings and counters."""
        return SimulatorState(
            running=self.running,
            tps=self.tps,
            fraud_rate=self.fraud_rate,
            max_tps=settings.sim_max_tps,
            generated=self.generated,
            fraud_injected=self.fraud_injected,
        )

    async def update(self, upd: SimulatorUpdate) -> SimulatorState:
        """Apply a partial settings update."""
        if upd.tps is not None:
            self.tps = min(upd.tps, settings.sim_max_tps)
        if upd.fraud_rate is not None:
            self.fraud_rate = upd.fraud_rate
        if upd.running is True:
            self._running.set()
        elif upd.running is False:
            self._running.clear()
        await self._notify()
        return self.state()

    async def trigger_burst(self, size: int) -> list[str]:
        """Immediately launch ``size`` fraud scenarios, cycling through every pattern."""
        patterns = [FRAUD_PATTERNS[i % len(FRAUD_PATTERNS)] for i in range(size)]
        self.rng.shuffle(patterns)
        for i, pattern in enumerate(patterns):
            self._spawn(pattern, delay=i * 0.35)
        await self._notify()
        return patterns

    async def _notify(self) -> None:
        if self.on_state_change:
            await self.on_state_change(self.state())

    # ------------------------------------------------------------------ loop
    async def _loop(self) -> None:
        while True:
            try:
                await self._running.wait()
                # Poisson arrivals: exponential inter-arrival times around 1/tps.
                await asyncio.sleep(min(self.rng.expovariate(self.tps), 5 / self.tps))
                if not self.running:
                    continue
                if self.rng.random() < self.fraud_rate:
                    self._spawn(self.rng.choice(FRAUD_PATTERNS))
                else:
                    await self._emit_normal()
            except asyncio.CancelledError:
                raise
            except Exception:  # keep the generator alive on transient Redis errors
                logger.exception("Simulator tick failed")
                await asyncio.sleep(1)

    def _pick_card(self, hold_s: float) -> CardholderProfile | None:
        """Choose a card that is not cooling down and reserve it for ``hold_s`` seconds."""
        now = time.monotonic()
        for _ in range(25):
            p = self.rng.choice(self.profiles)
            if self._busy_until.get(p.card_id, 0) <= now:
                self._busy_until[p.card_id] = now + hold_s
                return p
        return None

    async def _emit_normal(self) -> None:
        profile = self._pick_card(settings.sim_normal_card_cooldown_s)
        if profile:
            await self._publish(profile, sample_normal_purchase(profile, self.rng))

    async def _publish(self, profile: CardholderProfile, d: PurchaseDraft, pattern: str | None = None) -> None:
        tx = TransactionIn(
            id=str(uuid.uuid4()),
            card_id=profile.card_id,
            amount=round(d.amount, 2),
            currency="USD",
            merchant=d.merchant,
            merchant_category=d.category,
            city=d.city,
            country=d.country,
            lat=d.lat,
            lon=d.lon,
            local_hour=d.local_hour,
            timestamp=datetime.now(UTC),
            sim_pattern=pattern,
        )
        await self.redis.publish(tx)
        self.generated += 1

    # ------------------------------------------------------------- scenarios
    def _spawn(self, pattern: str, delay: float = 0.0) -> None:
        task = asyncio.create_task(self._run_scenario(pattern, delay), name=f"fraud-{pattern}")
        self._scenarios.add(task)
        task.add_done_callback(self._scenarios.discard)

    async def _run_scenario(self, pattern: str, delay: float) -> None:
        try:
            if delay:
                await asyncio.sleep(delay)
            # Hold the card long enough that normal traffic does not collide with the attack.
            profile = self._pick_card(hold_s=1_900 if pattern == "GEO_JUMP" else 700)
            if profile is None:
                return
            self.fraud_injected += 1
            match pattern:
                case "GEO_JUMP":
                    await self._geo_jump(profile)
                case "CARD_TESTING":
                    await self._card_testing(profile)
                case "HIGH_VALUE":
                    await self._high_value(profile)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Fraud scenario %s failed", pattern)

    async def _geo_jump(self, p: CardholderProfile) -> None:
        """Legit purchase at home, then the cloned card is used abroad seconds later."""
        await self._publish(p, sample_normal_purchase(p, self.rng))
        await asyncio.sleep(self.rng.uniform(2, 8))
        country = self.rng.choice([c for c in CITIES if c != p.home_country])
        city, lat, lon = self.rng.choice(CITIES[country])
        cat = CATEGORIES[self.rng.choice(("electronics", "fashion", "online_retail", "travel"))]
        for _ in range(self.rng.choice((1, 1, 2))):
            await self._publish(
                p,
                PurchaseDraft(
                    amount=round(p.avg_amount * self.rng.uniform(1.5, 5.0), 2),
                    merchant=self.rng.choice(cat.merchants),
                    category=cat.name,
                    city=city,
                    country=country,
                    lat=round(lat + self.rng.uniform(-0.03, 0.03), 5),
                    lon=round(lon + self.rng.uniform(-0.03, 0.03), 5),
                    local_hour=self.rng.randint(9, 22),
                ),
                pattern="GEO_JUMP",
            )
            await asyncio.sleep(self.rng.uniform(3, 10))

    async def _card_testing(self, p: CardholderProfile) -> None:
        """4-6 micro charges on a digital-goods merchant inside one minute."""
        merchant = self.rng.choice(CARD_TESTING_MERCHANTS)
        base = sample_normal_purchase(p, self.rng)
        for _ in range(self.rng.randint(4, 6)):
            await self._publish(
                p,
                PurchaseDraft(
                    amount=round(self.rng.uniform(1.0, 3.0), 2),
                    merchant=merchant,
                    category="online_retail",
                    city=base.city,
                    country=base.country,
                    lat=base.lat,
                    lon=base.lon,
                    local_hour=base.local_hour,
                ),
                pattern="CARD_TESTING",
            )
            await asyncio.sleep(self.rng.uniform(2, 9))

    async def _high_value(self, p: CardholderProfile) -> None:
        """One purchase 10-15x the user's average in the middle of the night."""
        cat = CATEGORIES[self.rng.choice(("electronics", "travel", "fashion"))]
        base = sample_normal_purchase(p, self.rng)
        await self._publish(
            p,
            PurchaseDraft(
                amount=round(p.avg_amount * self.rng.uniform(10, 15), 2),
                merchant=self.rng.choice(cat.merchants),
                category=cat.name,
                city=base.city,
                country=base.country,
                lat=base.lat,
                lon=base.lon,
                local_hour=self.rng.randint(1, 4),
            ),
            pattern="HIGH_VALUE",
        )
