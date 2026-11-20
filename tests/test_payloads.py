"""Payload pack loading and validation tests."""

from __future__ import annotations

import pytest

from ai_injector.errors import PayloadError
from ai_injector.payloads import (
    Payload,
    filter_payloads,
    load_builtin,
    load_entries,
)


def test_builtin_packs_load():
    payloads = load_builtin()
    assert len(payloads) >= 40
    modules = {p.module for p in payloads}
    assert modules == {"direct", "indirect"}


def test_direct_covers_all_techniques():
    from ai_injector.modules.direct import TECHNIQUES

    payloads = filter_payloads(load_builtin(), module="direct")
    covered = {p.technique for p in payloads}
    assert set(TECHNIQUES) <= covered


def test_indirect_covers_techniques():
    from ai_injector.modules.indirect import TECHNIQUES

    payloads = filter_payloads(load_builtin(), module="indirect")
    covered = {p.technique for p in payloads}
    # multi-source is present as its own technique id in the pack
    assert "retrieved-document-injection" in covered
    assert "rag-context-injection" in covered
    assert "cross-session" in covered
    assert len(payloads) >= 14


def test_required_fields_enforced():
    with pytest.raises(PayloadError):
        load_entries([{"id": "x", "module": "direct"}])


def test_canary_oracle_requires_mode():
    with pytest.raises(PayloadError):
        load_entries(
            [{"id": "x", "module": "direct", "technique": "t", "template": "hi", "oracle": "canary"}]
        )


def test_duplicate_ids_rejected():
    with pytest.raises(PayloadError):
        load_entries(
            [
                {"id": "dup", "module": "direct", "technique": "t", "template": "a"},
                {"id": "dup", "module": "direct", "technique": "t", "template": "b"},
            ]
        )


def test_multiturn_payload_parsed():
    p = Payload.from_dict(
        {
            "id": "mt",
            "module": "direct",
            "technique": "multi-turn",
            "template": "(final)",
            "turns": ["a", "b", "c"],
        }
    )
    assert p.is_multiturn
    assert p.turns[-1] == "c"


def test_every_builtin_payload_has_oracle_and_mode():
    for p in load_builtin():
        if p.oracle == "canary" and not p.is_multiturn:
            assert p.mode, f"{p.id} missing mode"
        assert p.template, f"{p.id} missing template"
