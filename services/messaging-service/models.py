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

KEYSPACE = "messaging"


class Message(Model):
    """conversation_id is the two usernames sorted and joined with '__', so
    both participants always land in the same partition regardless of who
    sent which message."""
    __keyspace__ = KEYSPACE
    __table_name__ = "messages"

    conversation_id = columns.Text(primary_key=True, partition_key=True)
    sent_at = columns.DateTime(primary_key=True, clustering_order="ASC", default=datetime.datetime.utcnow)
    sender_username = columns.Text(required=True)
    content = columns.Text(required=True)


class ConversationIndex(Model):
    """One row per (username, conversation partner), upserted in place on
    every new message so last_message_at/preview always reflect the latest
    state without scanning the messages table to list 'my conversations'."""
    __keyspace__ = KEYSPACE
    __table_name__ = "conversation_index"

    username = columns.Text(primary_key=True, partition_key=True)
    other_username = columns.Text(primary_key=True)
    last_message_at = columns.DateTime(required=True)
    last_message_preview = columns.Text(required=False)


def conversation_id_for(user_a: str, user_b: str) -> str:
    return "__".join(sorted([user_a, user_b]))


MODELS = [Message, ConversationIndex]


def init_db():
    contact_points = os.getenv("CASSANDRA_CONTACT_POINTS", "127.0.0.1").split(",")
    connection.setup(contact_points, KEYSPACE, retry_connect=True)
    for model in MODELS:
        sync_table(model)
