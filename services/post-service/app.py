import os

from flask import Flask, jsonify, request

from events import publish_event
from metrics import init_metrics
from models import Hashtag, Post, Repost, init_db
from text_utils import extract_hashtags
from ts_utils import id_to_ts, ts_to_id

app = Flask(__name__)
init_metrics(app)
init_db()


def current_username() -> str | None:
    return request.headers.get("X-User-Username")


def _serialize_post(post: Post) -> dict:
    return {
        "username": post.username,
        "date_posted": post.date_posted.isoformat(),
        "url_id": ts_to_id(post.date_posted),
        "content": post.content,
        "image_url": post.image_url,
    }


@app.get("/health")
def health():
    return jsonify(status="ok", service="post-service")


@app.post("/posts")
def create_post():
    username = current_username()
    if not username:
        return jsonify(error={"message": "Authentication required"}), 401

    data = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content or len(content) > 2000:
        return jsonify(error={"message": "Content must be 1-2000 characters"}), 400

    post = Post.create(username=username, content=content, image_url=data.get("image_url"))
    for tag in extract_hashtags(content):
        Hashtag.create(tag=tag, date_posted=post.date_posted, post_username=post.username)

    publish_event("post.created", {"username": post.username, "url_id": ts_to_id(post.date_posted)})
    return jsonify(_serialize_post(post)), 201


@app.get("/posts/<username>")
def list_posts(username):
    posts = Post.objects(username=username).all()
    return jsonify([_serialize_post(p) for p in posts])


@app.get("/posts/<username>/<ts>")
def get_post(username, ts):
    post = Post.objects(username=username, date_posted=id_to_ts(ts)).first()
    if post is None:
        return jsonify(error={"message": "Post not found"}), 404
    return jsonify(_serialize_post(post))


@app.post("/posts/<username>/<ts>/repost")
def create_repost(username, ts):
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401

    date_posted = id_to_ts(ts)
    original = Post.objects(username=username, date_posted=date_posted).first()
    if original is None:
        return jsonify(error={"message": "Original post not found"}), 404

    data = request.get_json(force=True, silent=True) or {}
    repost = Repost.create(
        reposter_username=me, original_username=username,
        original_date_posted=date_posted, comment=(data.get("comment") or None),
    )
    publish_event("post.reposted", {
        "reposter": me, "original_username": username, "original_url_id": ts,
        "comment": repost.comment,
    })
    return jsonify(
        reposter_username=repost.reposter_username,
        repost_date=repost.repost_date.isoformat(),
        original_username=original.username,
        original_url_id=ts,
        comment=repost.comment,
    ), 201


@app.get("/reposts/<username>")
def list_reposts(username):
    reposts = Repost.objects(reposter_username=username).all()
    result = []
    for r in reposts:
        original = Post.objects(username=r.original_username, date_posted=r.original_date_posted).first()
        if original is None:
            continue  # original post was deleted after the repost was made
        result.append({
            "reposter_username": r.reposter_username,
            "repost_date": r.repost_date.isoformat(),
            "comment": r.comment,
            "original": _serialize_post(original),
        })
    return jsonify(result)


@app.get("/hashtag/<tag>")
def posts_by_hashtag(tag):
    rows = Hashtag.objects(tag=tag.lower()).all()
    result = []
    for row in rows:
        post = Post.objects(username=row.post_username, date_posted=row.date_posted).first()
        if post is not None:
            result.append(_serialize_post(post))
    return jsonify(result)


@app.get("/internal/posts")
def internal_batch_lookup():
    """refs is a comma-separated list of 'username:url_id' pairs -- used by
    feed-service (and web-bff) to hydrate a batch of timeline entries
    without one HTTP round trip per post."""
    refs = [r for r in (request.args.get("refs") or "").split(",") if r]
    result = []
    for ref in refs:
        try:
            username, url_id = ref.split(":", 1)
        except ValueError:
            continue
        post = Post.objects(username=username, date_posted=id_to_ts(url_id)).first()
        if post is not None:
            result.append(_serialize_post(post))
    return jsonify(result)


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5003)), debug=debug_mode, threaded=True)
