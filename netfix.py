"""
DNS fallback for unreliable networks.

Some ISPs' DNS servers randomly fail lookups (Windows error 11002 "getaddrinfo failed"), which made map
searches, website audits and "no website" checks fail. install() wraps socket.getaddrinfo: if the
system lookup fails, the name is resolved through DNS-over-HTTPS on Google / Cloudflare, reached by IP
address so no DNS is needed to reach them. Every HTTP library that uses Python sockets benefits.
"""
import json
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:  # certifi ships with httpx, but stay safe
    _SSL = ssl.create_default_context()

_DOH_ENDPOINTS = ("https://8.8.8.8/resolve", "https://1.1.1.1/dns-query", "https://8.8.4.4/resolve")
_original_getaddrinfo = socket.getaddrinfo
_cache = {}  # host -> (expires_at, [ip, ...]); empty list = confirmed not to exist
_lock = threading.Lock()
_installed = False


def _is_ip(host: str) -> bool:
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, host)
            return True
        except (OSError, ValueError):
            pass
    return False


def resolve_doh(host: str):
    """Returns a list of IPv4 addresses, [] if the name does not exist, or None if DoH was unreachable."""
    now = time.time()
    with _lock:
        hit = _cache.get(host)
        if hit and hit[0] > now:
            return hit[1]
    for endpoint in _DOH_ENDPOINTS:
        url = f"{endpoint}?name={urllib.parse.quote(host)}&type=A"
        try:
            req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
            with urllib.request.urlopen(req, timeout=6, context=_SSL) as resp:
                data = json.load(resp)
        except Exception:
            continue
        if data.get("Status") == 3:  # NXDOMAIN
            ips, ttl = [], 300
        elif data.get("Status") == 0:
            answers = [a for a in data.get("Answer", []) if a.get("type") == 1]
            ips = [a["data"] for a in answers]
            ttl = min([a.get("TTL", 300) for a in answers] or [300])
        else:
            continue
        with _lock:
            _cache[host] = (now + max(60, ttl), ips)
        return ips
    return None


_exists_cache = {}  # host -> (expires_at, True/False)


async def host_exists(host: str):
    """
    Async DNS-over-HTTPS existence check (True / False / None if unknown). Reaches the resolvers by IP and
    never blocks a thread - use it before connecting to guessed domains, most of which don't exist and
    would otherwise each tie up a thread in getaddrinfo.
    """
    import httpx
    host = (host or "").split(":")[0].strip().lower().rstrip(".")
    now = time.time()
    hit = _exists_cache.get(host)
    if hit and hit[0] > now:
        return hit[1]
    for endpoint in _DOH_ENDPOINTS:
        try:
            async with httpx.AsyncClient(timeout=6.0, verify=_SSL) as client:
                res = await client.get(endpoint, params={"name": host, "type": "A"}, headers={"accept": "application/dns-json"})
            data = res.json()
        except Exception:
            continue
        if data.get("Status") == 3:
            result = False
        elif data.get("Status") == 0:
            result = any(a.get("type") in (1, 5) for a in data.get("Answer", []))
            ips = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
            if ips:
                with _lock:
                    _cache[host] = (now + 300, ips)
        else:
            continue
        _exists_cache[host] = (now + 600, result)
        return result
    return None


def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _original_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        name = host.decode() if isinstance(host, bytes) else host
        if not name or _is_ip(name) or name == "localhost" or family == socket.AF_INET6:
            raise
        known = _exists_cache.get(name.lower())
        if known and known[0] > time.time() and known[1] is False:
            raise  # already confirmed not to exist - skip the slow DoH round-trip
        ips = resolve_doh(name)
        if not ips:
            raise
        port_num = int(port) if port not in (None, "") and str(port).isdigit() else (
            socket.getservbyname(port) if isinstance(port, str) and port else 0)
        socktypes = [type] if type else [socket.SOCK_STREAM]
        return [(socket.AF_INET, st, proto or (socket.IPPROTO_TCP if st == socket.SOCK_STREAM else 0), "", (ip, port_num))
                for ip in ips for st in socktypes]


def install():
    global _installed
    if not _installed:
        socket.getaddrinfo = _getaddrinfo
        _installed = True
