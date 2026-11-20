"""Adapters: translate a logical "send a prompt, get a reply" operation into the
concrete HTTP contract of a specific AI surface, and extract the reply text.

v1.0 ships the four adapters that cover the targets people actually attack:

* ``openai-chat``  -- ``POST /v1/chat/completions`` (OpenAI-compatible; also
  your Assistant service, LM Studio, llama.cpp server, vLLM, Ollama's
  ``/v1`` shim, and most "compatible" third parties).
* ``custom-chat``  -- any JSON POST that returns text (e.g. ``{"query": ...}``
  -> ``{"response": ...}``). User-described in the target profile.
* ``sse-stream``   -- ``text/event-stream`` replies (deltas stitched together).
* ``http``         -- raw request building from a target profile, used by the
  indirect module to PLANT content into a document/RAG store and to TRIGGER a
  neutral retrieval.

Adapters are pure: they build a request description or parse a response body and
never open sockets. The engine owns transport + evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .errors import AdapterError, TargetError
from .template import substitute_obj

# ---------------------------------------------------------------------------
# Request / reply containers
# ---------------------------------------------------------------------------


@dataclass
class BuiltRequest:
    """A concrete request the engine will send."""

    method: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    json_body: Optional[Any] = None
    data: Optional[str] = None
    #: The exact text the payload contributed (for reflection checks / evidence)
    prompt_text: str = ""


# ---------------------------------------------------------------------------
# Reply extraction helpers
# ---------------------------------------------------------------------------


def dig(obj: Any, path: str, default: Any = None) -> Any:
    """Extract ``a.b[0].c`` from nested dicts/lists. Empty path -> obj."""
    if not path:
        return obj
    cur = obj
    for raw in path.split("."):
        token = raw.strip()
        if not token:
            continue
        index: Optional[int] = None
        if "[" in token and token.endswith("]"):
            name, _, idx = token.partition("[")
            token = name.strip()
            index = int(idx[:-1])
        if token:
            if not isinstance(cur, dict) or token not in cur:
                return default
            cur = cur[token]
        if index is not None:
            if not isinstance(cur, list) or index >= len(cur):
                return default
            cur = cur[index]
    return cur


def extract_text(body_text: str, reply_path: str = "") -> Optional[str]:
    """Return the reply string from a response body.

    If ``reply_path`` is set, JSON is parsed and the path is followed. Otherwise
    we try a few well-known shapes and finally fall back to the raw text. Returns
    ``None`` only when the body is empty.
    """
    if body_text is None:
        return None
    if not body_text.strip():
        return None

    if reply_path:
        try:
            parsed = json.loads(body_text)
        except json.JSONDecodeError:
            # Streams / plain text: if the caller pointed at a JSON path but the
            # body is not JSON, the raw text is still the best signal.
            return body_text
        value = dig(parsed, reply_path)
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    # Auto-detect common shapes.
    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError:
        return body_text
    if isinstance(parsed, str):
        return parsed
    for path in (
        "choices[0].message.content",   # OpenAI-compatible
        "choices[0].text",              # legacy completions
        "message.content",              # Anthropic-style
        "response",                     # simple apps
        "answer",
        "output",
        "text",
        "content",
        "result.text",
        "reply",
    ):
        value = dig(parsed, path)
        if isinstance(value, str) and value:
            return value
    # Last resort: whole JSON as text so rules can still run.
    return body_text


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


class BaseAdapter:
    name = "base"

    def __init__(self, profile: Dict[str, Any]) -> None:
        self.profile = profile

    @property
    def request(self) -> Dict[str, Any]:
        return self.profile.get("request") or {}

    @property
    def response(self) -> Dict[str, Any]:
        return self.profile.get("response") or {}

    def _headers(self, values: Dict[str, Any]) -> Dict[str, str]:
        headers = dict(self.profile.get("headers") or {})
        return {k: str(v) for k, v in substitute_obj(headers, values).items()}

    def _url(self, path: Optional[str] = None) -> str:
        base = str(self.profile.get("url", "")).rstrip("/")
        sub = path if path is not None else str(self.request.get("path", ""))
        if not sub:
            return base
        if not sub.startswith("/"):
            sub = "/" + sub
        return base + sub

    def build(self, prompt: str, values: Dict[str, Any]) -> BuiltRequest:
        raise NotImplementedError

    def parse(self, body_text: str) -> Optional[str]:
        return extract_text(body_text, str(self.response.get("reply_path", "")))


class OpenAIChatAdapter(BaseAdapter):
    name = "openai-chat"

    def build(self, prompt: str, values: Dict[str, Any]) -> BuiltRequest:
        body_template = self.request.get("body")
        if body_template is None:
            body_template = {
                "model": self.profile.get("model", "gpt-4o-mini"),
                "messages": [{"role": "user", "content": "{{prompt}}"}],
            }
        merged = dict(values)
        merged.setdefault("prompt", prompt)
        body = substitute_obj(body_template, merged)
        path = self.request.get("path", "/v1/chat/completions")
        headers = {"Content-Type": "application/json", **self._headers(values)}
        return BuiltRequest("POST", self._url(path), headers, json_body=body, prompt_text=prompt)


class CustomChatAdapter(BaseAdapter):
    name = "custom-chat"

    def build(self, prompt: str, values: Dict[str, Any]) -> BuiltRequest:
        body_template = self.request.get("body")
        if body_template is None:
            raise TargetError(
                "custom-chat adapter requires request.body in the target profile"
            )
        merged = dict(values)
        merged["prompt"] = prompt
        body = substitute_obj(body_template, merged)
        method = str(self.request.get("method", "POST")).upper()
        path = self.request.get("path", "")
        headers = {"Content-Type": "application/json", **self._headers(values)}
        return BuiltRequest(method, self._url(path), headers, json_body=body, prompt_text=prompt)


class SSEStreamAdapter(BaseAdapter):
    name = "sse-stream"

    def build(self, prompt: str, values: Dict[str, Any]) -> BuiltRequest:
        body_template = self.request.get("body") or {"query": "{{prompt}}"}
        merged = dict(values)
        merged["prompt"] = prompt
        body = substitute_obj(body_template, merged)
        path = self.request.get("path", "")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **self._headers(values),
        }
        return BuiltRequest("POST", self._url(path), headers, json_body=body, prompt_text=prompt)

    def parse(self, body_text: str) -> Optional[str]:
        return parse_sse(body_text)


class RawHTTPAdapter(BaseAdapter):
    """A generic request builder driven entirely by the profile.

    Used for indirect injection where we need to (a) plant a document via some
    endpoint and (b) issue a neutral trigger request. The ``prompt`` is injected
    into the templated body/data like any other adapter.
    """

    name = "http"

    def build(self, prompt: str, values: Dict[str, Any]) -> BuiltRequest:
        merged = dict(values)
        merged["prompt"] = prompt
        method = str(self.request.get("method", "POST")).upper()
        path = self.request.get("path", "")
        headers = self._headers(values)
        body_template = self.request.get("body")
        data_template = self.request.get("data")
        json_body = None
        data = None
        if body_template is not None:
            json_body = substitute_obj(body_template, merged)
            headers.setdefault("Content-Type", "application/json")
        elif data_template is not None:
            data = str(substitute_obj(data_template, merged))
        return BuiltRequest(method, self._url(path), headers, json_body=json_body, data=data, prompt_text=prompt)


def parse_sse(body_text: str) -> str:
    """Stitch an SSE body into a single reply string.

    Handles the common ``data: {json}`` shapes and a bare ``data: text`` form.
    Also tolerates newline-delimited JSON (no ``data:`` prefix).
    """
    if not body_text:
        return ""
    chunks: List[str] = []
    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload in ("[DONE]", ""):
                continue
            chunks.append(_sse_payload_text(payload))
        elif line.startswith("event:"):
            continue
        elif line.startswith("{") or line.startswith("["):
            chunks.append(_sse_payload_text(line))
    if not chunks:
        return body_text
    return "".join(chunks)


def _sse_payload_text(payload: str) -> str:
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    for path in (
        "delta.text",
        "choices[0].delta.content",
        "choices[0].text",
        "content_block.delta.text",
        "text",
        "token",
        "delta",
        "content",
        "message",
    ):
        value = dig(obj, path)
        if isinstance(value, str):
            return value
    return ""


_ADAPTERS = {
    OpenAIChatAdapter.name: OpenAIChatAdapter,
    CustomChatAdapter.name: CustomChatAdapter,
    SSEStreamAdapter.name: SSEStreamAdapter,
    RawHTTPAdapter.name: RawHTTPAdapter,
}


def get_adapter(name: str, profile: Dict[str, Any]) -> BaseAdapter:
    if name not in _ADAPTERS:
        raise AdapterError(
            f"unknown adapter {name!r}; known: {', '.join(sorted(_ADAPTERS))}"
        )
    return _ADAPTERS[name](profile)


def adapter_names() -> List[str]:
    return sorted(_ADAPTERS)


# ---------------------------------------------------------------------------
# Autodetection (used by ``targets add``)
# ---------------------------------------------------------------------------

#: (adapter, probe_path, probe_method, matcher(response)->bool, confidence)
_DETECTORS = [
    ("openai-chat", "/v1/models", "GET", lambda t, s: s == 200 and '"object"' in t, 90),
    ("openai-chat", "/v1/chat/completions", "POST", None, 40),
]


def detect_adapter(client: Any, base_url: str, timeout_values: Dict[str, Any]) -> Dict[str, Any]:
    """Probe a URL and propose an adapter + request/response mapping.

    Returns a dict suitable for merging into a target profile. Best-effort: the
    operator is expected to review the generated YAML.
    """
    base = base_url.rstrip("/")
    result: Dict[str, Any] = {"adapter": "custom-chat", "confidence": 20}

    # OpenAI-compatible? Check /v1/models.
    ex = client.send("GET", base + "/v1/models", headers={"Accept": "application/json"})
    if ex.ok and ex.response and ex.response.status == 200 and '"object"' in ex.response.body_text:
        return {
            "adapter": "openai-chat",
            "confidence": 90,
            "request": {"method": "POST", "path": "/v1/chat/completions"},
            "response": {"reply_path": "choices[0].message.content"},
            "evidence": "GET /v1/models returned an OpenAI-style model list",
        }

    # Common custom chat shapes.
    candidates = [
        ("/api/chat", {"query": "{{prompt}}"}, "response"),
        ("/api/chat", {"message": "{{prompt}}"}, "response"),
        ("/chat", {"message": "{{prompt}}"}, "response"),
        ("/api/chat", {"messages": [{"role": "user", "content": "{{prompt}}"}]}, "response"),
        ("/api/query", {"query": "{{prompt}}"}, "answer"),
        ("/ask", {"question": "{{prompt}}"}, "answer"),
    ]
    for path, body, reply in candidates:
        ex = client.send(
            "POST",
            base + path,
            headers={"Content-Type": "application/json"},
            json_body=substitute_obj(body, {"prompt": "ping", **timeout_values}),
        )
        if ex.ok and ex.response and ex.response.status < 500:
            text = extract_text(ex.response.body_text)
            if text:
                return {
                    "adapter": "custom-chat",
                    "confidence": 60,
                    "request": {"method": "POST", "path": path, "body": body},
                    "response": {"reply_path": reply},
                    "evidence": f"POST {path} returned a text field",
                }

    return result
