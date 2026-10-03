import time

from flask import Response, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE_NAME = "feed-service"

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "route", "status", "service"]
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds",
    ["method", "route", "status", "service"],
)

# Fan-out-specific: how long it takes to write the timeline row for every
# follower after a post/repost event is consumed, and how many followers
# were fanned out to -- the two numbers that matter for "is fan-out keeping
# up" alerting (see prometheus/alerts.yml).
FANOUT_DURATION = Histogram(
    "feed_fanout_duration_seconds", "Time to fan out one post/repost event to all followers",
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2.5, 5, 10],
)
FANOUT_FOLLOWERS = Histogram(
    "feed_fanout_followers_count", "Number of followers fanned out to per event",
    buckets=[0, 1, 5, 10, 50, 100, 500, 1000],
)
EVENTS_CONSUMED = Counter(
    "feed_events_consumed_total", "Total events consumed from RabbitMQ", ["routing_key"]
)


def init_metrics(app):
    @app.before_request
    def _start_timer():
        request._metrics_start = time.time()

    @app.after_request
    def _record(response):
        route = request.url_rule.rule if request.url_rule else request.path
        duration = time.time() - getattr(request, "_metrics_start", time.time())
        labels = dict(method=request.method, route=route, status=str(response.status_code), service=SERVICE_NAME)
        REQUEST_COUNT.labels(**labels).inc()
        REQUEST_DURATION.labels(**labels).observe(duration)
        return response

    @app.route("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
