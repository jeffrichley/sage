"""Validation helpers for YouTube URLs and identifiers."""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs


class InvalidYouTubeURLError(ValueError):
    """Raised when a provided URL is not a valid YouTube video link."""


_VIDEO_ID_PATTERN = re.compile(r"^[0-9A-Za-z_-]{11}$")


def extract_video_id(url: str) -> str:
    """Extract and validate a YouTube video ID from a URL or raw ID string."""

    stripped = url.strip()
    if _VIDEO_ID_PATTERN.fullmatch(stripped):
        return stripped

    parsed = urlparse(stripped)
    if parsed.netloc in {"youtu.be"}:
        candidate = parsed.path.lstrip("/")
        if _VIDEO_ID_PATTERN.fullmatch(candidate):
            return candidate

    if parsed.netloc.endswith("youtube.com"):
        # Handle standard watch URLs and embedded formats.
        if parsed.path == "/watch":
            query_params = parse_qs(parsed.query)
            candidate_list = query_params.get("v", [])
            if candidate_list:
                candidate = candidate_list[0]
                if _VIDEO_ID_PATTERN.fullmatch(candidate):
                    return candidate
        else:
            embedded_match = re.search(r"/embed/([0-9A-Za-z_-]{11})", parsed.path)
            if embedded_match:
                return embedded_match.group(1)

    raise InvalidYouTubeURLError(f"Invalid YouTube URL or video ID: {url!r}")


def validate_youtube_url(url: str) -> str:
    """Validate a URL and return the normalized video ID if successful."""

    return extract_video_id(url)


__all__ = ["InvalidYouTubeURLError", "extract_video_id", "validate_youtube_url"]

