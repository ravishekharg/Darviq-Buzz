import sys
from types import ModuleType

if "asyncore" not in sys.modules:
    mock_asyncore = ModuleType("asyncore")
    mock_asyncore.loop = lambda *args, **kwargs: None
    mock_asyncore.dispatcher = object
    sys.modules["asyncore"] = mock_asyncore

import os

if "CASSANDRA_SOCKET_FACTORY" not in os.environ:
    os.environ["CASSANDRA_SOCKET_FACTORY"] = "cassandra.io.asyncioreactor.AsyncioConnection"

import datetime

from cassandra.cqlengine import columns, connection
from cassandra.cqlengine.management import sync_table
from cassandra.cqlengine.models import Model

KEYSPACE = "feed"


class Timeline(Model):
    """Precomputed per-user feed (fan-out-on-write): one row per (post or
    repost) that should appear in `username`'s feed, written at publish time
    by the RabbitMQ consumer in consumer.py rather than assembled at read
    time. Replaces the original monolith's scatter-gather build_feed()."""
    __keyspace__ = KEYSPACE
    __table_name__ = "timeline"

    username = columns.Text(primary_key=True, partition_key=True)
    sort_key = columns.DateTime(primary_key=True, clustering_order="DESC")
    entry_type = columns.Text(required=True)  # "post" | "repost"
    ref_username = columns.Text(required=True)  # the post's original author
    ref_url_id = columns.Text(required=True)
    reposted_by = columns.Text(required=False)  # set only for entry_type == "repost"
    repost_comment = columns.Text(required=False)


MODELS = [Timeline]


def init_db():
    contact_points = os.getenv("CASSANDRA_CONTACT_POINTS", "127.0.0.1").split(",")
    connection.setup(contact_points, KEYSPACE, retry_connect=True)
    for model in MODELS:
        sync_table(model)
