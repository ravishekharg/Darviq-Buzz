import os
import time

import jwt
import requests
from flask import Flask, Response, jsonify, request

from metrics import init_metrics

app = Flask(__name__)
init_metrics(app)

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-change-me")

# Route table: path prefix -> target service base URL. Every prefix strips
# only the literal "/api" before forwarding -- every backend service mounts
# its own routes to match exactly what's left (e.g. gateway "/api/auth/login"
# -> user-service "/auth/login"), so no per-service path-rewrite rules are
# needed as more services are added here in later checkpoints.
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://user-service:5001")
POST_SERVICE_URL = os.environ.get("POST_SERVICE_URL", "http://post-service:5003")

SERVICES = {
    "/api/auth": USER_SERVICE_URL,
    "/api/users": USER_SERVICE_URL,
    "/api/follow": os.environ.get("SOCIAL_GRAPH_SERVICE_URL", "http://social-graph-service:5002"),
    "/api/friends": os.environ.get("SOCIAL_GRAPH_SERVICE_URL", "http://social-graph-service:5002"),
    "/api/friend-requests": os.environ.get("SOCIAL_GRAPH_SERVICE_URL", "http://social-graph-service:5002"),
    "/api/posts": POST_SERVICE_URL,
    "/api/reposts": POST_SERVICE_URL,
    "/api/hashtag": POST_SERVICE_URL,
    "/api/stories": os.environ.get("STORY_SERVICE_URL", "http://story-service:5005"),
    "/api/messages": os.environ.get("MESSAGING_SERVICE_URL", "http://messaging-service:5006"),
    "/api/conversations": os.environ.get("MESSAGING_SERVICE_URL", "http://messaging-service:5006"),
    "/api/feed": os.environ.get("FEED_SERVICE_URL", "http://feed-service:5007"),
    "/api/notifications": os.environ.get("NOTIFICATION_SERVICE_URL", "http://notification-service:5008"),
    "/api/media": os.environ.get("MEDIA_SERVICE_URL", "http://media-service:5009"),
}

# Engagement-service's routes are nested under /posts/<...>/react|comments,
# which collides with post-service's own /api/posts prefix above -- the two
# need to be told apart by suffix, not just prefix, so they're handled
# separately from the generic SERVICES table (see route_for_post_subpath).
ENGAGEMENT_SERVICE_URL = os.environ.get("ENGAGEMENT_SERVICE_URL", "http://engagement-service:5004")
ENGAGEMENT_SUFFIXES = ("/react", "/engagement", "/comments")


def route_for_post_subpath(full_path: str) -> str | None:
    if full_path.startswith("/api/posts/") and any(full_path.rstrip("/").endswith(s) or f"{s}/" in full_path for s in ENGAGEMENT_SUFFIXES):
        return ENGAGEMENT_SERVICE_URL
    return None

EXCLUDED_RESPONSE_HEADERS = {"content-encoding", "content-length", "transfer-encoding", "connection"}
EXCLUDED_REQUEST_HEADERS = {"host", "authorization", "content-length"}


def verify_jwt() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer "):]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("username")
    except jwt.PyJWTError:
        return None


@app.get("/api/health")
def health():
    return jsonify(status="ok", service="gateway")


@app.route("/api/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy(subpath):
    full_path = "/api/" + subpath

    target_base = route_for_post_subpath(full_path)
    matched_prefix = "/api/posts (engagement)" if target_base else ""
    if target_base is None:
        for prefix, base in SERVICES.items():
            if (full_path == prefix or full_path.startswith(prefix + "/")) and len(prefix) > len(matched_prefix):
                target_base, matched_prefix = base, prefix
    if target_base is None:
        return jsonify(error={"message": "Not found"}), 404

    # JWT verified once, here -- downstream services trust X-User-Username
    # instead of re-verifying the token (see services/*/app.py's use of the
    # header for the reasoning).
    username = verify_jwt()

    forward_headers = {k: v for k, v in request.headers.items() if k.lower() not in EXCLUDED_REQUEST_HEADERS}
    if username:
        forward_headers["X-User-Username"] = username

    # Confirmed live on this cluster: in-cluster DNS lookups intermittently
    # fail to resolve under load (a known glibc-resolver/CoreDNS race, not an
    # actual outage) -- every occurrence observed here succeeded on the very
    # next attempt, so a couple of quick retries on connection-level
    # failures only (not a real timeout, which already waited 20s) is the
    # standard mitigation.
    upstream = None
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            upstream = requests.request(
                method=request.method,
                url=target_base + full_path[len("/api"):],
                headers=forward_headers,
                params=request.args,
                data=request.get_data(),
                allow_redirects=False,
                timeout=20,
            )
            break
        except requests.exceptions.ConnectionError as e:
            print(f"[gateway] call to {target_base} failed (attempt {attempt}/{attempts}): {e}")
            if attempt < attempts:
                time.sleep(0.3)
        except requests.RequestException as e:
            print(f"[gateway] call to {target_base} failed: {e}")
            return jsonify(error={"message": f"{matched_prefix} is temporarily unavailable"}), 503
    if upstream is None:
        return jsonify(error={"message": f"{matched_prefix} is temporarily unavailable"}), 503

    response_headers = [(k, v) for k, v in upstream.headers.items() if k.lower() not in EXCLUDED_RESPONSE_HEADERS]
    return Response(upstream.content, upstream.status_code, response_headers)


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=debug_mode, threaded=True)
