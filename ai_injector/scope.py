"""Authorization / scope guard.

Rule: **no request leaves the process for a host that is not explicitly
authorized.** Two independent gates must both pass:

1. The host must be in the global allowlist (``config.scope.allow``).
2. The target profile must have been confirmed by the operator
   (``ai-injector scope confirm <name> --owned``).

This is intentionally conservative. An offensive tool that can be pointed at
an arbitrary host by a typo is a liability, so we fail closed and demand an
explicit, recorded confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from .errors import ScopeError


@dataclass
class ScopeDecision:
    allowed: bool
    host: str
    reason: str


def host_of(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host


def host_in_allowlist(url: str, allow: List[str]) -> bool:
    """Match host against the allowlist.

    Supports exact hostnames and a single leading-dot / ``*.`` wildcard form
    (``.example.com`` matches ``api.example.com`` but not ``example.com.evil``).
    """
    host = host_of(url)
    if not host:
        return False
    for entry in allow:
        entry = entry.strip().lower()
        if not entry:
            continue
        if entry.startswith("*."):
            entry = entry[1:]  # "*.x.com" -> ".x.com"
        if entry.startswith("."):
            if host == entry[1:] or host.endswith(entry):
                return True
        elif host == entry:
            return True
    return False


def check(
    url: str,
    allow: List[str],
    confirmed: bool,
    require_confirmation: bool = True,
) -> ScopeDecision:
    """Evaluate the two scope gates and return a decision.

    Never raises; callers decide whether to abort. :func:`enforce` is the
    raising wrapper used on the request path.
    """
    host = host_of(url)
    if not host:
        return ScopeDecision(False, host, "could not determine target host")

    if not host_in_allowlist(url, allow):
        return ScopeDecision(
            False,
            host,
            f"host '{host}' is not in the scope allowlist {allow!r}",
        )

    if require_confirmation and not confirmed:
        return ScopeDecision(
            False,
            host,
            f"target '{host}' has not been confirmed as authorized "
            f"(run: ai-injector scope confirm <name> --owned)",
        )

    return ScopeDecision(True, host, "authorized")


def enforce(
    url: str,
    allow: List[str],
    confirmed: bool,
    require_confirmation: bool = True,
) -> None:
    decision = check(url, allow, confirmed, require_confirmation)
    if not decision.allowed:
        raise ScopeError(decision.reason)


@dataclass
class ScopeResult:
    url: str
    allowed: bool
    reason: str
    confirmed: bool
    in_allowlist: bool
