import time

from flask import Response, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE_NAME = "media-service"

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "route", "status", "service"]
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds",
    ["method", "route", "status", "service"],
)

# media-service-specific: upload latency by backend, and how often S3 fails
# over to local disk -- the two numbers that matter for this service's own
# alerting (a rising S3-fallback rate means real AWS credentials/bucket
# trouble, not just "local dev has no S3").
UPLOAD_DURATION = Histogram(
    "media_upload_duration_seconds", "Time to store an uploaded image", ["backend"],
    buckets=[0.05, 0.1, 0.5, 1, 2.5, 5, 10],
)
S3_FALLBACK_TOTAL = Counter(
    "media_s3_fallback_total", "Total uploads that fell back to local disk after S3 failed"
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
