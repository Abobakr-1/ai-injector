"""Typed errors so the CLI can exit with meaningful codes and honest messages."""

from __future__ import annotations


class AIInjectorError(Exception):
    """Base class for all ai-injector errors."""


class ConfigError(AIInjectorError):
    """Configuration is missing or malformed."""


class ScopeError(AIInjectorError):
    """A request was blocked by the authorization / scope guard.

    Raised *before* any network traffic leaves the process.
    """


class TargetError(AIInjectorError):
    """Target profile could not be loaded, probed, or is malformed."""


class AdapterError(AIInjectorError):
    """An adapter could not build a request or parse a response."""


class PayloadError(AIInjectorError):
    """A payload pack is missing fields or is otherwise invalid."""


class TransportError(AIInjectorError):
    """A network request failed (timeout, DNS, connection reset, ...).

    A transport failure is a *coverage gap*, never a negative result. The engine
    records it as ERROR and it is reported separately from NEGATIVE findings.
    """
