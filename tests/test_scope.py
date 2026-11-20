"""Scope-guard tests."""

from __future__ import annotations

import pytest

from ai_injector.errors import ScopeError
from ai_injector.scope import check, enforce, host_in_allowlist, host_of


def test_host_extraction():
    assert host_of("http://127.0.0.1:5000/api") == "127.0.0.1"
    assert host_of("https://API.Example.com/x") == "api.example.com"


def test_allowlist_exact_and_wildcard():
    allow = ["127.0.0.1", ".example.com"]
    assert host_in_allowlist("http://127.0.0.1:1/", allow)
    assert host_in_allowlist("http://api.example.com/", allow)
    assert host_in_allowlist("http://example.com/", allow)
    # suffix trap: not a real subdomain of example.com
    assert not host_in_allowlist("http://example.com.evil.tld/", allow)


def test_check_requires_confirmation():
    d = check("http://127.0.0.1:5000/", ["127.0.0.1"], confirmed=False, require_confirmation=True)
    assert not d.allowed
    assert "confirmed" in d.reason


def test_check_blocks_out_of_scope_host():
    d = check("http://evil.tld/", ["127.0.0.1"], confirmed=True)
    assert not d.allowed
    assert "allowlist" in d.reason


def test_enforce_raises():
    with pytest.raises(ScopeError):
        enforce("http://evil.tld/", ["127.0.0.1"], confirmed=True)


def test_enforce_passes_when_confirmed_and_allowed():
    enforce("http://127.0.0.1/", ["127.0.0.1"], confirmed=True)  # no raise


def test_confirmation_can_be_disabled():
    d = check("http://127.0.0.1/", ["127.0.0.1"], confirmed=False, require_confirmation=False)
    assert d.allowed
