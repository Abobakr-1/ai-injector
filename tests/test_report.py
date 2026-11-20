"""Report rendering tests."""

from __future__ import annotations

import json

from ai_injector.evidence import Finding
from ai_injector.report import render_json, render_markdown
from ai_injector.verdicts import Verdict


def _findings():
    return [
        Finding(
            index=1, payload_id="p1", module="direct", technique="instruction-override",
            verdict=Verdict.CONFIRMED.value, oracle="canary", detail="obeyed",
            target="t", severity="high", matched=["ABC"], request_text="req1",
            response_text="resp1", evidence_file="evidence/0001.json",
        ),
        Finding(
            index=2, payload_id="p2", module="direct", technique="jailbreak",
            verdict=Verdict.NEGATIVE.value, oracle="none", detail="no signal",
            target="t", severity="medium", request_text="req2", response_text="resp2",
        ),
        Finding(
            index=3, payload_id="p3", module="direct", technique="jailbreak",
            verdict=Verdict.ERROR.value, oracle="transport", detail="timeout",
            target="t", severity="low",
        ),
    ]


def test_markdown_has_sections_and_verdicts():
    md = render_markdown(
        target_name="t", target_url="http://x", adapter="custom-chat",
        module="direct", findings=_findings(), run_id="run1",
    )
    assert "# ai-injector report" in md
    assert "## Confirmed findings" in md
    assert "## Inconclusive" in md
    assert "## Coverage gaps" in md
    assert "CONFIRMED" in md and "NEGATIVE" in md


def test_markdown_negative_run_is_valid():
    md = render_markdown(
        target_name="t", target_url="http://x", adapter="a", module="direct",
        findings=[_findings()[1]],
    )
    assert "None. No injection produced a deterministic success signal" in md


def test_json_report_is_valid_json():
    out = render_json(
        target_name="t", target_url="http://x", adapter="a", module="direct",
        findings=_findings(), run_id="run1",
    )
    data = json.loads(out)
    assert data["summary"]["CONFIRMED"] == 1
    assert data["summary"]["NEGATIVE"] == 1
    assert data["summary"]["ERROR"] == 1
    assert len(data["findings"]) == 3


def test_confirmed_sorted_first():
    out = render_json(
        target_name="t", target_url="http://x", adapter="a", module="direct",
        findings=_findings(),
    )
    data = json.loads(out)
    assert data["findings"][0]["verdict"] == "CONFIRMED"
