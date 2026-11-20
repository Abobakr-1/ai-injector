"""Template substitution tests."""

from __future__ import annotations

import pytest

from ai_injector.template import (
    TemplateError,
    has_unresolved,
    substitute,
    substitute_obj,
)


def test_basic_substitution():
    assert substitute("hi {{name}}", {"name": "bob"}) == "hi bob"


def test_unknown_variable_errors():
    with pytest.raises(TemplateError):
        substitute("{{nope}}", {})


def test_env_substitution(monkeypatch):
    monkeypatch.setenv("AI_TEST_TOKEN", "secret-value")
    assert substitute("tok={{env:AI_TEST_TOKEN}}", {}) == "tok=secret-value"


def test_env_missing_errors():
    with pytest.raises(TemplateError):
        substitute("{{env:DEFINITELY_NOT_SET_XYZ}}", {})


def test_nested_object_substitution():
    out = substitute_obj(
        {"query": "{{prompt}}", "meta": {"u": "{{user}}"}},
        {"prompt": "p", "user": "alice"},
    )
    assert out == {"query": "p", "meta": {"u": "alice"}}


def test_unresolved_detection():
    assert has_unresolved("still {{here}}")
    assert not has_unresolved("clean")
