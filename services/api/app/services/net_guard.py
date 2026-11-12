"""Outbound URL guard.

Webhook endpoints are user supplied and the API POSTs to them, which is a
server-side request forgery surface. Only public http(s) destinations are allowed.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "metadata.google.internal"}


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True  # not a literal IP, handled by the hostname check

    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_public_url(url: str) -> str:
    """Returns the URL unchanged, or raises ``ValueError`` with a reason."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Webhook URL must be an absolute http(s) URL.")

    host = parsed.hostname.lower().rstrip(".")
    if host in LOCAL_HOSTNAMES or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("Webhook URL must point at a public host, not a local address.")

    if not _is_public_address(host):
        raise ValueError("Webhook URL must point at a public host, not a private IP address.")

    # Resolve names when possible so a public-looking name cannot hide a private IP.
    try:
        resolved = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except OSError:
        return url  # unreachable names fail later, when the delivery is attempted

    if any(not _is_public_address(item) for item in resolved):
        raise ValueError("Webhook URL resolves to a private address; use a public endpoint.")

    return url
