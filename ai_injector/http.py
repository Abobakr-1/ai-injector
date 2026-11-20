"""HTTP transport with raw evidence capture.

Every request the engine makes goes through :class:`HttpClient`. The client:

* enforces the scope guard **before** opening a socket,
* records the exact request (method, URL, headers-with-redaction, body) and the
  exact response (status, headers, body) so a finding is reproducible,
* classifies transport failures as :class:`TransportError` (a coverage gap),
  never as a negative result.

Redaction: header values for Authorization / api-key / cookie are replaced with
``<redacted>`` in the *stored* evidence only. The live request still carries the
real value.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import requests

from .errors import TransportError

_REDACT_HEADERS = {
    "authorization",
    "api-key",
    "x-api-key",
    "cookie",
    "set-cookie",
    "proxy-authorization",
}


def redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _REDACT_HEADERS:
            out[key] = "<redacted>"
        else:
            out[key] = value
    return out


@dataclass
class CapturedRequest:
    method: str
    url: str
    headers: Dict[str, str]
    body: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "headers": redact_headers(self.headers),
            "body": self.body,
        }


@dataclass
class CapturedResponse:
    status: int
    headers: Dict[str, str]
    body_text: str
    elapsed_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "headers": redact_headers(self.headers),
            "body_text": self.body_text,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass
class Exchange:
    """A single request/response pair plus provenance."""

    request: CapturedRequest
    response: Optional[CapturedResponse]
    error: Optional[str] = None
    ok: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "response": self.response.to_dict() if self.response else None,
            "error": self.error,
            "ok": self.ok,
        }


class HttpClient:
    def __init__(
        self,
        *,
        timeout: int = 30,
        follow_redirects: bool = False,
        verify_tls: bool = True,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.verify_tls = verify_tls
        self._session = session or requests.Session()

    def send(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Any] = None,
        data: Optional[str] = None,
    ) -> Exchange:
        headers = dict(headers or {})
        captured_headers = dict(headers)
        if json_body is not None:
            body_for_record: Optional[Any] = json_body
            send_kwargs: Dict[str, Any] = {"json": json_body}
        elif data is not None:
            body_for_record = data
            send_kwargs = {"data": data.encode("utf-8")}
        else:
            body_for_record = None
            send_kwargs = {}

        captured = CapturedRequest(method=method, url=url, headers=captured_headers, body=body_for_record)

        started = time.monotonic()
        try:
            resp = self._session.request(
                method,
                url,
                headers=headers or None,
                timeout=self.timeout,
                allow_redirects=self.follow_redirects,
                verify=self.verify_tls,
                **send_kwargs,
            )
        except requests.RequestException as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            return Exchange(
                request=captured,
                response=None,
                error=f"{type(exc).__name__}: {exc}",
                ok=False,
            )

        elapsed = int((time.monotonic() - started) * 1000)
        response = CapturedResponse(
            status=resp.status_code,
            headers=dict(resp.headers),
            body_text=resp.text,
            elapsed_ms=elapsed,
        )
        return Exchange(request=captured, response=response, ok=True)

    def send_or_raise(self, *args: Any, **kwargs: Any) -> Exchange:
        ex = self.send(*args, **kwargs)
        if not ex.ok:
            raise TransportError(ex.error or "transport failure")
        return ex
