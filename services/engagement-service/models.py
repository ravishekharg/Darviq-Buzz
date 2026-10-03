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

KEYSPACE = "engagement"


class Like(Model):
    __keyspace__ = KEYSPACE
    __table_name__ = "likes"

    post_username = columns.Text(primary_key=True, partition_key=True)
    post_date_posted = columns.DateTime(primary_key=True, partition_key=True)
    liker_username = columns.Text(primary_key=True)
    liked_at = columns.DateTime(default=datetime.datetime.utcnow)
    reaction_type = columns.Text(required=False, default="like")


class Comment(Model):
    __keyspace__ = KEYSPACE
    __table_name__ = "comments"

    post_username = columns.Text(primary_key=True, partition_key=True)
    post_date_posted = columns.DateTime(primary_key=True, partition_key=True)
    comment_date = columns.DateTime(primary_key=True, clustering_order="ASC", default=datetime.datetime.utcnow)
    commenter_username = columns.Text(primary_key=True)
    content = columns.Text(required=True)


MODELS = [Like, Comment]


def init_db():
    contact_points = os.getenv("CASSANDRA_CONTACT_POINTS", "127.0.0.1").split(",")
    connection.setup(contact_points, KEYSPACE, retry_connect=True)
    for model in MODELS:
        sync_table(model)
