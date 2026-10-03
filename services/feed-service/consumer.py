"""RabbitMQ consumer for the fan-out-on-write timeline: runs in a background
thread alongside the Flask app (pika's BlockingConnection needs its own
loop, separate from Flask's request-handling thread). Retries with backoff
if RabbitMQ isn't up yet -- nothing in k8s/compose guarantees ordering.
"""
import datetime
import json
import os
import threading
import time

import pika
import requests

from metrics import EVENTS_CONSUMED, FANOUT_DURATION, FANOUT_FOLLOWERS
from models import Timeline

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672")
EXCHANGE = "buzz.events"
QUEUE = "feed-service.fanout"
SOCIAL_GRAPH_SERVICE_URL = os.environ.get("SOCIAL_GRAPH_SERVICE_URL", "http://social-graph-service:5002")

_connected = False


def is_connected() -> bool:
    return _connected


def _followers_of(username: str) -> list[str]:
    # Confirmed live on this cluster: in-cluster DNS lookups intermittently
    # fail to resolve under load (a known glibc-resolver/CoreDNS race, not an
    # actual outage). Unlike a user-facing request, there's no one to retry
    # this call by hand -- silently returning [] here means a post never
    # reaches any follower's feed at all, so a couple of quick retries on
    # connection-level failures matters more here than anywhere else in the
    # app.
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(f"{SOCIAL_GRAPH_SERVICE_URL}/follow/{username}/followers", timeout=5)
            resp.raise_for_status()
            return resp.json().get("usernames", [])
        except requests.exceptions.ConnectionError as e:
            print(f"[feed-service] failed to fetch followers of {username} (attempt {attempt}/{attempts}): {e}")
            if attempt < attempts:
                time.sleep(0.3)
        except requests.RequestException as e:
            print(f"[feed-service] failed to fetch followers of {username}: {e}")
            return []
    return []


def _fan_out(entry_type: str, ref_username: str, ref_url_id: str, audience: list[str], reposted_by: str | None, repost_comment: str | None = None) -> None:
    start = time.time()
    sort_key = datetime.datetime.utcnow()
    for recipient in audience:
        Timeline.create(
            username=recipient, sort_key=sort_key, entry_type=entry_type,
            ref_username=ref_username, ref_url_id=ref_url_id, reposted_by=reposted_by,
            repost_comment=repost_comment,
        )
    FANOUT_DURATION.observe(time.time() - start)
    FANOUT_FOLLOWERS.observe(len(audience))


def _handle_post_created(payload: dict) -> None:
    username = payload["username"]
    # The author always sees their own post in their feed, whether or not
    # they follow themselves.
    audience = list({*_followers_of(username), username})
    _fan_out("post", username, payload["url_id"], audience, reposted_by=None)


def _handle_post_reposted(payload: dict) -> None:
    reposter = payload["reposter"]
    audience = list({*_followers_of(reposter), reposter})
    _fan_out(
        "repost", payload["original_username"], payload["original_url_id"], audience,
        reposted_by=reposter, repost_comment=payload.get("comment"),
    )


HANDLERS = {
    "post.created": _handle_post_created,
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
            print(f"[feed-service] connected, consuming {list(HANDLERS)} from '{QUEUE}'")

            def on_message(ch, method, _properties, body):
                try:
                    payload = json.loads(body)
                    HANDLERS[method.routing_key](payload)
                    EVENTS_CONSUMED.labels(routing_key=method.routing_key).inc()
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:  # noqa: BLE001
                    print(f"[feed-service] failed to process message: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            channel.basic_consume(queue=QUEUE, on_message_callback=on_message)
            channel.start_consuming()
        except Exception as e:  # noqa: BLE001
            _connected = False
            print(f"[feed-service] rabbitmq connection lost/failed, retrying in 5s: {e}")
            time.sleep(5)


def start_consumer_thread() -> None:
    threading.Thread(target=_run, daemon=True).start()
