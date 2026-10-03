import os

from flask import Flask, jsonify, request

from events import publish_event
from metrics import init_metrics
from models import Comment, Like, init_db
from ts_utils import id_to_ts

app = Flask(__name__)
init_metrics(app)
init_db()

REACTION_TYPES = {"like", "love", "haha", "wow", "sad", "angry"}


def current_username() -> str | None:
    return request.headers.get("X-User-Username")


@app.get("/health")
def health():
    return jsonify(status="ok", service="engagement-service")


@app.post("/posts/<username>/<ts>/react")
def react(username, ts):
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401

    date_posted = id_to_ts(ts)
    data = request.get_json(force=True, silent=True) or {}
    reaction_type = data.get("reaction_type", "like")
    if reaction_type not in REACTION_TYPES:
        reaction_type = "like"

    existing_qs = Like.objects(post_username=username, post_date_posted=date_posted, liker_username=me)
    existing = existing_qs.first()
    if existing is not None and (existing.reaction_type or "like") == reaction_type:
        existing_qs.delete()  # clicking the same reaction again toggles it off
        return jsonify(status="removed")
    if existing is not None:
        existing_qs.update(reaction_type=reaction_type)
        return jsonify(status="updated", reaction_type=reaction_type)

    Like.create(post_username=username, post_date_posted=date_posted, liker_username=me, reaction_type=reaction_type)
    publish_event("post.liked", {
        "post_username": username, "post_url_id": ts, "liker": me, "reaction_type": reaction_type,
    })
    return jsonify(status="added", reaction_type=reaction_type), 201


@app.get("/posts/<username>/<ts>/engagement")
def engagement(username, ts):
    date_posted = id_to_ts(ts)
    viewer = request.args.get("viewer") or current_username()

    reactions = list(Like.objects(post_username=username, post_date_posted=date_posted).all())
    counts: dict[str, int] = {}
    my_reaction = None
    for r in reactions:
        r_type = r.reaction_type or "like"
        counts[r_type] = counts.get(r_type, 0) + 1
        if viewer and r.liker_username == viewer:
            my_reaction = r_type

    top_types = sorted(counts, key=lambda t: counts[t], reverse=True)[:3]
    comment_count = Comment.objects(post_username=username, post_date_posted=date_posted).count()

    return jsonify(
        like_count=len(reactions),
        is_liked=my_reaction is not None,
        my_reaction=my_reaction,
        reaction_counts=counts,
        top_reaction_types=top_types,
        comment_count=comment_count,
    )


@app.post("/posts/<username>/<ts>/comments")
def add_comment(username, ts):
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401

    data = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content or len(content) > 500:
        return jsonify(error={"message": "Comment must be 1-500 characters"}), 400

    comment = Comment.create(
        post_username=username, post_date_posted=id_to_ts(ts), commenter_username=me, content=content,
    )
    publish_event("post.commented", {"post_username": username, "post_url_id": ts, "commenter": me})
    return jsonify(
        commenter_username=comment.commenter_username,
        content=comment.content,
        comment_date=comment.comment_date.isoformat(),
    ), 201


@app.get("/posts/<username>/<ts>/comments")
def list_comments(username, ts):
    comments = Comment.objects(post_username=username, post_date_posted=id_to_ts(ts)).all()
    return jsonify([
        {"commenter_username": c.commenter_username, "content": c.content, "comment_date": c.comment_date.isoformat()}
        for c in comments
    ])


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5004)), debug=debug_mode, threaded=True)
