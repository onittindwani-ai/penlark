"""Shared adapter helpers: the SSRF guard for base URLs a person can set.

The address is checked in two steps. When the adapter is built only the text of the URL is checked (no network, so a DNS hiccup at restart cannot stop the API or the worker
from starting). The host is looked up, and refused if it is private, at the moment of each request.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from sendora_core.adapters import AdapterError

PRIVATE_HOW_TO = "For a scheduling tool you run yourself on a private address, set ALLOW_PRIVATE_SCHEDULER=true."


def _private(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def safe_base_url(url: str, *, allow_http_local: bool = False) -> str:
    """Refuse base URLs that are not a plain web address (checked as text, never by looking the host up).

    Only https is accepted, no credentials in the URL, and no address or name that is plainly local. `allow_http_local` (a deliberate choice for a tool on your own network, and tests)
    also allows http and private addresses.
    """
    u = urlparse(url)
    if u.scheme not in {"https", "http"} or not u.hostname:
        raise AdapterError("The URL must start with https:// and include a host name.")
    if u.username or u.password:
        raise AdapterError("Put credentials in the key fields, not in the URL.")
    if u.scheme == "http" and not allow_http_local:
        raise AdapterError("Use an https:// URL. " + PRIVATE_HOW_TO)
    if not allow_http_local:
        host = u.hostname.lower()
        try:
            literal = _private(ipaddress.ip_address(host))
        except ValueError:
            literal = host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan"))
        if literal:
            raise AdapterError("That URL points at a private or local address, which is refused. " + PRIVATE_HOW_TO)
    return url.rstrip("/")


def check_host_now(host: str, port: int, *, allow_private: bool) -> None:
    """Look the host up now and refuse it when it is not found or points at a private address. Called before every request, never at start up."""
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise AdapterError(f"The host {host} could not be found.") from exc
    for info in infos:
        if _private(ipaddress.ip_address(info[4][0])):
            raise AdapterError("That URL points at a private or local address, which is refused. " + PRIVATE_HOW_TO)


def guarded_client(base_url: str, *, allow_private: bool = False, timeout: float = 30, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """An HTTP client for a scheduling tool. Nothing goes over the network when it is built; each request first checks where the host really points."""
    url = safe_base_url(base_url, allow_http_local=allow_private)

    def guard(request: httpx.Request) -> None:
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        check_host_now(request.url.host, port, allow_private=allow_private)

    return httpx.Client(base_url=url, timeout=timeout, event_hooks={"request": [guard]}, transport=transport)
