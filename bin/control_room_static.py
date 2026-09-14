#!/usr/bin/env python3
"""Static file serving for the Control Room (T5.3), fail-closed.

Three extensions, one directory, no symlink escape: the requested name resolves under the static
directory or it is a 404, and anything the allowlist does not name is a 404 before the disk is
touched. The handler adds the headers; this module only decides what bytes, if any, exist.
"""
from __future__ import annotations

import pathlib

CONTENT_TYPES = {"css": "text/css", "js": "text/javascript", "svg": "image/svg+xml"}


def serve(static_dir: pathlib.Path, name: str) -> tuple[int, str | None, bytes]:
    suffix = name.rsplit(".", 1)[-1] if "." in name else ""
    content_type = CONTENT_TYPES.get(suffix)
    if not content_type or not name or "/" in name or "\\" in name:
        return 404, None, b""
    root = pathlib.Path(static_dir).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path.parent != root or not path.is_file():
        return 404, None, b""
    return 200, content_type, path.read_bytes()
