"""HTTP clients for every backend service, called directly (not through the
gateway) -- web-bff is a trusted internal caller.
web-bff asserts X-User-Username itself once a browser session is
authenticated, rather than round-tripping a JWT through the session cookie.
"""
import os
import time

import requests

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://user-service:5001")
SOCIAL_GRAPH_SERVICE_URL = os.environ.get("SOCIAL_GRAPH_SERVICE_URL", "http://social-graph-service:5002")
POST_SERVICE_URL = os.environ.get("POST_SERVICE_URL", "http://post-service:5003")
ENGAGEMENT_SERVICE_URL = os.environ.get("ENGAGEMENT_SERVICE_URL", "http://engagement-service:5004")
STORY_SERVICE_URL = os.environ.get("STORY_SERVICE_URL", "http://story-service:5005")
MESSAGING_SERVICE_URL = os.environ.get("MESSAGING_SERVICE_URL", "http://messaging-service:5006")
FEED_SERVICE_URL = os.environ.get("FEED_SERVICE_URL", "http://feed-service:5007")
NOTIFICATION_SERVICE_URL = os.environ.get("NOTIFICATION_SERVICE_URL", "http://notification-service:5008")
MEDIA_SERVICE_URL = os.environ.get("MEDIA_SERVICE_URL", "http://media-service:5009")

# 5s was too tight for this environment: a direct measurement during
# diagnosis showed pod-to-pod exec round-trips taking up to 22s under this
# node's disk/CPU contention, so a plain HTTP call between services can
# plausibly exceed 5s too, surfacing as a spurious "service unavailable"
# even though the target is healthy.
TIMEOUT = 20


def _headers(as_user: str | None) -> dict:
    return {"X-User-Username": as_user} if as_user else {}


def _req(method: str, url: str, as_user: str | None = None, **kwargs):
    # Confirmed live on this cluster: in-cluster DNS lookups (e.g.
    # "user-service") intermittently fail to resolve under load -- a known
    # glibc-resolver/CoreDNS race (concurrent A/AAAA queries), not an actual
    # outage. Every occurrence observed here succeeded on the very next
    # attempt, so a couple of quick retries on connection-level failures
    # (not on a real timeout, which already waited TIMEOUT seconds) is the
    # standard, Kubernetes-docs-recommended mitigation.
    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            return requests.request(method, url, headers=_headers(as_user), timeout=TIMEOUT, **kwargs)
        except requests.exceptions.ConnectionError as e:
            print(f"[web-bff] call to {url} failed (attempt {attempt}/{attempts}): {e}")
            if attempt < attempts:
                time.sleep(0.3)
        except requests.RequestException as e:
            print(f"[web-bff] call to {url} failed: {e}")
            return None
    return None


# -------------------------------------------------------------------------
# user-service
# -------------------------------------------------------------------------

def register(username: str, password: str, **extra):
    payload = {"username": username, "password": password, **extra}
    return _req("POST", f"{USER_SERVICE_URL}/auth/register", json=payload)


def login(username: str, password: str):
    return _req("POST", f"{USER_SERVICE_URL}/auth/login", json={"username": username, "password": password})


def get_user(username: str) -> dict | None:
    resp = _req("GET", f"{USER_SERVICE_URL}/users/{username}")
    return resp.json() if resp is not None and resp.status_code == 200 else None


def update_user(username: str, data: dict) -> dict | None:
    resp = _req("PUT", f"{USER_SERVICE_URL}/users/{username}", as_user=username, json=data)
    return resp.json() if resp is not None and resp.status_code == 200 else None


def batch_users(usernames: list[str]) -> dict[str, dict]:
    if not usernames:
        return {}
    resp = _req("GET", f"{USER_SERVICE_URL}/internal/users", params={"usernames": ",".join(usernames)})
    if resp is None or resp.status_code != 200:
        return {}
    return {u["username"]: u for u in resp.json()}


def all_users() -> list[dict]:
    resp = _req("GET", f"{USER_SERVICE_URL}/internal/users/all")
    return resp.json() if resp is not None and resp.status_code == 200 else []


# -------------------------------------------------------------------------
# social-graph-service
# -------------------------------------------------------------------------

def follow(me: str, username: str):
    return _req("POST", f"{SOCIAL_GRAPH_SERVICE_URL}/follow/{username}", as_user=me)


def unfollow(me: str, username: str):
    return _req("DELETE", f"{SOCIAL_GRAPH_SERVICE_URL}/follow/{username}", as_user=me)


def followers_of(username: str) -> list[str]:
    resp = _req("GET", f"{SOCIAL_GRAPH_SERVICE_URL}/follow/{username}/followers")
    return resp.json().get("usernames", []) if resp is not None and resp.status_code == 200 else []


def following_of(username: str) -> list[str]:
    resp = _req("GET", f"{SOCIAL_GRAPH_SERVICE_URL}/follow/{username}/following")
    return resp.json().get("usernames", []) if resp is not None and resp.status_code == 200 else []


def is_following(viewer: str, username: str) -> bool:
    resp = _req("GET", f"{SOCIAL_GRAPH_SERVICE_URL}/follow/{username}/is-following", params={"viewer": viewer})
    return resp.json().get("is_following", False) if resp is not None and resp.status_code == 200 else False


def send_friend_request(me: str, username: str):
    return _req("POST", f"{SOCIAL_GRAPH_SERVICE_URL}/friends/{username}/request", as_user=me)


def accept_friend_request(me: str, username: str):
    return _req("POST", f"{SOCIAL_GRAPH_SERVICE_URL}/friends/{username}/accept", as_user=me)


def decline_friend_request(me: str, username: str):
    return _req("POST", f"{SOCIAL_GRAPH_SERVICE_URL}/friends/{username}/decline", as_user=me)


def cancel_friend_request(me: str, username: str):
    return _req("POST", f"{SOCIAL_GRAPH_SERVICE_URL}/friends/{username}/cancel", as_user=me)


def unfriend(me: str, username: str):
    return _req("DELETE", f"{SOCIAL_GRAPH_SERVICE_URL}/friends/{username}", as_user=me)


def friends_of(username: str, limit: int | None = None) -> dict:
    params = {"limit": limit} if limit else {}
    resp = _req("GET", f"{SOCIAL_GRAPH_SERVICE_URL}/friends/{username}", params=params)
    return resp.json() if resp is not None and resp.status_code == 200 else {"count": 0, "usernames": []}


def friendship_status(viewer: str, username: str) -> str:
    resp = _req("GET", f"{SOCIAL_GRAPH_SERVICE_URL}/friends/{username}/status", params={"viewer": viewer})
    return resp.json().get("status", "none") if resp is not None and resp.status_code == 200 else "none"


def friend_requests(me: str) -> dict:
    resp = _req("GET", f"{SOCIAL_GRAPH_SERVICE_URL}/friend-requests", as_user=me)
    return resp.json() if resp is not None and resp.status_code == 200 else {"incoming": [], "outgoing": []}


# -------------------------------------------------------------------------
# post-service
# -------------------------------------------------------------------------

def create_post(me: str, content: str, image_url: str | None) -> dict | None:
    resp = _req("POST", f"{POST_SERVICE_URL}/posts", as_user=me, json={"content": content, "image_url": image_url})
    return resp.json() if resp is not None and resp.status_code == 201 else None


def get_post(username: str, ts: str) -> dict | None:
    resp = _req("GET", f"{POST_SERVICE_URL}/posts/{username}/{ts}")
    return resp.json() if resp is not None and resp.status_code == 200 else None


def posts_by_user(username: str) -> list[dict]:
    resp = _req("GET", f"{POST_SERVICE_URL}/posts/{username}")
    return resp.json() if resp is not None and resp.status_code == 200 else []


def batch_posts(refs: list[str]) -> dict[str, dict]:
    """refs: list of 'username:url_id' strings. Returns keyed by the same."""
    if not refs:
        return {}
    resp = _req("GET", f"{POST_SERVICE_URL}/internal/posts", params={"refs": ",".join(refs)})
    if resp is None or resp.status_code != 200:
        return {}
    return {f"{p['username']}:{p['url_id']}": p for p in resp.json()}


def create_repost(me: str, username: str, ts: str, comment: str | None) -> dict | None:
    resp = _req("POST", f"{POST_SERVICE_URL}/posts/{username}/{ts}/repost", as_user=me, json={"comment": comment})
    return resp.json() if resp is not None and resp.status_code == 201 else None


def reposts_by_user(username: str) -> list[dict]:
    resp = _req("GET", f"{POST_SERVICE_URL}/reposts/{username}")
    return resp.json() if resp is not None and resp.status_code == 200 else []


def posts_by_hashtag(tag: str) -> list[dict]:
    resp = _req("GET", f"{POST_SERVICE_URL}/hashtag/{tag}")
    return resp.json() if resp is not None and resp.status_code == 200 else []


# -------------------------------------------------------------------------
# engagement-service
# -------------------------------------------------------------------------

def react(me: str, username: str, ts: str, reaction_type: str):
    return _req("POST", f"{ENGAGEMENT_SERVICE_URL}/posts/{username}/{ts}/react", as_user=me, json={"reaction_type": reaction_type})


def engagement(username: str, ts: str, viewer: str | None) -> dict:
    params = {"viewer": viewer} if viewer else {}
    resp = _req("GET", f"{ENGAGEMENT_SERVICE_URL}/posts/{username}/{ts}/engagement", params=params)
    if resp is not None and resp.status_code == 200:
        return resp.json()
    return {"like_count": 0, "is_liked": False, "my_reaction": None, "reaction_counts": {}, "top_reaction_types": [], "comment_count": 0}


def add_comment(me: str, username: str, ts: str, content: str):
    return _req("POST", f"{ENGAGEMENT_SERVICE_URL}/posts/{username}/{ts}/comments", as_user=me, json={"content": content})


def list_comments(username: str, ts: str) -> list[dict]:
    resp = _req("GET", f"{ENGAGEMENT_SERVICE_URL}/posts/{username}/{ts}/comments")
    return resp.json() if resp is not None and resp.status_code == 200 else []


# -------------------------------------------------------------------------
# story-service
# -------------------------------------------------------------------------

def create_story(me: str, content: str | None, image_url: str | None):
    return _req("POST", f"{STORY_SERVICE_URL}/stories", as_user=me, json={"content": content, "image_url": image_url})


def stories_of(username: str) -> list[dict]:
    resp = _req("GET", f"{STORY_SERVICE_URL}/stories/{username}")
    return resp.json() if resp is not None and resp.status_code == 200 else []


def stories_feed(usernames: list[str]) -> list[dict]:
    if not usernames:
        return []
    resp = _req("GET", f"{STORY_SERVICE_URL}/stories/feed", params={"usernames": ",".join(usernames)})
    return resp.json() if resp is not None and resp.status_code == 200 else []


# -------------------------------------------------------------------------
# messaging-service
# -------------------------------------------------------------------------

def conversations(me: str) -> list[dict]:
    resp = _req("GET", f"{MESSAGING_SERVICE_URL}/conversations", as_user=me)
    return resp.json() if resp is not None and resp.status_code == 200 else []


def send_message(me: str, other_username: str, content: str):
    return _req("POST", f"{MESSAGING_SERVICE_URL}/messages/{other_username}", as_user=me, json={"content": content})


def message_history(me: str, other_username: str) -> list[dict]:
    resp = _req("GET", f"{MESSAGING_SERVICE_URL}/messages/{other_username}", as_user=me)
    return resp.json() if resp is not None and resp.status_code == 200 else []


def poll_messages(me: str, other_username: str, since: str | None) -> list[dict]:
    params = {"since": since} if since else {}
    resp = _req("GET", f"{MESSAGING_SERVICE_URL}/messages/{other_username}/poll", as_user=me, params=params)
    return resp.json() if resp is not None and resp.status_code == 200 else []


# -------------------------------------------------------------------------
# feed-service
# -------------------------------------------------------------------------

def get_feed(username: str, limit: int = 50) -> list[dict]:
    resp = _req("GET", f"{FEED_SERVICE_URL}/feed/{username}", params={"limit": limit})
    return resp.json() if resp is not None and resp.status_code == 200 else []


# -------------------------------------------------------------------------
# notification-service
# -------------------------------------------------------------------------

def list_notifications(me: str, limit: int = 30) -> list[dict]:
    resp = _req("GET", f"{NOTIFICATION_SERVICE_URL}/notifications", as_user=me, params={"limit": limit})
    return resp.json() if resp is not None and resp.status_code == 200 else []


def unread_notification_count(me: str) -> int:
    resp = _req("GET", f"{NOTIFICATION_SERVICE_URL}/notifications/unread-count", as_user=me)
    return resp.json().get("count", 0) if resp is not None and resp.status_code == 200 else 0


def mark_all_notifications_read(me: str):
    return _req("POST", f"{NOTIFICATION_SERVICE_URL}/notifications/read-all", as_user=me)


# -------------------------------------------------------------------------
# media-service
# -------------------------------------------------------------------------

def upload_media(me: str, file_storage) -> dict | None:
    """file_storage is a werkzeug FileStorage from request.files."""
    files = {"file": (file_storage.filename, file_storage.stream, file_storage.mimetype)}
    resp = _req("POST", f"{MEDIA_SERVICE_URL}/media/upload", as_user=me, files=files)
    return resp.json() if resp is not None and resp.status_code == 201 else None
