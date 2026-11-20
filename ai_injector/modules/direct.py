"""MODULE 1 -- Direct prompt injection.

Scope: manipulating AI behavior through *user-controlled input*. The attacker
controls the user turn (and, optionally, earlier turns of the conversation). The
payload lands in the message the application sends to the model.

Developed techniques (see ``ai_injector/payloads/direct.yaml`` for the library):

* Instruction override            -- "ignore previous instructions" and variants
* Role manipulation               -- "you are now X" persona takeover
* Delimiter injection             -- fake system/assistant blocks, fences, tags
* System prompt extraction        -- ask the model to reveal its configuration
* Jailbreak techniques            -- DAN-style, hypothetical framing, encoding
* Multi-turn prompt injection     -- gradual escalation across turns
* Context manipulation            -- overflow / attention steering
* Payload variations and chaining -- layered payloads that stack techniques

The engine owns detection; this module owns delivery and technique coverage.
All direct payloads use the ``direct`` deliverer (send as the user turn).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..payloads import Payload, filter_payloads, load_builtin, load_pack

MODULE = "direct"

#: The techniques this module is responsible for.
TECHNIQUES = [
    "instruction-override",
    "role-manipulation",
    "delimiter-injection",
    "system-prompt-extraction",
    "jailbreak",
    "multi-turn",
    "context-manipulation",
    "chaining",
]


def load_payloads(
    *,
    extra_packs: Optional[List[Path]] = None,
    technique: Optional[str] = None,
    stage: Optional[str] = None,
    tag: Optional[str] = None,
    payload_id: Optional[str] = None,
) -> List[Payload]:
    payloads = filter_payloads(load_builtin(), module=MODULE)
    for pack in extra_packs or []:
        payloads.extend(
            filter_payloads(load_pack(Path(pack)), module=MODULE)
        )
    return filter_payloads(
        payloads, technique=technique, stage=stage, tag=tag, payload_id=payload_id
    )
