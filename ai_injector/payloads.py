"""Payload model and YAML pack loader.

A payload is a small, declarative test case: a prompt template, the canary mode
that will prove success, and metadata (module, technique, tags, expected
severity if it lands).

Templates may use these variables:

    {{prompt_prefix}}      the target's legitimate task framing (optional)
    {{canary}}             the raw forward token
    {{canary_instruction}} the sentence that makes the model emit the
                           *derived* (non-reflective) canary form
    {{directive}}          convenience alias, defaults to "print"

The loader validates required fields and rejects packs that are missing a
canary mode for canary-oracle payloads, so a mis-authored pack cannot silently
degrade to "always NEGATIVE".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from .errors import PayloadError

REQUIRED_FIELDS = ("id", "module", "technique", "template")


@dataclass
class Payload:
    id: str
    module: str
    technique: str
    template: str
    mode: Optional[str] = "derive_reverse"
    oracle: str = "canary"
    severity: str = "medium"
    stage: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    markers: List[str] = field(default_factory=list)
    marker_authoritative: bool = False
    delivery: str = "direct"  # "direct" | "indirect"
    turns: List[str] = field(default_factory=list)  # multi-turn payloads
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_multiturn(self) -> bool:
        return bool(self.turns)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Payload":
        if not isinstance(data, dict):
            raise PayloadError("payload entry must be a mapping")
        missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
        if missing:
            raise PayloadError(
                f"payload {data.get('id', '<no id>')!r} missing field(s): {missing}"
            )
        turns = data.get("turns")
        if turns is not None and not isinstance(turns, list):
            raise PayloadError(f"payload {data['id']!r}: 'turns' must be a list")
        if data.get("oracle") == "canary" and not data.get("mode") and not turns:
            raise PayloadError(
                f"payload {data['id']!r}: canary oracle requires a 'mode'"
            )
        known = {
            "id", "module", "technique", "template", "mode", "oracle", "severity",
            "stage", "description", "tags", "markers", "marker_authoritative",
            "delivery", "turns",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=str(data["id"]),
            module=str(data["module"]),
            technique=str(data["technique"]),
            template=str(data["template"]),
            mode=(str(data["mode"]) if data.get("mode") else None),
            oracle=str(data.get("oracle", "canary")),
            severity=str(data.get("severity", "medium")),
            stage=str(data.get("stage", "")),
            description=str(data.get("description", "")),
            tags=list(data.get("tags") or []),
            markers=list(data.get("markers") or []),
            marker_authoritative=bool(data.get("marker_authoritative", False)),
            delivery=str(data.get("delivery", "direct")),
            turns=list(turns or []),
            extra=extra,
        )


def load_pack(path: Path) -> List[Payload]:
    if not path.exists():
        raise PayloadError(f"payload pack not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PayloadError(f"invalid YAML in {path}: {exc}") from exc
    return load_entries(data, source=str(path))


def load_entries(data: Any, source: str = "<memory>") -> List[Payload]:
    if isinstance(data, dict) and "payloads" in data:
        entries = data["payloads"]
    elif isinstance(data, list):
        entries = data
    else:
        raise PayloadError(f"{source}: expected a list or a 'payloads:' mapping")
    payloads = [Payload.from_dict(e) for e in entries]
    seen: Dict[str, int] = {}
    for p in payloads:
        seen[p.id] = seen.get(p.id, 0) + 1
    dupes = [pid for pid, n in seen.items() if n > 1]
    if dupes:
        raise PayloadError(f"{source}: duplicate payload id(s): {dupes}")
    return payloads


def filter_payloads(
    payloads: Iterable[Payload],
    *,
    module: Optional[str] = None,
    technique: Optional[str] = None,
    stage: Optional[str] = None,
    tag: Optional[str] = None,
    payload_id: Optional[str] = None,
) -> List[Payload]:
    out = []
    for p in payloads:
        if module and p.module != module:
            continue
        if technique and p.technique != technique:
            continue
        if stage and p.stage != stage:
            continue
        if tag and tag not in p.tags:
            continue
        if payload_id and p.id != payload_id:
            continue
        out.append(p)
    return out


def builtin_pack_dir() -> Path:
    return Path(__file__).with_name("payloads")


def load_builtin(module: Optional[str] = None) -> List[Payload]:
    packs = sorted(builtin_pack_dir().glob("*.yaml"))
    payloads: List[Payload] = []
    for pack in packs:
        payloads.extend(load_pack(pack))
    return filter_payloads(payloads, module=module) if module else payloads
