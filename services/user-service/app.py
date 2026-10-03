import datetime
import os
import re

import jwt
from flask import Flask, jsonify, request
from flask_bcrypt import Bcrypt

from metrics import init_metrics
from models import BUSINESS_CATEGORIES, SessionLocal, User, init_db

PASSWORD_MIN_LENGTH = 10
_PASSWORD_SPECIAL_CHARS = r"""!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?"""


def password_policy_errors(password: str) -> list[str]:
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"be at least {PASSWORD_MIN_LENGTH} characters")
    if not re.search(r"[a-z]", password):
        errors.append("include a lowercase letter")
    if not re.search(r"[A-Z]", password):
        errors.append("include an uppercase letter")
    if not re.search(r"\d", password):
        errors.append("include a digit")
    if not re.search(f"[{re.escape(_PASSWORD_SPECIAL_CHARS)}]", password):
        errors.append("include a special character")
    return errors

app = Flask(__name__)
bcrypt = Bcrypt(app)
init_metrics(app)
init_db()

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-change-me")
JWT_ALGO = "HS256"


def sign_token(username: str) -> str:
    payload = {
        "username": username,
        "iat": datetime.datetime.utcnow(),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


@app.get("/health")
def health():
    return jsonify(status="ok", service="user-service")


@app.post("/auth/register")
def register():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    account_type = data.get("account_type") or "personal"
    if len(username) < 2 or len(username) > 20:
        return jsonify(error={"message": "Username must be 2-20 characters"}), 400
    policy_errors = password_policy_errors(password)
    if policy_errors:
        return jsonify(error={"message": "Password must " + ", ".join(policy_errors)}), 400
    if account_type not in ("personal", "business"):
        return jsonify(error={"message": "Invalid account type"}), 400
    business_category = (data.get("business_category") or "").strip()
    if account_type == "business" and business_category not in BUSINESS_CATEGORIES:
        return jsonify(error={"message": "Choose a business category"}), 400

    db = SessionLocal()
    try:
        if db.get(User, username) is not None:
            return jsonify(error={"message": "Username already taken"}), 409
        user = User(
            username=username,
            password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
            account_type=account_type,
            business_category=business_category if account_type == "business" else None,
            business_phone=(data.get("business_phone") or "").strip() or None if account_type == "business" else None,
            business_address=(data.get("business_address") or "").strip() or None if account_type == "business" else None,
        )
        db.add(user)
        db.commit()
        return jsonify(token=sign_token(username)), 201
    finally:
        db.close()


@app.post("/auth/login")
def login():
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username") or ""
    password = data.get("password") or ""

    db = SessionLocal()
    try:
        user = db.get(User, username)
        if user is None or not bcrypt.check_password_hash(user.password_hash, password):
            return jsonify(error={"message": "Invalid username or password"}), 401
        return jsonify(token=sign_token(username))
    finally:
        db.close()


@app.get("/users/<username>")
def get_user(username):
    db = SessionLocal()
    try:
        user = db.get(User, username)
        if user is None:
            return jsonify(error={"message": "User not found"}), 404
        return jsonify(user.to_public_dict())
    finally:
        db.close()


@app.put("/users/<username>")
def update_user(username):
    caller = request.headers.get("X-User-Username")
    if caller != username:
        return jsonify(error={"message": "Forbidden"}), 403

    data = request.get_json(force=True, silent=True) or {}
    editable = [
        "bio", "avatar_url", "cover_url", "work", "education", "current_city",
        "hometown", "relationship_status", "website",
        "business_category", "business_phone", "business_address",
    ]

    db = SessionLocal()
    try:
        user = db.get(User, username)
        if user is None:
            return jsonify(error={"message": "User not found"}), 404
        for field in editable:
            if field in data:
                setattr(user, field, data[field])
        db.commit()
        return jsonify(user.to_public_dict())
    finally:
        db.close()


@app.get("/internal/users")
def internal_batch_lookup():
    """Not exposed through the gateway -- used by other services to hydrate
    display data (avatar, bio) for usernames they only store as references."""
    usernames = [u for u in (request.args.get("usernames") or "").split(",") if u]
    if not usernames:
        return jsonify([])

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.username.in_(usernames)).all()
        return jsonify([u.to_public_dict() for u in users])
    finally:
        db.close()


@app.get("/internal/users/all")
def internal_all_usernames():
    """Backs /discover -- same unfiltered-scan limitation the original app
    documented; fine at this practice scale, not at real scale."""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        return jsonify([u.to_public_dict() for u in users])
    finally:
        db.close()


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=debug_mode, threaded=True)
