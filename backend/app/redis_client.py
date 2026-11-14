"""Redis Streams producer/consumer and sliding-window state helpers.

Key layout
----------
``gs:transactions:incoming``  Stream of raw authorization requests (field ``payload`` = JSON).
``gs:profiles``               Hash  card_id -> CardholderProfile JSON (customer master data).
``gs:vel:{card_id}``          Sorted set of tx ids scored by epoch-ms (velocity windows).
``gs:last:{card_id}``         Hash with the card's previous location (geo-jump rule).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from app.config import settings
from app.engine.state import CardWindowState
from app.schemas import CardholderProfile, TransactionIn

logger = logging.getLogger(__name__)

PROFILES_KEY = "gs:profiles"


class RedisClient:
    """Thin async wrapper around redis-py for GuardStream's needs."""

    def __init__(self, url: str = settings.redis_url) -> None:
        self.redis: aioredis.Redis = aioredis.from_url(url, decode_responses=True)

    async def ping(self) -> bool:
        """Return True when Redis answers."""
        return bool(await self.redis.ping())

    async def close(self) -> None:
        """Close the connection pool."""
        await self.redis.aclose()

    # ------------------------------------------------------------------ streams
    async def ensure_group(self) -> None:
        """Create the consumer group (and stream) if missing."""
        try:
            await self.redis.xgroup_create(settings.stream_key, settings.stream_group, id="$", mkstream=True)
            logger.info("Created consumer group %s", settings.stream_group)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, tx: TransactionIn) -> str:
        """Append a transaction to the ingestion stream."""
        return await self.redis.xadd(
            settings.stream_key,
            {"payload": tx.model_dump_json()},
            maxlen=settings.stream_maxlen,
            approximate=True,
        )

    async def read_batch(self, pending: bool = False) -> list[tuple[str, TransactionIn | None]]:
        """Read a batch of messages for this consumer.

        Args:
            pending: when True, re-read this consumer's un-acked messages (id ``0``)
                instead of new ones (id ``>``) — used for crash recovery on startup.
        """
        resp = await self.redis.xreadgroup(
            settings.stream_group,
            settings.stream_consumer,
            {settings.stream_key: "0" if pending else ">"},
            count=settings.stream_read_count,
            block=None if pending else settings.stream_block_ms,
        )
        out: list[tuple[str, TransactionIn | None]] = []
        for _stream, messages in resp or []:
            for msg_id, fields in messages:
                try:
                    out.append((msg_id, TransactionIn.model_validate_json(fields["payload"])))
                except (KeyError, ValueError) as exc:
                    logger.error("Dropping malformed message %s: %s", msg_id, exc)
                    out.append((msg_id, None))
        return out

    async def ack(self, *msg_ids: str) -> None:
        """Acknowledge processed messages."""
        if msg_ids:
            await self.redis.xack(settings.stream_key, settings.stream_group, *msg_ids)

    # ---------------------------------------------------------------- profiles
    async def save_profiles(self, profiles: list[CardholderProfile]) -> None:
        """Bulk-store cardholder baselines."""
        if profiles:
            await self.redis.hset(PROFILES_KEY, mapping={p.card_id: p.model_dump_json() for p in profiles})

    async def get_profile(self, card_id: str) -> CardholderProfile | None:
        """Fetch a cardholder baseline."""
        raw = await self.redis.hget(PROFILES_KEY, card_id)
        return CardholderProfile.model_validate_json(raw) if raw else None

    # ---------------------------------------------------------- sliding windows
    async def record_and_get_window(self, tx: TransactionIn) -> CardWindowState:
        """Atomically register ``tx`` in the card's windows and return prior state.

        One pipelined round-trip:
          1. read the previous-location hash,
          2. add this tx to the velocity sorted set and evict entries > 10 min old,
          3. count entries in the velocity / 10-minute windows,
          4. overwrite the previous-location hash with this tx.
        """
        now_ms = int(tx.timestamp.timestamp() * 1000)
        vel_key = f"gs:vel:{tx.card_id}"
        last_key = f"gs:last:{tx.card_id}"
        feature_ms = settings.feature_window_s * 1000
        velocity_ms = settings.velocity_window_s * 1000

        pipe = self.redis.pipeline(transaction=True)
        pipe.hgetall(last_key)
        pipe.zremrangebyscore(vel_key, "-inf", now_ms - feature_ms)
        pipe.zcount(vel_key, now_ms - velocity_ms, "+inf")
        pipe.zcount(vel_key, now_ms - feature_ms, "+inf")
        pipe.zadd(vel_key, {tx.id: now_ms})
        pipe.expire(vel_key, settings.feature_window_s + 60)
        pipe.hset(
            last_key,
            mapping={
                "country": tx.country,
                "city": tx.city,
                "lat": tx.lat,
                "lon": tx.lon,
                "ts_ms": now_ms,
            },
        )
        pipe.expire(last_key, settings.geo_window_s + 60)
        last, _, vel_count, count_10m, *_ = await pipe.execute()

        return CardWindowState(
            prior_count_velocity=int(vel_count),
            prior_count_10m=int(count_10m),
            last_country=last.get("country"),
            last_city=last.get("city"),
            last_lat=float(last["lat"]) if "lat" in last else None,
            last_lon=float(last["lon"]) if "lon" in last else None,
            last_ts_ms=int(last["ts_ms"]) if "ts_ms" in last else None,
        )

    async def flush_card_state(self) -> None:
        """Delete velocity/location state (used for demo resets)."""
        async for key in self.redis.scan_iter(match="gs:vel:*", count=500):
            await self.redis.delete(key)
        async for key in self.redis.scan_iter(match="gs:last:*", count=500):
            await self.redis.delete(key)


def dumps(obj: object) -> str:
    """JSON-encode with datetime support."""
    return json.dumps(obj, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o))
