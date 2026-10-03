"""Best-effort event publishing to RabbitMQ -- a down broker must not block
the write it's reporting on (fire-and-forget). Duplicated per-service like metrics.py.
"""
import json
import os

import pika

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672")
EXCHANGE = "buzz.events"

_connection = None


def _get_channel():
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = _connection.channel()
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    return channel


def publish_event(routing_key: str, payload: dict) -> None:
    try:
        channel = _get_channel()
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(payload).encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
        channel.close()
    except Exception as e:  # noqa: BLE001 -- a broker outage must not break the caller
        print(f"[events] failed to publish '{routing_key}': {e}")
