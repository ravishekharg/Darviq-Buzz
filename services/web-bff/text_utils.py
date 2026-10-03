"""Pure text parsing helpers: hashtag/mention extraction and linkification.

Kept dependency-free and side-effect-free so it's cheaply unit-testable
without a database or Flask app context.
"""
from __future__ import annotations

import re
from markupsafe import Markup, escape

HASHTAG_PATTERN = re.compile(r"#(\w+)")
MENTION_PATTERN = re.compile(r"@(\w+)")


def extract_hashtags(content: str) -> list[str]:
    """Returns unique lowercase hashtags (without the '#'), in first-seen order."""
    seen: dict[str, None] = {}
    for match in HASHTAG_PATTERN.finditer(content):
        tag = match.group(1).lower()
        seen.setdefault(tag, None)
    return list(seen)


def extract_mentions(content: str) -> list[str]:
    """Returns unique mentioned usernames (without the '@'), in first-seen order."""
    seen: dict[str, None] = {}
    for match in MENTION_PATTERN.finditer(content):
        seen.setdefault(match.group(1), None)
    return list(seen)


def linkify(content: str) -> Markup:
    """Escapes content then turns #hashtag and @mention tokens into links.

    Escaping happens first so post content can never inject arbitrary HTML;
    only the tokens we generate ourselves become markup.
    """
    escaped = str(escape(content))

    def hashtag_sub(match: re.Match) -> str:
        tag = match.group(1)
        return f'<a href="/hashtag/{tag.lower()}">#{tag}</a>'

    def mention_sub(match: re.Match) -> str:
        username = match.group(1)
        return f'<a href="/user/{username}">@{username}</a>'

    linked = HASHTAG_PATTERN.sub(hashtag_sub, escaped)
    linked = MENTION_PATTERN.sub(mention_sub, linked)
    return Markup(linked)
