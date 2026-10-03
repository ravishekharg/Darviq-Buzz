import sys
from types import ModuleType

# Python 3.12 removed the 'asyncore' stdlib module that cassandra-driver's
# asyncio reactor still imports at load time -- same compatibility patch the
# original monolith needed (see the old app.py's top-of-file comment).
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

KEYSPACE = "social_graph"


class Following(Model):
    """Rows: 'who does <follower_username> follow'."""
    __keyspace__ = KEYSPACE
    __table_name__ = "following"

    follower_username = columns.Text(primary_key=True, partition_key=True)
    followed_username = columns.Text(primary_key=True)
    followed_at = columns.DateTime(default=datetime.datetime.utcnow)


class Followers(Model):
    """Denormalized inverse of Following, written/deleted together with it."""
    __keyspace__ = KEYSPACE
    __table_name__ = "followers"

    followed_username = columns.Text(primary_key=True, partition_key=True)
    follower_username = columns.Text(primary_key=True)
    followed_at = columns.DateTime(default=datetime.datetime.utcnow)


class FriendRequest(Model):
    """Rows: pending friend requests sent BY sender_username. Deleted (not
    status-flagged) on accept/decline/cancel."""
    __keyspace__ = KEYSPACE
    __table_name__ = "friend_requests_sent"

    sender_username = columns.Text(primary_key=True, partition_key=True)
    receiver_username = columns.Text(primary_key=True)
    requested_at = columns.DateTime(default=datetime.datetime.utcnow)


class IncomingFriendRequest(Model):
    """Denormalized inverse of FriendRequest."""
    __keyspace__ = KEYSPACE
    __table_name__ = "friend_requests_received"

    receiver_username = columns.Text(primary_key=True, partition_key=True)
    sender_username = columns.Text(primary_key=True)
    requested_at = columns.DateTime(default=datetime.datetime.utcnow)


class Friendship(Model):
    """Symmetric: a row is written for BOTH users on accept, deleted for
    both on unfriend."""
    __keyspace__ = KEYSPACE
    __table_name__ = "friendships"

    username = columns.Text(primary_key=True, partition_key=True)
    friend_username = columns.Text(primary_key=True)
    friends_since = columns.DateTime(default=datetime.datetime.utcnow)


MODELS = [Following, Followers, FriendRequest, IncomingFriendRequest, Friendship]


def init_db():
    contact_points = os.getenv("CASSANDRA_CONTACT_POINTS", "127.0.0.1").split(",")
    connection.setup(contact_points, KEYSPACE, retry_connect=True)
    for model in MODELS:
        sync_table(model)
