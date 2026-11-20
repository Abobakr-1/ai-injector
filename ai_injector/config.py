"""Configuration loading and the on-disk layout of a workspace.

A "workspace" is just a directory (default ``~/.config/ai-injector``) that holds::

    config.yaml
    targets/<name>.yaml
    runs/<timestamp>_<target>_<module>/...

Everything is plain text so an operator can audit and version it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .errors import ConfigError

ENV_HOME = "AI_INJECTOR_HOME"

DEFAULT_CONFIG: Dict[str, Any] = {
    "output_dir": None,  # resolved at runtime to <home>/runs
    "timeout": 30,
    "follow_redirects": False,
    "verify_tls": True,
    "save_raw_evidence": True,
    "scope": {
        "allow": ["127.0.0.1", "localhost", "::1"],
        "require_confirmation": True,
    },
    "oracle": {
        "canary": True,
        "rules": True,
        # Optional LLM judge endpoint (OpenAI-compatible). Off unless set.
        "judge": None,
    },
}


def default_home() -> Path:
    env = os.environ.get(ENV_HOME)
    if env:
        return Path(env).expanduser()
    return Path.home() / ".config" / "ai-injector"


@dataclass
class Config:
    """Resolved configuration for a single invocation."""

    home: Path
    output_dir: Path
    timeout: int = 30
    follow_redirects: bool = False
    verify_tls: bool = True
    save_raw_evidence: bool = True
    scope_allow: List[str] = field(default_factory=list)
    require_confirmation: bool = True
    oracle_canary: bool = True
    oracle_rules: bool = True
    judge: Optional[str] = None

    # ---- paths -----------------------------------------------------------
    @property
    def targets_dir(self) -> Path:
        return self.home / "targets"

    @property
    def config_path(self) -> Path:
        return self.home / "config.yaml"

    def target_path(self, name: str) -> Path:
        return self.targets_dir / f"{_safe_name(name)}.yaml"

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.targets_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ---- (de)serialization ----------------------------------------------
    @classmethod
    def load(cls, home: Optional[Path] = None) -> "Config":
        home = Path(home) if home else default_home()
        data = dict(DEFAULT_CONFIG)
        cfg_path = home / "config.yaml"
        if cfg_path.exists():
            try:
                loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:  # pragma: no cover - guard
                raise ConfigError(f"invalid config.yaml: {exc}") from exc
            if not isinstance(loaded, dict):
                raise ConfigError("config.yaml must be a mapping")
            _deep_merge(data, loaded)

        scope = data.get("scope") or {}
        oracle = data.get("oracle") or {}
        out = data.get("output_dir") or str(home / "runs")

        return cls(
            home=home,
            output_dir=Path(out).expanduser(),
            timeout=int(data.get("timeout", 30)),
            follow_redirects=bool(data.get("follow_redirects", False)),
            verify_tls=bool(data.get("verify_tls", True)),
            save_raw_evidence=bool(data.get("save_raw_evidence", True)),
            scope_allow=[str(h).lower() for h in scope.get("allow", [])],
            require_confirmation=bool(scope.get("require_confirmation", True)),
            oracle_canary=bool(oracle.get("canary", True)),
            oracle_rules=bool(oracle.get("rules", True)),
            judge=oracle.get("judge") or None,
        )

    def write_default(self, overwrite: bool = False) -> Path:
        """Create config.yaml if missing. Returns the path."""
        self.home.mkdir(parents=True, exist_ok=True)
        if self.config_path.exists() and not overwrite:
            return self.config_path
        to_write = dict(DEFAULT_CONFIG)
        to_write["output_dir"] = str(self.output_dir)
        self.config_path.write_text(
            yaml.safe_dump(to_write, sort_keys=False), encoding="utf-8"
        )
        return self.config_path


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _safe_name(name: str) -> str:
    keep = "-_."
    cleaned = "".join(c for c in name if c.isalnum() or c in keep)
    if not cleaned:
        raise ConfigError(f"invalid target name: {name!r}")
    return cleaned
