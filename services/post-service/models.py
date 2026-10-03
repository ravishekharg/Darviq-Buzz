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

KEYSPACE = "posts"


class Post(Model):
    __keyspace__ = KEYSPACE
    __table_name__ = "user_posts"

    username = columns.Text(primary_key=True, partition_key=True)
    date_posted = columns.DateTime(primary_key=True, clustering_order="DESC", default=datetime.datetime.utcnow)
    content = columns.Text(required=True)
    image_url = columns.Text(required=False)


class Hashtag(Model):
    """Index table for browsing posts by tag: partitioned by the tag
    itself, newest posts first."""
    __keyspace__ = KEYSPACE
    __table_name__ = "hashtags"

    tag = columns.Text(primary_key=True, partition_key=True)
    date_posted = columns.DateTime(primary_key=True, clustering_order="DESC")
    post_username = columns.Text(primary_key=True)


class Repost(Model):
    __keyspace__ = KEYSPACE
    __table_name__ = "reposts"

    reposter_username = columns.Text(primary_key=True, partition_key=True)
    repost_date = columns.DateTime(primary_key=True, clustering_order="DESC", default=datetime.datetime.utcnow)
    original_username = columns.Text(required=True)
    original_date_posted = columns.DateTime(required=True)
    comment = columns.Text(required=False)


MODELS = [Post, Hashtag, Repost]


def init_db():
    contact_points = os.getenv("CASSANDRA_CONTACT_POINTS", "127.0.0.1").split(",")
    connection.setup(contact_points, KEYSPACE, retry_connect=True)
    for model in MODELS:
        sync_table(model)
