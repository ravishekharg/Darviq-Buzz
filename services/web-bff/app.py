import os
from functools import wraps

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_wtf import CSRFProtect

import services as svc
from forms import CommentForm, EditProfileForm, LoginForm, MessageForm, PostForm, RegistrationForm, RepostForm
from metrics import init_metrics
from text_utils import linkify
from view_helpers import build_feed_display, build_post_display, build_posts_display, build_reposts_display

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_fallback_secret_key_12345")
csrf = CSRFProtect(app)
init_metrics(app)

app.jinja_env.filters["linkify"] = linkify

REACTION_TYPES = {
    "like": "\U0001F44D", "love": "❤️", "haha": "\U0001F606",
    "wow": "\U0001F62E", "sad": "\U0001F622", "angry": "\U0001F621",
}
EMOJI_PALETTE = [
    "\U0001F600", "\U0001F602", "\U0001F60D", "\U0001F60E", "\U0001F914", "\U0001F622", "\U0001F621",
    "\U0001F44D", "\U0001F44F", "\U0001F64F", "\U0001F525", "\U0001F389", "❤️", "\U0001F4AF",
]


def current_username() -> str | None:
    return session.get("username")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_username():
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)

    return wrapper


@app.context_processor
def inject_globals():
    me = current_username()
    ctx = {"reaction_types": REACTION_TYPES, "emoji_palette": EMOJI_PALETTE, "current_username": me}
    if not me:
        return ctx
    following = set(svc.following_of(me))
    ctx["sidebar_suggestions"] = [u for u in svc.all_users() if u["username"] != me and u["username"] not in following][:5]
    ctx["incoming_request_count"] = len(svc.friend_requests(me).get("incoming", []))
    ctx["unread_notification_count"] = svc.unread_notification_count(me)
    return ctx


def _maybe_upload(me: str, file_storage) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    result = svc.upload_media(me, file_storage)
    if result is None:
        flash("Image upload failed -- posted without it.", "warning")
        return None
    return result["url"]


# -------------------------------------------------------------------------
# HEALTH / METRICS (init_metrics adds /metrics)
# -------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify(status="ok", service="web-bff")


# -------------------------------------------------------------------------
# AUTH
# -------------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_username():
        return redirect(url_for("home"))
    form = RegistrationForm()
    if form.validate_on_submit():
        resp = svc.register(
            form.username.data, form.password.data,
            account_type=form.account_type.data,
            business_category=form.business_category.data,
            business_phone=form.business_phone.data,
            business_address=form.business_address.data,
        )
        if resp is not None and resp.status_code == 201:
            flash("Your account has been created! You are now able to log in", "success")
            return redirect(url_for("login"))
        message = resp.json().get("error", {}).get("message", "Registration failed") if resp is not None else "user-service is unavailable"
        flash(message, "danger")
    return render_template("register.html", title="Register", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_username():
        return redirect(url_for("home"))
    form = LoginForm()
    if form.validate_on_submit():
        resp = svc.login(form.username.data, form.password.data)
        if resp is not None and resp.status_code == 200:
            session["username"] = form.username.data
            if form.remember.data:
                session.permanent = True
            next_page = request.args.get("next")
            return redirect(next_page) if next_page else redirect(url_for("home"))
        flash("Login unsuccessful. Please check username and password", "danger")
    return render_template("login.html", title="Login", form=form)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# -------------------------------------------------------------------------
# HOME FEED
# -------------------------------------------------------------------------

@app.route("/")
@app.route("/home")
@login_required
def home():
    me = current_username()
    following = svc.following_of(me)
    raw_feed = svc.get_feed(me)
    feed = build_feed_display(raw_feed, me)
    stories = svc.stories_feed([me] + following)
    form = PostForm()
    return render_template("index.html", feed=feed, form=form, has_follows=bool(following), stories=stories)


@app.post("/post/new")
@login_required
def new_post():
    me = current_username()
    form = PostForm()
    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for error in field_errors:
                flash(error, "danger")
        return redirect(url_for("home"))

    image_url = _maybe_upload(me, form.photo.data)
    post = svc.create_post(me, form.content.data, image_url)
    if post is None:
        flash("Failed to create post.", "danger")
    else:
        flash("Posted!", "success")
    return redirect(url_for("home"))


# -------------------------------------------------------------------------
# DISCOVER
# -------------------------------------------------------------------------

@app.get("/discover")
@login_required
def discover():
    me = current_username()
    account_type_filter = request.args.get("type", "all")
    users = [u for u in svc.all_users() if u["username"] != me]
    if account_type_filter in ("personal", "business"):
        users = [u for u in users if u.get("account_type", "personal") == account_type_filter]
    following_set = set(svc.following_of(me))
    friendship_statuses = {u["username"]: svc.friendship_status(me, u["username"]) for u in users}
    return render_template(
        "discover.html", users=users, following_set=following_set,
        friendship_statuses=friendship_statuses, account_type_filter=account_type_filter,
    )


# -------------------------------------------------------------------------
# PROFILES & FOLLOW GRAPH
# -------------------------------------------------------------------------

@app.get("/user/<username>")
@login_required
def profile(username):
    me = current_username()
    user = svc.get_user(username)
    if user is None:
        flash(f"No such user: {username}", "warning")
        return redirect(url_for("home"))

    posts = svc.posts_by_user(username)
    feed = build_posts_display(posts, me)
    friends_preview = svc.friends_of(username, limit=9)
    hydrated_friends = svc.batch_users(friends_preview["usernames"]).values()

    return render_template(
        "profile.html",
        profile_user=user,
        feed=feed,
        follower_count=len(svc.followers_of(username)),
        following_count=len(svc.following_of(username)),
        friend_count=friends_preview["count"],
        friends_preview=list(hydrated_friends),
        friendship_status=svc.friendship_status(me, username),
        is_following=svc.is_following(me, username),
        is_self=(me == username),
    )


@app.get("/user/<username>/friends")
@login_required
def friends_list(username):
    user = svc.get_user(username)
    if user is None:
        flash(f"No such user: {username}", "warning")
        return redirect(url_for("home"))
    friends = svc.friends_of(username)
    hydrated = list(svc.batch_users(friends["usernames"]).values())
    return render_template("friends_list.html", profile_user=user, friends=hydrated, is_self=(current_username() == username))


@app.post("/user/<username>/friend-request")
@login_required
def send_friend_request(username):
    me = current_username()
    if username == me or svc.get_user(username) is None:
        return redirect(request.referrer or url_for("home"))
    resp = svc.send_friend_request(me, username)
    if resp is not None and resp.status_code == 200 and resp.json().get("status") == "friends":
        flash(f"You are now friends with @{username}!", "success")
    elif resp is not None and resp.status_code == 201:
        flash(f"Friend request sent to @{username}.", "success")
    return redirect(request.referrer or url_for("profile", username=username))


@app.post("/friend-requests/<username>/accept")
@login_required
def accept_friend_request(username):
    me = current_username()
    resp = svc.accept_friend_request(me, username)
    if resp is not None and resp.status_code == 200:
        flash(f"You are now friends with @{username}!", "success")
    else:
        flash("No such friend request.", "warning")
    return redirect(request.referrer or url_for("friend_requests_page"))


@app.post("/friend-requests/<username>/decline")
@login_required
def decline_friend_request(username):
    svc.decline_friend_request(current_username(), username)
    flash("Friend request declined.", "info")
    return redirect(request.referrer or url_for("friend_requests_page"))


@app.post("/friend-requests/<username>/cancel")
@login_required
def cancel_friend_request(username):
    svc.cancel_friend_request(current_username(), username)
    flash("Friend request canceled.", "info")
    return redirect(request.referrer or url_for("profile", username=username))


@app.post("/user/<username>/unfriend")
@login_required
def unfriend(username):
    svc.unfriend(current_username(), username)
    flash(f"Removed @{username} from your friends.", "info")
    return redirect(request.referrer or url_for("profile", username=username))


@app.get("/friend-requests")
@login_required
def friend_requests_page():
    me = current_username()
    raw = svc.friend_requests(me)
    users = svc.batch_users(raw["incoming"] + raw["outgoing"])
    incoming = [users.get(u, {"username": u}) for u in raw["incoming"]]
    outgoing = [users.get(u, {"username": u}) for u in raw["outgoing"]]
    return render_template("friend_requests.html", incoming=incoming, outgoing=outgoing)


@app.post("/user/<username>/follow")
@login_required
def follow(username):
    me = current_username()
    if username != me and svc.get_user(username) is not None:
        svc.follow(me, username)
    return redirect(url_for("profile", username=username))


@app.post("/user/<username>/unfollow")
@login_required
def unfollow_route(username):
    svc.unfollow(current_username(), username)
    return redirect(request.referrer or url_for("profile", username=username))


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    me = current_username()
    user = svc.get_user(me)
    form = EditProfileForm()
    if form.validate_on_submit():
        svc.update_user(me, {
            "bio": form.bio.data, "avatar_url": form.avatar_url.data, "cover_url": form.cover_url.data,
            "work": form.work.data, "education": form.education.data, "current_city": form.current_city.data,
            "hometown": form.hometown.data, "relationship_status": form.relationship_status.data,
            "website": form.website.data, "business_category": form.business_category.data,
            "business_phone": form.business_phone.data, "business_address": form.business_address.data,
        })
        flash("Profile updated.", "success")
        return redirect(url_for("profile", username=me))

    fields = [
        "bio", "avatar_url", "cover_url", "work", "education", "current_city", "hometown",
        "relationship_status", "website", "business_category", "business_phone", "business_address",
    ]
    for field in fields:
        getattr(form, field).data = user.get(field) if user else None
    return render_template("edit_profile.html", form=form, is_business=(user or {}).get("account_type") == "business")


# -------------------------------------------------------------------------
# POST DETAIL, LIKES, COMMENTS, REPOSTS
# -------------------------------------------------------------------------

@app.get("/post/<username>/<ts>")
@login_required
def post_detail(username, ts):
    me = current_username()
    post = svc.get_post(username, ts)
    if post is None:
        flash("Post not found.", "warning")
        return redirect(url_for("home"))
    entry = build_post_display(post, me, svc.batch_users([username]))
    comments = svc.list_comments(username, ts)
    comment_authors = svc.batch_users([c["commenter_username"] for c in comments])
    for c in comments:
        c["author"] = comment_authors.get(c["commenter_username"], {"username": c["commenter_username"]})
    return render_template("post_detail.html", entry=entry, comments=comments, comment_form=CommentForm(), repost_form=RepostForm())


@app.post("/post/<username>/<ts>/like")
@login_required
def like_post(username, ts):
    reaction_type = request.form.get("reaction", "like")
    svc.react(current_username(), username, ts, reaction_type)
    return redirect(request.referrer or url_for("home"))


@app.post("/post/<username>/<ts>/comment")
@login_required
def add_comment(username, ts):
    form = CommentForm()
    if form.validate_on_submit():
        svc.add_comment(current_username(), username, ts, form.content.data)
    return redirect(url_for("post_detail", username=username, ts=ts))


@app.post("/post/<username>/<ts>/repost")
@login_required
def repost(username, ts):
    form = RepostForm()
    if form.validate_on_submit():
        result = svc.create_repost(current_username(), username, ts, form.comment.data or None)
        if result is not None:
            flash("Reposted!", "success")
    return redirect(request.referrer or url_for("home"))


# -------------------------------------------------------------------------
# STORIES
# -------------------------------------------------------------------------

@app.post("/story/new")
@login_required
def new_story():
    me = current_username()
    content = (request.form.get("content") or "").strip()
    image_url = _maybe_upload(me, request.files.get("photo"))
    if not content and not image_url:
        flash("Add a photo or some text for your story.", "warning")
        return redirect(url_for("home"))
    svc.create_story(me, content or None, image_url)
    flash("Story posted! It disappears in 24 hours.", "success")
    return redirect(url_for("home"))


@app.get("/stories/<username>")
@login_required
def view_stories(username):
    stories = svc.stories_of(username)
    if not stories:
        flash("No active stories.", "info")
        return redirect(url_for("home"))
    return render_template("stories_viewer.html", stories=stories, story_username=username)


# -------------------------------------------------------------------------
# HASHTAGS
# -------------------------------------------------------------------------

@app.get("/hashtag/<tag>")
@login_required
def hashtag(tag):
    posts = svc.posts_by_hashtag(tag.lower())
    feed = build_posts_display(posts, current_username())
    return render_template("hashtag.html", tag=tag.lower(), feed=feed)


# -------------------------------------------------------------------------
# DIRECT MESSAGES
# -------------------------------------------------------------------------

@app.get("/messages")
@login_required
def messages_inbox():
    me = current_username()
    convos = svc.conversations(me)
    users = svc.batch_users([c["other_username"] for c in convos])
    for c in convos:
        c["other_user"] = users.get(c["other_username"], {"username": c["other_username"]})
    return render_template("messages_inbox.html", conversations=convos)


@app.route("/messages/<other_username>", methods=["GET", "POST"])
@login_required
def messages_thread(other_username):
    me = current_username()
    if other_username == me:
        flash("You can't message yourself.", "warning")
        return redirect(url_for("messages_inbox"))
    if svc.get_user(other_username) is None:
        flash(f"No such user: {other_username}", "warning")
        return redirect(url_for("messages_inbox"))

    form = MessageForm()
    if form.validate_on_submit():
        svc.send_message(me, other_username, form.content.data)
        return redirect(url_for("messages_thread", other_username=other_username))

    history = svc.message_history(me, other_username)
    latest_id = history[-1]["sent_at_id"] if history else "0"
    return render_template("messages_thread.html", other_username=other_username, history=history, form=form, latest_id=latest_id)


@app.get("/messages/<other_username>/poll")
@login_required
def messages_poll(other_username):
    since = request.args.get("since")
    return jsonify(svc.poll_messages(current_username(), other_username, since))


# -------------------------------------------------------------------------
# NOTIFICATIONS
# -------------------------------------------------------------------------

@app.get("/notifications")
@login_required
def notifications_page():
    me = current_username()
    notifs = svc.list_notifications(me)
    actors = svc.batch_users([n["actor_username"] for n in notifs])
    for n in notifs:
        n["actor"] = actors.get(n["actor_username"], {"username": n["actor_username"]})
    svc.mark_all_notifications_read(me)
    return render_template("notifications.html", notifications=notifs)


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5010)), debug=debug_mode, threaded=True)
