"""Shared test fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_injector.config import Config  # noqa: E402
from ai_injector.http import CapturedRequest, CapturedResponse, Exchange  # noqa: E402
from ai_injector.targets import Target  # noqa: E402


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    (h / "targets").mkdir(parents=True)
    (h / "runs").mkdir(parents=True)
    return h


@pytest.fixture
def config(home: Path) -> Config:
    cfg = Config(home=home, output_dir=home / "runs")
    cfg.scope_allow = ["127.0.0.1", "localhost"]
    cfg.require_confirmation = True
    cfg.save_raw_evidence = True
    return cfg


@pytest.fixture
def target() -> Target:
    t = Target.from_dict(
        {
            "name": "t",
            "url": "http://127.0.0.1:5000",
            "adapter": "custom-chat",
            "request": {
                "method": "POST",
                "path": "/api/chat",
                "body": {"query": "{{prompt}}"},
            },
            "response": {"reply_path": "response"},
            "identities": [{"name": "default", "user": "u", "session": "s"}],
        }
    )
    t.confirm("test")
    return t


def make_exchange(
    url: str = "http://127.0.0.1:5000/api/chat",
    body: str = '{"response": "hello"}',
    status: int = 200,
    ok: bool = True,
    error: str | None = None,
) -> Exchange:
    return Exchange(
        request=CapturedRequest("POST", url, {"Content-Type": "application/json"}, {"query": "x"}),
        response=(
            CapturedResponse(status, {"Content-Type": "application/json"}, body, 5)
            if ok
            else None
        ),
        error=error,
        ok=ok,
    )


class FakeClient:
    """Records requests and replays scripted replies.

    ``responses`` may be a single string (used for every call) or a list of
    strings consumed in order; the last value repeats.
    """

    def __init__(self, responses):
        if isinstance(responses, str):
            responses = [responses]
        self.responses = responses
        self.calls = []

    def send(self, method, url, headers=None, json_body=None, data=None):
        self.calls.append({"method": method, "url": url, "json_body": json_body, "data": data})
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        body = self.responses[idx]
        if isinstance(body, dict):
            body = json.dumps(body)
        return Exchange(
            request=CapturedRequest(method, url, dict(headers or {}), json_body),
            response=CapturedResponse(200, {"Content-Type": "application/json"}, body, 3),
            ok=True,
        )
