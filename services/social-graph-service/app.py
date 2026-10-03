import datetime
import os

from flask import Flask, jsonify, request

from events import publish_event
from metrics import init_metrics
from models import Followers, Following, FriendRequest, Friendship, IncomingFriendRequest, init_db

app = Flask(__name__)
init_metrics(app)
init_db()


def current_username() -> str | None:
    return request.headers.get("X-User-Username")


def require_user():
    username = current_username()
    if not username:
        return None, (jsonify(error={"message": "Authentication required"}), 401)
    return username, None


# -------------------------------------------------------------------------
# FOLLOW GRAPH
# -------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify(status="ok", service="social-graph-service")


@app.post("/follow/<username>")
def follow(username):
    me, err = require_user()
    if err:
        return err
    if me == username:
        return jsonify(error={"message": "Cannot follow yourself"}), 400

    Following.create(follower_username=me, followed_username=username)
    Followers.create(followed_username=username, follower_username=me)
    publish_event("user.followed", {"follower": me, "followed": username})
    return jsonify(status="followed"), 201


@app.delete("/follow/<username>")
def unfollow(username):
    me, err = require_user()
    if err:
        return err
    Following.objects(follower_username=me, followed_username=username).delete()
    Followers.objects(followed_username=username, follower_username=me).delete()
    return jsonify(status="unfollowed")


@app.get("/follow/<username>/followers")
def list_followers(username):
    rows = Followers.objects(followed_username=username).all()
    usernames = [r.follower_username for r in rows]
    return jsonify(count=len(usernames), usernames=usernames)


@app.get("/follow/<username>/following")
def list_following(username):
    rows = Following.objects(follower_username=username).all()
    usernames = [r.followed_username for r in rows]
    return jsonify(count=len(usernames), usernames=usernames)


@app.get("/follow/<username>/is-following")
def is_following_check(username):
    viewer = request.args.get("viewer") or current_username()
    if not viewer:
        return jsonify(is_following=False)
    following = Following.objects(follower_username=viewer, followed_username=username).count() > 0
    return jsonify(is_following=following)


# -------------------------------------------------------------------------
# FRIEND GRAPH
# -------------------------------------------------------------------------

def _friendship_status(me: str, other: str) -> str:
    if me == other:
        return "self"
    if Friendship.objects(username=me, friend_username=other).count() > 0:
        return "friends"
    if FriendRequest.objects(sender_username=me, receiver_username=other).count() > 0:
        return "request_sent"
    if IncomingFriendRequest.objects(receiver_username=me, sender_username=other).count() > 0:
        return "request_received"
    return "none"


def _accept_friend_request(sender: str, receiver: str) -> None:
    FriendRequest.objects(sender_username=sender, receiver_username=receiver).delete()
    IncomingFriendRequest.objects(receiver_username=receiver, sender_username=sender).delete()
    now = datetime.datetime.utcnow()
    Friendship.create(username=sender, friend_username=receiver, friends_since=now)
    Friendship.create(username=receiver, friend_username=sender, friends_since=now)
    # Becoming friends also follows each other both ways, matching how
    # Facebook's friend graph feeds the News Feed -- see the original
    # app.py's _accept_friend_request for the same reasoning.
    Following.create(follower_username=sender, followed_username=receiver)
    Followers.create(followed_username=receiver, follower_username=sender)
    Following.create(follower_username=receiver, followed_username=sender)
    Followers.create(followed_username=sender, follower_username=receiver)
    publish_event("friend.request_accepted", {"sender": sender, "receiver": receiver})


@app.post("/friends/<username>/request")
def send_friend_request(username):
    me, err = require_user()
    if err:
        return err
    if me == username:
        return jsonify(error={"message": "Cannot friend-request yourself"}), 400

    status = _friendship_status(me, username)
    if status == "request_received":
        _accept_friend_request(sender=username, receiver=me)
        return jsonify(status="friends")
    if status == "none":
        FriendRequest.create(sender_username=me, receiver_username=username)
        IncomingFriendRequest.create(receiver_username=username, sender_username=me)
        publish_event("friend.request_sent", {"sender": me, "receiver": username})
        return jsonify(status="request_sent"), 201
    return jsonify(status=status)


@app.post("/friends/<username>/accept")
def accept_friend_request(username):
    me, err = require_user()
    if err:
        return err
    if IncomingFriendRequest.objects(receiver_username=me, sender_username=username).count() == 0:
        return jsonify(error={"message": "No such friend request"}), 404
    _accept_friend_request(sender=username, receiver=me)
    return jsonify(status="friends")


@app.post("/friends/<username>/decline")
def decline_friend_request(username):
    me, err = require_user()
    if err:
        return err
    FriendRequest.objects(sender_username=username, receiver_username=me).delete()
    IncomingFriendRequest.objects(receiver_username=me, sender_username=username).delete()
    return jsonify(status="declined")


@app.post("/friends/<username>/cancel")
def cancel_friend_request(username):
    me, err = require_user()
    if err:
        return err
    FriendRequest.objects(sender_username=me, receiver_username=username).delete()
    IncomingFriendRequest.objects(receiver_username=username, sender_username=me).delete()
    return jsonify(status="canceled")


@app.delete("/friends/<username>")
def unfriend(username):
    me, err = require_user()
    if err:
        return err
    Friendship.objects(username=me, friend_username=username).delete()
    Friendship.objects(username=username, friend_username=me).delete()
    return jsonify(status="unfriended")


@app.get("/friends/<username>")
def friends_of(username):
    limit = request.args.get("limit", type=int)
    usernames = [f.friend_username for f in Friendship.objects(username=username).all()]
    if limit is not None:
        usernames = usernames[:limit]
    return jsonify(count=Friendship.objects(username=username).count(), usernames=usernames)


@app.get("/friends/<username>/status")
def friendship_status_endpoint(username):
    me = request.args.get("viewer") or current_username()
    if not me:
        return jsonify(status="none")
    return jsonify(status=_friendship_status(me, username))


@app.get("/friend-requests")
def friend_requests():
    me, err = require_user()
    if err:
        return err
    incoming = [r.sender_username for r in IncomingFriendRequest.objects(receiver_username=me).all()]
    outgoing = [r.receiver_username for r in FriendRequest.objects(sender_username=me).all()]
    return jsonify(incoming=incoming, outgoing=outgoing)


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5002)), debug=debug_mode, threaded=True)
