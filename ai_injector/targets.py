"""Target profiles: the readable contract describing how to talk to one AI
surface, plus the authorization confirmation state.

A profile is YAML on disk (``<home>/targets/<name>.yaml``). Example::

    name: aurora
    url: http://127.0.0.1:5000
    adapter: custom-chat
    authorization:
      confirmed: true
      basis: "owned lab"
      confirmed_at: "2026-11-20T17:00:00Z"
    request:
      method: POST
      path: /api/chat
      body:
        query: "{{prompt}}"
        user_id: "{{user}}"
        session_id: "{{session}}"
    response:
      reply_path: response
    identities:
      - name: alice
        user: alice
        session: sess-alice
    headers:
      X-Trace: "ai-injector"
    # Optional, for the indirect module:
    indirect:
      plant:
        method: POST
        path: /documents
        body:
          title: "{{title}}"
          content: "{{prompt}}"
      trigger:
        method: POST
        path: /api/chat
        body:
          query: "{{prompt}}"
          user_id: "{{user}}"
      marker: "AIJC-INDIRECT-OK"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .errors import TargetError


@dataclass
class Identity:
    name: str
    user: str = ""
    session: str = ""

    def values(self) -> Dict[str, str]:
        return {"user": self.user, "session": self.session}


@dataclass
class Authorization:
    confirmed: bool = False
    basis: str = ""
    confirmed_at: str = ""


@dataclass
class Target:
    name: str
    url: str
    adapter: str = "openai-chat"
    request: Dict[str, Any] = field(default_factory=dict)
    response: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, Any] = field(default_factory=dict)
    identities: List[Identity] = field(default_factory=list)
    authorization: Authorization = field(default_factory=Authorization)
    indirect: Dict[str, Any] = field(default_factory=dict)
    model: str = ""
    description: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    # ---- convenience -----------------------------------------------------
    @property
    def confirmed(self) -> bool:
        return bool(self.authorization.confirmed)

    def identity(self, name: Optional[str]) -> Identity:
        if not self.identities:
            return Identity(name=name or "default", user="user", session="")
        if name:
            for ident in self.identities:
                if ident.name == name:
                    return ident
            raise TargetError(
                f"identity {name!r} not defined; available: "
                f"{[i.name for i in self.identities]}"
            )
        return self.identities[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "adapter": self.adapter,
            "model": self.model,
            "description": self.description,
            "request": self.request,
            "response": self.response,
            "headers": self.headers,
            "identities": [i.__dict__ for i in self.identities],
            "authorization": self.authorization.__dict__,
            "indirect": self.indirect,
        }

    # ---- (de)serialization ----------------------------------------------
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Target":
        if not isinstance(data, dict):
            raise TargetError("target profile must be a mapping")
        name = data.get("name")
        url = data.get("url")
        if not name:
            raise TargetError("target profile missing 'name'")
        if not url:
            raise TargetError(f"target {name!r} missing 'url'")

        auth_raw = data.get("authorization") or {}
        auth = Authorization(
            confirmed=bool(auth_raw.get("confirmed", False)),
            basis=str(auth_raw.get("basis", "")),
            confirmed_at=str(auth_raw.get("confirmed_at", "")),
        )

        identities = []
        for item in data.get("identities") or []:
            if isinstance(item, str):
                identities.append(Identity(name=item, user=item))
            elif isinstance(item, dict):
                identities.append(
                    Identity(
                        name=str(item.get("name", "default")),
                        user=str(item.get("user", item.get("name", ""))),
                        session=str(item.get("session", "")),
                    )
                )

        return cls(
            name=str(name),
            url=str(url),
            adapter=str(data.get("adapter", "openai-chat")),
            request=data.get("request") or {},
            response=data.get("response") or {},
            headers=data.get("headers") or {},
            identities=identities,
            authorization=auth,
            indirect=data.get("indirect") or {},
            model=str(data.get("model", "")),
            description=str(data.get("description", "")),
            raw=data,
        )

    @classmethod
    def load(cls, path: Path) -> "Target":
        if not path.exists():
            raise TargetError(f"target profile not found: {path}")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise TargetError(f"invalid YAML in {path}: {exc}") from exc
        return cls.from_dict(data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def confirm(self, basis: str) -> None:
        self.authorization = Authorization(
            confirmed=True,
            basis=basis,
            confirmed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
