"""Cassandra TIMESTAMP <-> URL-safe id helpers. Duplicated in every service
that exposes a date-keyed row by URL (post-service, story-service,
engagement-service, messaging-service) -- pure, tiny, no shared package
needed. Millisecond precision matches Cassandra's own TIMESTAMP column, and
we only ever build these from values already round-tripped through
Cassandra, so exact equality lookups are safe.
"""
import datetime


def ts_to_id(dt: datetime.datetime) -> str:
    return str(int(dt.timestamp() * 1000))


def id_to_ts(raw: str) -> datetime.datetime:
    return datetime.datetime.utcfromtimestamp(int(raw) / 1000)
