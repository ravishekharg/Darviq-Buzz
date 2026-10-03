import os

from flask import Flask, jsonify, request

from metrics import init_metrics
from models import Story, init_db

app = Flask(__name__)
init_metrics(app)
init_db()

STORY_TTL_SECONDS = 24 * 60 * 60


def current_username() -> str | None:
    return request.headers.get("X-User-Username")


def _serialize(story: Story) -> dict:
    return {
        "username": story.username,
        "created_at": story.created_at.isoformat(),
        "content": story.content,
        "image_url": story.image_url,
    }


@app.get("/health")
def health():
    return jsonify(status="ok", service="story-service")


@app.post("/stories")
def new_story():
    username = current_username()
    if not username:
        return jsonify(error={"message": "Authentication required"}), 401

    data = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip() or None
    image_url = data.get("image_url")
    if not content and not image_url:
        return jsonify(error={"message": "Add a photo or some text for your story"}), 400

    story = Story.objects.ttl(STORY_TTL_SECONDS).create(username=username, content=content, image_url=image_url)
    return jsonify(_serialize(story)), 201


@app.get("/stories/<username>")
def list_stories(username):
    stories = list(Story.objects(username=username).all())
    return jsonify([_serialize(s) for s in stories])


@app.get("/stories/feed")
def stories_feed():
    """Latest story + count per requested username, sorted newest-first --
    powers the home page's stories carousel across everyone the viewer
    follows plus themselves."""
    usernames = [u for u in (request.args.get("usernames") or "").split(",") if u]
    items = []
    for username in usernames:
        latest = Story.objects(username=username).first()  # clustering DESC -> newest first
        if latest is None:
            continue
        items.append({
            "username": username,
            "latest": _serialize(latest),
            "count": Story.objects(username=username).count(),
        })
    items.sort(key=lambda s: s["latest"]["created_at"], reverse=True)
    return jsonify(items)


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5005)), debug=debug_mode, threaded=True)
