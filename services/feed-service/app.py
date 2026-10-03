import os

from flask import Flask, jsonify, request

from consumer import is_connected, start_consumer_thread
from metrics import init_metrics
from models import Timeline, init_db

app = Flask(__name__)
init_metrics(app)
init_db()
start_consumer_thread()


@app.get("/health")
def health():
    return jsonify(status="ok", service="feed-service")


@app.get("/ready")
def ready():
    if not is_connected():
        return jsonify(status="not ready"), 503
    return jsonify(status="ready")


@app.get("/feed/<username>")
def get_feed(username):
    limit = request.args.get("limit", default=50, type=int)
    entries = Timeline.objects(username=username).limit(limit).all()
    return jsonify([
        {
            "entry_type": e.entry_type,
            "ref_username": e.ref_username,
            "ref_url_id": e.ref_url_id,
            "reposted_by": e.reposted_by,
            "repost_comment": e.repost_comment,
            "sort_key": e.sort_key.isoformat(),
        }
        for e in entries
    ])


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5007)), debug=debug_mode, threaded=True)
