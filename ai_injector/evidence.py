"""Evidence store: append-only, per-run, on-disk record of everything tested.

Layout::

    runs/2026-11-20T17-55-00Z_aurora_direct/
        run.json            run metadata + summary
        findings.json       the ledger (one entry per attempt)
        evidence/
            0001_<payload-id>.json     raw request + response
            ...
        report.md           generated on demand

Design: raw request/response pairs are written immediately and never mutated.
The ledger references evidence by relative filename so a report is portable.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .verdicts import Verdict


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)[:80]


@dataclass
class Finding:
    index: int
    payload_id: str
    module: str
    technique: str
    verdict: str
    oracle: str
    detail: str
    target: str
    identity: str = ""
    severity: str = "medium"
    stage: str = ""
    matched: List[str] = field(default_factory=list)
    evidence_file: str = ""
    request_text: str = ""
    response_text: str = ""
    error: str = ""
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def verdict_enum(self) -> Verdict:
        return Verdict(self.verdict)

    @property
    def finding_id(self) -> str:
        return f"F-{self.index:03d}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunMeta:
    run_id: str
    target: str
    target_url: str
    adapter: str
    module: str
    started_at: str
    finished_at: str = ""
    options: Dict[str, Any] = field(default_factory=dict)


class EvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.evidence_dir = self.root / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0
        self.findings: List[Finding] = []
        self.meta: Optional[RunMeta] = None

    # ---- lifecycle -------------------------------------------------------
    def start(self, meta: RunMeta) -> None:
        self.meta = meta
        self.root.mkdir(parents=True, exist_ok=True)
        self.write_run()

    def write_run(self) -> None:
        if self.meta is None:
            return
        (self.root / "run.json").write_text(
            json.dumps(asdict(self.meta), indent=2), encoding="utf-8"
        )

    def finish(self) -> None:
        if self.meta is not None:
            self.meta.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.write_run()
        # Rewrite run.json with the summary included.
        summary = self.summary()
        if self.meta is not None:
            payload = asdict(self.meta)
            payload["summary"] = summary
            (self.root / "run.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        (self.root / "findings.json").write_text(
            json.dumps([f.to_dict() for f in self.findings], indent=2),
            encoding="utf-8",
        )

    # ---- records ---------------------------------------------------------
    def record_exchange(self, payload_id: str, exchange: Dict[str, Any]) -> str:
        self._counter += 1
        fname = f"{self._counter:04d}_{_safe(payload_id)}.json"
        (self.evidence_dir / fname).write_text(
            json.dumps(exchange, indent=2), encoding="utf-8"
        )
        return f"evidence/{fname}"

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    # ---- summary ---------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        counts = {v.value: 0 for v in Verdict}
        for f in self.findings:
            counts[f.verdict] = counts.get(f.verdict, 0) + 1
        return {
            "total": len(self.findings),
            "counts": counts,
            "confirmed": counts.get(Verdict.CONFIRMED.value, 0),
            "has_findings": counts.get(Verdict.CONFIRMED.value, 0) > 0,
        }
