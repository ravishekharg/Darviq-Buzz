"""RabbitMQ consumer -- see feed-service/consumer.py for the background-
thread-plus-reconnect reasoning, duplicated here with notification-service's
own event-to-row mapping."""
import json
import os
import threading
import time

import pika

from metrics import EVENTS_CONSUMED
from models import Notification, SessionLocal

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672")
EXCHANGE = "buzz.events"
QUEUE = "notification-service.notify"

_connected = False


def is_connected() -> bool:
    return _connected


def _notify(recipient: str, actor: str, notif_type: str, target_ref: str | None = None) -> None:
    if recipient == actor:
        return  # never notify someone about their own action
    db = SessionLocal()
    try:
        db.add(Notification(recipient_username=recipient, actor_username=actor, notif_type=notif_type, target_ref=target_ref))
        db.commit()
    finally:
        db.close()


def _handle_user_followed(p: dict) -> None:
    _notify(recipient=p["followed"], actor=p["follower"], notif_type="follow")


def _handle_friend_request_sent(p: dict) -> None:
    _notify(recipient=p["receiver"], actor=p["sender"], notif_type="friend_request")


def _handle_friend_request_accepted(p: dict) -> None:
    # The receiver accepted the sender's request -- notify the original sender.
    _notify(recipient=p["sender"], actor=p["receiver"], notif_type="friend_accept")


def _handle_post_liked(p: dict) -> None:
    _notify(
        recipient=p["post_username"], actor=p["liker"], notif_type="like",
        target_ref=f"{p['post_username']}:{p['post_url_id']}",
    )


def _handle_post_commented(p: dict) -> None:
    _notify(
        recipient=p["post_username"], actor=p["commenter"], notif_type="comment",
        target_ref=f"{p['post_username']}:{p['post_url_id']}",
    )


def _handle_post_reposted(p: dict) -> None:
    _notify(
        recipient=p["original_username"], actor=p["reposter"], notif_type="repost",
        target_ref=f"{p['original_username']}:{p['original_url_id']}",
    )


HANDLERS = {
    "user.followed": _handle_user_followed,
    "friend.request_sent": _handle_friend_request_sent,
    "friend.request_accepted": _handle_friend_request_accepted,
    "post.liked": _handle_post_liked,
    "post.commented": _handle_post_commented,
    "post.reposted": _handle_post_reposted,
}


def _run() -> None:
    global _connected
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            channel = connection.channel()
            channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
            channel.queue_declare(queue=QUEUE, durable=True)
            for routing_key in HANDLERS:
                channel.queue_bind(exchange=EXCHANGE, queue=QUEUE, routing_key=routing_key)

            _connected = True
            print(f"[notification-service] connected, consuming {list(HANDLERS)} from '{QUEUE}'")

            def on_message(ch, method, _properties, body):
                try:
                    payload = json.loads(body)
                    HANDLERS[method.routing_key](payload)
                    EVENTS_CONSUMED.labels(routing_key=method.routing_key).inc()
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:  # noqa: BLE001
                    print(f"[notification-service] failed to process message: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            channel.basic_consume(queue=QUEUE, on_message_callback=on_message)
            channel.start_consuming()
        except Exception as e:  # noqa: BLE001
            _connected = False
            print(f"[notification-service] rabbitmq connection lost/failed, retrying in 5s: {e}")
            time.sleep(5)


def start_consumer_thread() -> None:
    threading.Thread(target=_run, daemon=True).start()
