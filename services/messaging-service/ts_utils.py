"""Cassandra TIMESTAMP <-> URL-safe id helpers. Duplicated in every service
that exposes a date-keyed row by URL (post-service, story-service,
engagement-service, messaging-service) -- pure, tiny, no shared package
needed. Millisecond precision matches Cassandra's own TIMESTAMP column, and
we only ever build these from values already round-tripped through
Cassandra, so exact equality lookups are safe.
"""
import datetime

from werkzeug.exceptions import NotFound


def ts_to_id(dt: datetime.datetime) -> str:
    return str(int(dt.timestamp() * 1000))


def id_to_ts(raw: str) -> datetime.datetime:
    # A malformed id in a URL (a typo, a truncated link) is a 404, not a server error. Found by the
    # Darviq-Observability dashboards: every mistyped post link was showing up as a 500.
    try:
        return datetime.datetime.utcfromtimestamp(int(raw) / 1000)
    except (ValueError, OverflowError, OSError):
        raise NotFound("No such item")
