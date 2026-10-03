import time

from flask import Response, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE_NAME = "gateway"

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "route", "status", "service"]
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds",
    ["method", "route", "status", "service"],
)


def init_metrics(app):
    @app.before_request
    def _start_timer():
        request._metrics_start = time.time()

    @app.after_request
    def _record(response):
        # Proxied requests match the catch-all <path:subpath> rule, not a
        # per-endpoint pattern -- label by the first two path segments
        # instead (e.g. "/api/auth") so at least which backend is slow is
        # visible without an unbounded cardinality explosion.
        parts = request.path.strip("/").split("/")
        route = "/" + "/".join(parts[:2]) if parts else request.path
        duration = time.time() - getattr(request, "_metrics_start", time.time())
        labels = dict(method=request.method, route=route, status=str(response.status_code), service=SERVICE_NAME)
        REQUEST_COUNT.labels(**labels).inc()
        REQUEST_DURATION.labels(**labels).observe(duration)
        return response

    @app.route("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
