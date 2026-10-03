"""Assembles display-ready dicts for templates by combining calls across
several backend services -- the equivalent of the original monolith's
_post_engagement()/build_feed() helpers, now doing HTTP calls instead of
local Cassandra queries. Several small calls per item (N+1) is a deliberate,
documented tradeoff carried over from the original app's own design notes,
not an oversight.
"""
import services as svc


def build_post_display(post: dict, viewer: str | None, users_by_username: dict, reposted_by: str | None = None, repost_comment: str | None = None) -> dict:
    eng = svc.engagement(post["username"], post["url_id"], viewer)
    author = users_by_username.get(post["username"], {"username": post["username"], "avatar_url": None})
    return {
        "type": "repost" if reposted_by else "post",
        "author": author,
        "post": post,
        "reposted_by": reposted_by,
        "repost_comment": repost_comment,
        **eng,
    }


def build_feed_display(raw_entries: list[dict], viewer: str | None) -> list[dict]:
    refs = [f"{e['ref_username']}:{e['ref_url_id']}" for e in raw_entries]
    posts_by_ref = svc.batch_posts(refs)

    usernames = {e["ref_username"] for e in raw_entries}
    usernames |= {e["reposted_by"] for e in raw_entries if e.get("reposted_by")}
    users = svc.batch_users(list(usernames))

    display = []
    for e in raw_entries:
        post = posts_by_ref.get(f"{e['ref_username']}:{e['ref_url_id']}")
        if post is None:
            continue  # original post was deleted after this timeline entry was written
        display.append(build_post_display(
            post, viewer, users, reposted_by=e.get("reposted_by"), repost_comment=e.get("repost_comment"),
        ))
    return display


def build_posts_display(posts: list[dict], viewer: str | None) -> list[dict]:
    users = svc.batch_users(list({p["username"] for p in posts}))
    return [build_post_display(p, viewer, users) for p in posts]


def build_reposts_display(reposts: list[dict], viewer: str | None) -> list[dict]:
    users = svc.batch_users(list({r["original"]["username"] for r in reposts} | {r["reposter_username"] for r in reposts}))
    return [
        build_post_display(r["original"], viewer, users, reposted_by=r["reposter_username"], repost_comment=r["comment"])
        for r in reposts
    ]
