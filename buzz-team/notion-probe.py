#!/usr/bin/env python3
"""Round-trip the Notion broker socket. Exits 0 when the credential authenticates.

Its own file so verify-fleet.sh can run it unchanged on the host and inside an
agent's bwrap namespace via nsenter — the two places that can disagree, and the
disagreement that broke augustus's Notion access on 2026-08-10.
Prints the broker's answer, which by construction never carries the token.
"""

from __future__ import annotations

import json
import os
import socket
import sys


SOCKET_PATH = os.environ.get(
    "BUZZ_NOTION_SOCKET",
    f"/run/user/{os.getuid()}/buzz-notion.sock",
)


def main() -> int:
    request = json.dumps({"tool": "notion_status", "arguments": {}}).encode("utf-8")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(30)
            client.connect(SOCKET_PATH)
            client.sendall(request + b"\n")
            client.shutdown(socket.SHUT_WR)
            body = client.recv(65536)
    except OSError as exc:
        print(f"broker unreachable at {SOCKET_PATH}: {exc}", file=sys.stderr)
        return 1
    response = json.loads(body.decode("utf-8"))
    print(json.dumps(response))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
