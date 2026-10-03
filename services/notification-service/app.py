import os

from flask import Flask, jsonify, request

from consumer import is_connected, start_consumer_thread
from metrics import init_metrics
from models import Notification, SessionLocal, init_db

app = Flask(__name__)
init_metrics(app)
init_db()
start_consumer_thread()


def current_username() -> str | None:
    return request.headers.get("X-User-Username")


@app.get("/health")
def health():
    return jsonify(status="ok", service="notification-service")


@app.get("/ready")
def ready():
    if not is_connected():
        return jsonify(status="not ready"), 503
    return jsonify(status="ready")


@app.get("/notifications")
def list_notifications():
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401
    limit = request.args.get("limit", default=30, type=int)

    db = SessionLocal()
    try:
        rows = (
            db.query(Notification)
            .filter(Notification.recipient_username == me)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .all()
        )
        return jsonify([r.to_dict() for r in rows])
    finally:
        db.close()


@app.get("/notifications/unread-count")
def unread_count():
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401

    db = SessionLocal()
    try:
        count = (
            db.query(Notification)
            .filter(Notification.recipient_username == me, Notification.is_read.is_(False))
            .count()
        )
        return jsonify(count=count)
    finally:
        db.close()


@app.post("/notifications/<notification_id>/read")
def mark_read(notification_id):
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401

    db = SessionLocal()
    try:
        notif = db.get(Notification, notification_id)
        if notif is None or notif.recipient_username != me:
            return jsonify(error={"message": "Notification not found"}), 404
        notif.is_read = True
        db.commit()
        return jsonify(status="ok")
    finally:
        db.close()


@app.post("/notifications/read-all")
def mark_all_read():
    me = current_username()
    if not me:
        return jsonify(error={"message": "Authentication required"}), 401

    db = SessionLocal()
    try:
        db.query(Notification).filter(
            Notification.recipient_username == me, Notification.is_read.is_(False)
        ).update({"is_read": True})
        db.commit()
        return jsonify(status="ok")
    finally:
        db.close()


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5008)), debug=debug_mode, threaded=True)
