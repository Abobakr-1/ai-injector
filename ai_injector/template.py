"""Deliberately minimal templating for target bodies and payload text.

Only these forms are supported, so a profile stays easy to audit:

    {{prompt}}       user-supplied prompt / payload text
    {{user}}         current identity's "user" value
    {{session}}      current identity's "session" value
    {{canary}}       the unique canary token for this run
    {{env:NAME}}     value of environment variable NAME (secrets)

No loops, no conditionals, no attribute access. Unknown variables are a hard
error rather than silently left in place, because a body that still contains
``{{prompt}}`` would test nothing and could produce a false NEGATIVE.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w:.-]*)\s*\}\}")


class TemplateError(ValueError):
    pass


def substitute(text: str, values: Dict[str, Any], allow_env: bool = True) -> str:
    if not isinstance(text, str):
        return text

    def repl(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key.startswith("env:"):
            if not allow_env:
                raise TemplateError("env substitution disabled")
            name = key[4:]
            val = os.environ.get(name)
            if val is None:
                raise TemplateError(f"environment variable {name!r} is not set")
            return val
        if key not in values:
            raise TemplateError(f"unknown template variable {{{{{key}}}}}")
        val = values[key]
        return "" if val is None else str(val)

    return _TEMPLATE_RE.sub(repl, text)


def has_unresolved(text: str) -> bool:
    """True if any ``{{...}}`` token remains (used as a sanity assertion)."""
    return bool(isinstance(text, str) and _TEMPLATE_RE.search(text))


def substitute_obj(obj: Any, values: Dict[str, Any], allow_env: bool = True) -> Any:
    """Recursively substitute inside dicts / lists / strings."""
    if isinstance(obj, str):
        return substitute(obj, values, allow_env=allow_env)
    if isinstance(obj, dict):
        return {k: substitute_obj(v, values, allow_env=allow_env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute_obj(v, values, allow_env=allow_env) for v in obj]
    return obj
