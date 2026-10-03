import datetime
import os

from flask import Flask, jsonify, request

from metrics import init_metrics
from models import ConversationIndex, Message, conversation_id_for, init_db
from ts_utils import id_to_ts, ts_to_id

app = Flask(__name__)
init_metrics(app)
init_db()


def current_username() -> str | None:
    return request.headers.get("X-User-Username")


def _serialize(m: Message) -> dict:
    return {
        "sender": m.sender_username,
        "content": m.content,
        "sent_at": m.sent_at.strftime("%Y-%m-%d %H:%M"),
        "sent_at_id": ts_to_id(m.sent_at),
    }


def _upsert_conversation_index(username: str, other_username: str, sent_at, preview: str) -> None:
    existing = ConversationIndex.objects(username=username, other_username=other_username)
    if existing.count() > 0:
        existing.update(last_message_at=sent_at, last_message_preview=preview)
    else:
        ConversationIndex.create(
            username=username, other_username=other_username,
            last_message_at=sent_at, last_message_preview=preview,
        )


@app.get("/health")
def health():
    return jsonify(status="ok", service="messaging-service")


@app.get("/conversations")
def conversations():
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401
    rows = sorted(ConversationIndex.objects(username=me).all(), key=lambda c: c.last_message_at, reverse=True)
    return jsonify([
        {"other_username": r.other_username, "last_message_at": r.last_message_at.isoformat(),
         "last_message_preview": r.last_message_preview}
        for r in rows
    ])


@app.post("/messages/<other_username>")
def send_message(other_username):
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401
    if me == other_username:
        return jsonify(error={"message": "Cannot message yourself"}), 400

    data = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content or len(content) > 1000:
        return jsonify(error={"message": "Message must be 1-1000 characters"}), 400

    cid = conversation_id_for(me, other_username)
    sent_at = datetime.datetime.utcnow()
    Message.create(conversation_id=cid, sent_at=sent_at, sender_username=me, content=content)

    preview = content[:80]
    _upsert_conversation_index(me, other_username, sent_at, preview)
    _upsert_conversation_index(other_username, me, sent_at, preview)
    return jsonify(status="sent"), 201


@app.get("/messages/<other_username>")
def message_history(other_username):
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401
    cid = conversation_id_for(me, other_username)
    history = [_serialize(m) for m in Message.objects(conversation_id=cid).all()]
    return jsonify(history)


@app.get("/messages/<other_username>/poll")
def poll(other_username):
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401
    cid = conversation_id_for(me, other_username)
    query = Message.objects(conversation_id=cid)
    since_raw = request.args.get("since")
    if since_raw:
        query = query.filter(sent_at__gt=id_to_ts(since_raw))
    return jsonify([_serialize(m) for m in query.all()])


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5006)), debug=debug_mode, threaded=True)
