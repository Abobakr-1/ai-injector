"""Adapter parsing / request-building tests."""

from __future__ import annotations

import json

from ai_injector.adapters import (
    CustomChatAdapter,
    OpenAIChatAdapter,
    RawHTTPAdapter,
    SSEStreamAdapter,
    dig,
    extract_text,
    get_adapter,
    parse_sse,
)


def test_dig_paths():
    obj = {"a": {"b": [{"c": 1}]}}
    assert dig(obj, "a.b[0].c") == 1
    assert dig(obj, "a.missing") is None
    assert dig(obj, "") is obj


def test_extract_openai_shape():
    body = json.dumps({"choices": [{"message": {"content": "hi"}}]})
    assert extract_text(body, "choices[0].message.content") == "hi"


def test_extract_autodetect_response_field():
    assert extract_text('{"response": "hello"}') == "hello"
    assert extract_text('{"answer": "hey"}') == "hey"


def test_extract_plain_text_fallback():
    assert extract_text("just text") == "just text"


def test_openai_adapter_builds_messages():
    adapter = get_adapter(
        "openai-chat",
        {"url": "http://x", "request": {"path": "/v1/chat/completions"}},
    )
    built = adapter.build("payload!", {"user": "u", "session": "s"})
    assert built.method == "POST"
    assert built.url == "http://x/v1/chat/completions"
    assert built.json_body["messages"][0]["content"] == "payload!"


def test_custom_chat_adapter_requires_body():
    adapter = get_adapter("custom-chat", {"url": "http://x", "request": {"path": "/c"}})
    try:
        adapter.build("p", {})
        raise AssertionError("expected TargetError")
    except Exception as exc:  # noqa: BLE001
        assert "request.body" in str(exc)


def test_custom_chat_adapter_substitutes_identity():
    adapter = get_adapter(
        "custom-chat",
        {
            "url": "http://x",
            "request": {
                "path": "/api/chat",
                "body": {"query": "{{prompt}}", "user_id": "{{user}}"},
            },
        },
    )
    built = adapter.build("hello", {"user": "alice", "session": "s1"})
    assert built.json_body == {"query": "hello", "user_id": "alice"}


def test_sse_parse_openai_deltas():
    body = (
        'data: {"choices":[{"delta":{"content":"He"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"llo"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    assert parse_sse(body) == "Hello"


def test_sse_parse_plain_text_deltas():
    body = 'data: {"text": "wor"}\n\ndata: {"text": "ld"}\n\n'
    assert parse_sse(body) == "world"


def test_raw_http_adapter_builds_plant_request():
    adapter = get_adapter(
        "http",
        {
            "url": "http://x",
            "request": {
                "method": "POST",
                "path": "/documents",
                "body": {"title": "{{title}}", "content": "{{prompt}}"},
            },
        },
    )
    built = adapter.build("PAYLOAD", {"title": "doc"})
    assert built.url == "http://x/documents"
    assert built.json_body == {"title": "doc", "content": "PAYLOAD"}


def test_sse_adapter_sets_accept_header():
    adapter = get_adapter("sse-stream", {"url": "http://x", "request": {"path": "/s"}})
    built = adapter.build("p", {"user": "u", "session": "s"})
    assert built.headers.get("Accept") == "text/event-stream"


def test_unknown_adapter_errors():
    try:
        get_adapter("nope", {"url": "http://x"})
        raise AssertionError("expected AdapterError")
    except Exception as exc:  # noqa: BLE001
        assert "unknown adapter" in str(exc)
