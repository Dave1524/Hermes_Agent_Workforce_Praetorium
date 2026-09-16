#!/usr/bin/env python3
"""Static file serving for the Control Room (T5.3, SPA since T5.3e), fail-closed.

Four extensions, flat directories, no symlink escape: the requested name resolves directly under
the directory it was asked from or it is a 404, and anything the allowlist does not name is a
404 before the disk is touched. Three entry points share the one guard — `/static/<name>` for
the SSR pages, `/app/assets/<name>` for the SPA bundle and fonts, and the SPA shell itself. The
handler adds the headers; this module only decides what bytes, if any, exist.
"""
from __future__ import annotations

import pathlib

CONTENT_TYPES = {"css": "text/css", "js": "text/javascript", "svg": "image/svg+xml", "woff2": "font/woff2"}
APP_DIR = "app"
APP_ASSETS_DIR = "assets"
APP_SHELL = "index.html"


def _resolve_inside(root: pathlib.Path, name: str) -> pathlib.Path | None:
    if not name or "/" in name or "\\" in name:
        return None
    root = pathlib.Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path.parent != root or not path.is_file():
        return None
    return path


def serve(static_dir: pathlib.Path, name: str) -> tuple[int, str | None, bytes]:
    suffix = name.rsplit(".", 1)[-1] if "." in name else ""
    content_type = CONTENT_TYPES.get(suffix)
    if not content_type:
        return 404, None, b""
    path = _resolve_inside(pathlib.Path(static_dir), name)
    if path is None:
        return 404, None, b""
    return 200, content_type, path.read_bytes()


def serve_app_asset(static_dir: pathlib.Path, name: str) -> tuple[int, str | None, bytes]:
    return serve(pathlib.Path(static_dir) / APP_DIR / APP_ASSETS_DIR, name)


def serve_app_shell(static_dir: pathlib.Path) -> tuple[int, bytes]:
    path = _resolve_inside(pathlib.Path(static_dir) / APP_DIR, APP_SHELL)
    if path is None:
        return 404, b""
    return 200, path.read_bytes()
