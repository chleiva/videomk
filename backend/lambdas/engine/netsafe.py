"""Small, defensive HTTP helpers for fetching third-party content (images, search APIs)."""
import ipaddress
import json
import os
import socket
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

# Wikimedia and Openverse ask automated clients to identify themselves; set HTTP_USER_AGENT per deployment.
USER_AGENT = os.environ.get("HTTP_USER_AGENT", "explainer-engine/2.0")


class FetchError(RuntimeError):
    pass


def _check_public_https(url: str) -> None:
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or not p.hostname:
        raise FetchError("only https URLs are allowed")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchError("dns failure") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError("refusing non-public address")


class _NoCrossSchemeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_public_https(newurl)  # every hop must also be public https
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_NoCrossSchemeRedirect)


def fetch_bytes(url: str, *, max_bytes: int = 15_000_000, timeout: int = 20, headers: Optional[Dict[str, str]] = None) -> bytes:
    _check_public_https(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with _opener.open(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
    except FetchError:
        raise
    except Exception as e:
        raise FetchError(f"fetch failed: {type(e).__name__}") from e
    if len(data) > max_bytes:
        raise FetchError("response too large")
    return data


def fetch_json(url: str, *, timeout: int = 15) -> Any:
    return json.loads(fetch_bytes(url, max_bytes=2_000_000, timeout=timeout, headers={"Accept": "application/json"}))
