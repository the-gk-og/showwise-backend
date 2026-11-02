"""
Outbound checks against customer instances: is it up, and is its support-login receiver switched on?

Only public https:// URLs are contacted. The host must resolve to global addresses, redirects are not
followed, and the timeout is short, so a bad organization URL cannot be used to probe internal services.
"""
import ipaddress
import socket
import time
from urllib.parse import urlparse

import requests

USER_AGENT = 'ShowWise-Instance-Check/1.0'


def _result(status, detail, latency=None):
    return {'status': status, 'detail': detail, 'latency_ms': latency}


def _fetch(raw_url, path):
    """GET raw_url + path. Returns (response, latency_ms, None) or (None, None, error_result)."""
    raw_url = (raw_url or '').strip()
    parsed = urlparse(raw_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        return None, None, _result('unknown', 'Set a valid https:// URL for this organization')
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise OSError('No DNS addresses')
        for address in addresses:
            if not ipaddress.ip_address(address[4][0]).is_global:
                return None, None, _result('blocked', 'URL resolves to a non-public address')
        start = time.monotonic()
        response = requests.get(raw_url.rstrip('/') + path, timeout=4, allow_redirects=False,
                                headers={'User-Agent': USER_AGENT})
        return response, round((time.monotonic() - start) * 1000), None
    except requests.RequestException as exc:
        return None, None, _result('down', type(exc).__name__)
    except (OSError, ValueError) as exc:
        return None, None, _result('down', type(exc).__name__)


def instance_health(raw_url):
    """status: up | degraded | down | blocked | unknown"""
    response, latency, error = _fetch(raw_url, '/api/health')
    if error:
        return error
    if response.status_code == 200:
        try:
            healthy = response.json().get('status') == 'ok'
        except (ValueError, AttributeError):
            healthy = False
        return _result('up' if healthy else 'degraded', f'HTTP {response.status_code}', latency)
    return _result('degraded', f'HTTP {response.status_code}', latency)


def support_receiver_status(raw_url):
    """Is /support/login on the instance switched on?

    ready           the receiver answered
    not_configured  404 or some other page: SUPPORT_PUBLIC_KEY / SUPPORT_INSTANCE_ID are not set,
                    or the instance does not include support_access.py yet
    down/unknown/blocked/error  see detail
    """
    response, latency, error = _fetch(raw_url, '/support/login')
    if error:
        return error
    code = response.status_code
    if code == 429:
        return _result('ready', 'Receiver is on (rate limited right now)', latency)
    if code == 200:
        body = response.text[:4000]
        if 'Support login' in body and 'name=token' in body:
            return _result('ready', 'Receiver is on', latency)
        return _result('not_configured', 'This URL answers, but it is not the support receiver', latency)
    if code == 404:
        return _result('not_configured', 'Not set up: add SUPPORT_PUBLIC_KEY and SUPPORT_INSTANCE_ID and restart', latency)
    if 300 <= code < 400:
        return _result('not_configured', 'Redirects instead of showing the support login', latency)
    return _result('error', f'HTTP {code}', latency)
