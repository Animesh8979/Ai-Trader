"""Static SSRF guard for outbound URLs built from config/user-controlled input.

ScrollCraft-pattern transfer: any URL handed to an HTTP client must pass
validate_public_http_url(). Static mode (no DNS resolution) blocks schemes,
embedded credentials, localhost-style hosts, and private/link-local literal
IPs (incl. cloud metadata 169.254.169.254) while keeping offline tests
deterministic. resolve=True additionally pins every resolved A/AAAA record
to a public address for defense-in-depth at runtime.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse


class URLBlockedError(ValueError):
    """Raised when a URL fails SSRF safety checks."""


_CGNAT_NETS = tuple(ipaddress.ip_network(n) for n in (
    "100.64.0.0/10",    # RFC 6598 carrier-grade NAT — is_private misses it
))


def _require_public_ip(ip: ipaddress._BaseAddress) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # includes cloud metadata 169.254.169.254
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified  # 0.0.0.0 / ::
        or any(ip.version == 4 and ip in net for net in _CGNAT_NETS)
    ):
        raise URLBlockedError(f"non-public IP blocked: {ip}")


def validate_public_http_url(url: str, *, resolve: bool = False) -> str:
    """Return `url` unchanged if safe, else raise URLBlockedError."""
    if not url or not isinstance(url, str):
        raise URLBlockedError("URL must be a non-empty string")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise URLBlockedError(f"URL scheme {parsed.scheme!r} not allowed (http/https only)")
    if parsed.username or parsed.password:
        raise URLBlockedError("credentials embedded in URL are not allowed")

    host = parsed.hostname
    if not host:
        raise URLBlockedError("URL has no hostname")
    host_l = host.lower().rstrip(".")

    literal_ip: Optional[ipaddress._BaseAddress]
    try:
        literal_ip = ipaddress.ip_address(host_l)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        _require_public_ip(literal_ip)
    else:
        if host_l == "localhost" or host_l.endswith(".localhost") or host_l.endswith(".local"):
            raise URLBlockedError(f"local hostname blocked: {host}")
        if resolve:
            try:
                infos = socket.getaddrinfo(host, None)
            except socket.gaierror as exc:
                raise URLBlockedError(f"could not resolve {host}: {exc}")
            if not infos:
                raise URLBlockedError(f"no DNS records for {host}")
            for info in infos:
                _require_public_ip(ipaddress.ip_address(info[4][0]))

    return url
