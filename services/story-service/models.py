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

KEYSPACE = "stories"


class Story(Model):
    """Rows carry a Cassandra-native TTL (see STORY_TTL_SECONDS in app.py)
    so expiry is enforced by the database itself -- an expired story simply
    stops appearing in queries, no cleanup job needed."""
    __keyspace__ = KEYSPACE
    __table_name__ = "stories"

    username = columns.Text(primary_key=True, partition_key=True)
    created_at = columns.DateTime(primary_key=True, clustering_order="DESC", default=datetime.datetime.utcnow)
    content = columns.Text(required=False)
    image_url = columns.Text(required=False)


MODELS = [Story]


def init_db():
    contact_points = os.getenv("CASSANDRA_CONTACT_POINTS", "127.0.0.1").split(",")
    connection.setup(contact_points, KEYSPACE, retry_connect=True)
    for model in MODELS:
        sync_table(model)
