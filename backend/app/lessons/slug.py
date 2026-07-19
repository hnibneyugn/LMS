"""Slug generation for lessons.

Hand-rolled rather than pulling in python-slugify: the project's first design
principle is to stay simple and dependency-light, and the only hard
requirement here is stripping Vietnamese diacritics, which `unicodedata`
already does.
"""

import re
import unicodedata

_MAX_SLUG_CHARS = 80
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase ASCII slug. Returns "" if nothing usable survives."""
    # NFD splits "ế" into "e" + combining accent; the Mn filter then drops the
    # accent. "đ"/"Đ" is NOT a base letter plus accent, so it survives NFD
    # untouched and has to be mapped by hand.
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    ascii_text = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    ).lower()
    slug = _NON_SLUG.sub("-", ascii_text).strip("-")
    # Strip again after truncation so a cut that lands on a separator does not
    # leave a trailing dash.
    return slug[:_MAX_SLUG_CHARS].strip("-")


def unique_slug(base: str, taken: set[str]) -> str:
    """`base`, or `base-2`, `base-3`... until one is free in `taken`."""
    if base not in taken:
        return base
    counter = 2
    while f"{base}-{counter}" in taken:
        counter += 1
    return f"{base}-{counter}"
