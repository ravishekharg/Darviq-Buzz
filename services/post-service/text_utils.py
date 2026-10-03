"""Hashtag extraction only -- linkify (HTML rendering) is a web-bff concern,
not post-service's. Pure function, ported unchanged from the original
monolith's text_utils.py."""
import re

HASHTAG_PATTERN = re.compile(r"#(\w+)")


def extract_hashtags(content: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in HASHTAG_PATTERN.finditer(content):
        tag = match.group(1).lower()
        seen.setdefault(tag, None)
    return list(seen)
