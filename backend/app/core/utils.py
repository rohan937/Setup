"""Shared utility functions."""

from __future__ import annotations

import re


def slugify(value: str) -> str:
    """Convert a string to a URL-safe slug.

    Lowercases, strips non-alphanumeric characters (keeping hyphens and
    spaces), collapses whitespace/hyphens to single hyphens, and trims.
    Truncates to 100 characters to match the slug column length.
    """
    s = value.lower()
    s = re.sub(r"[^\w\s-]", "", s)  # remove non-word chars except spaces/hyphens
    s = re.sub(r"[\s_]+", "-", s)   # collapse whitespace and underscores
    s = re.sub(r"-+", "-", s)        # collapse multiple hyphens
    s = s.strip("-")
    return s[:100]
