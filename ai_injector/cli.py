"""ai-injector command-line interface.

Commands
--------
init                     create the workspace config
doctor                   check the environment
targets add|list|show    manage target profiles
scope confirm|check      record / verify authorization
profile <target>         quick surface probe (reachability + adapter sanity)
attacks list             show available modules/techniques/payloads
run <target>             execute an attack module
findings [run]           list findings from a run
show <run> <id>          full detail + evidence for one finding
replay <run> <id>        re-send the exact request and re-judge
report [run]             emit a markdown/JSON report
payloads where           print the built-in payload directory

Exit codes
----------
0   ran normally, no confirmed findings
1   error (config/scope/target)
10  at least one CONFIRMED finding (CI-friendly)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .adapters import detect_adapter, get_adapter
from .banner import banner, short_banner
from .config import Config, default_home
from .engine import Engine, RunOptions
from .errors import AIInjectorError, ScopeError
from .evidence import EvidenceStore, Finding
from .http import HttpClient
from .modules import direct as direct_mod
from .modules import indirect as indirect_mod
from .payloads import builtin_pack_dir, load_builtin
from .report import write_report
from .scope import check
from .targets import Target
from .verdicts import Verdict

EXIT_OK = 0
EXIT_ERR = 1
EXIT_FINDINGS = 10


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _out(msg: str = "") -> None:
    print(msg)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _config(args: argparse.Namespace) -> Config:
    home = Path(args.home).expanduser() if getattr(args, "home", None) else default_home()
    cfg = Config.load(home)
    if getattr(args, "timeout", None):
        cfg.timeout = int(args.timeout)
    if getattr(args, "judge", None):
        cfg.judge = args.judge
    return cfg


def _load_target(cfg: Config, name: str) -> Target:
    return Target.load(cfg.target_path(name))


def _normalize_request_path(path: Optional[str]) -> Optional[str]:
    """Repair paths mangled by MSYS/Git-Bash POSIX-to-Windows conversion.

    Git Bash rewrites a bare ``/api/chat`` argument into
    ``C:/Program Files/Git/api/chat`` before Python ever sees it. We detect that
    prefix and restore the original URL path so profiles stay correct regardless
    of the shell. (Users can also set MSYS_NO_PATHCONV=1.)
    """
    if not path:
        return path
    import re as _re

    original = path
    # Strip a "<drive>:/Program Files/Git" or generic "<drive>:/.../<msys root>" prefix.
    m = _re.match(r"^[A-Za-z]:/(?:Program Files/)?Git(?P<rest>/.*)$", path)
    if m:
        path = m.group("rest")
    elif _re.match(r"^[A-Za-z]:/", path) and "/api/" in path:
        path = path[path.index("/api/"):]
    if path != original and not path.startswith("/"):
        path = "/" + path
    return path


def _platform() -> str:
    import platform as _p

    system = _p.system()
    if system == "Linux":
        try:
            import pathlib

            if "kali" in pathlib.Path("/etc/os-release").read_text(encoding="utf-8", errors="ignore").lower():
                return "Kali Linux"
        except Exception:  # noqa: BLE001
            pass
        return "Linux"
    return system


def _module_loader(module: str):
    return direct_mod if module == "direct" else indirect_mod


def _latest_run(cfg: Config) -> Optional[Path]:
    if not cfg.output_dir.exists():
        return None
    runs = sorted([p for p in cfg.output_dir.iterdir() if p.is_dir()])
    return runs[-1] if runs else None


def _load_findings(run_dir: Path) -> List[Finding]:
    path = run_dir / "findings.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Finding(**{k: v for k, v in item.items()}) for item in data]


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    cfg = _config(args)
    cfg.ensure_dirs()
    path = cfg.write_default(overwrite=args.force)
    _out(banner(_platform()))
    _out("")
    _out(f"[+] workspace: {cfg.home}")
    _out(f"[+] config   : {path}")
    _out(f"[+] targets  : {cfg.targets_dir}")
    _out(f"[+] runs     : {cfg.output_dir}")
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = _config(args)
    _out("ai-injector doctor")
    _out(f"  version      : {__version__}")
    _out(f"  python       : {sys.version.split()[0]}")
    try:
        import requests  # noqa: F401

        _out("  requests     : present")
    except Exception as exc:  # noqa: BLE001
        _out(f"  requests     : MISSING ({exc})")
    try:
        import yaml  # noqa: F401

        _out("  pyyaml       : present")
    except Exception as exc:  # noqa: BLE001
        _out(f"  pyyaml       : MISSING ({exc})")
    _out(f"  home         : {cfg.home}")
    _out(f"  config       : {cfg.config_path if cfg.config_path.exists() else 'not created (run: ai-injector init)'}")
    _out(f"  scope allow  : {cfg.scope_allow}")
    _out(f"  require conf : {cfg.require_confirmation}")
    _out(f"  judge        : {cfg.judge or 'disabled'}")
    try:
        packs = sorted(p.name for p in builtin_pack_dir().glob('*.yaml'))
        _out(f"  payload packs: {', '.join(packs) if packs else 'none'}")
        total = len(load_builtin())
        _out(f"  payloads     : {total} loaded")
    except Exception as exc:  # noqa: BLE001
        _out(f"  payloads     : ERROR ({exc})")
    return EXIT_OK


def cmd_targets_add(args: argparse.Namespace) -> int:
    cfg = _config(args)
    cfg.ensure_dirs()

    decision = check(args.url, cfg.scope_allow, confirmed=True, require_confirmation=False)
    if not decision.allowed:
        _err(f"[!] scope: {decision.reason}")
        _err("    add the host to scope.allow in config.yaml if this is authorized")
        return EXIT_ERR

    path = _normalize_request_path(args.path)
    profile = {
        "name": args.name,
        "url": args.url.rstrip("/"),
        "adapter": args.adapter or "openai-chat",
        "description": args.description or "",
        "request": {"method": "POST", "path": path or "/v1/chat/completions"},
        "response": {"reply_path": args.reply_path or "choices[0].message.content"},
        "identities": [{"name": "default", "user": "ai-injector", "session": "sess-1"}],
    }
    if args.adapter in (None, "custom-chat", "sse-stream") and path:
        # For a custom chat surface we must describe the request body. Default to
        # a single {{prompt}} field (configurable with --query-field), plus any
        # identity fields the user asked to include.
        qfield = args.query_field or "query"
        body = {qfield: "{{prompt}}"}
        if args.with_identity:
            body["user_id"] = "{{user}}"
            body["session_id"] = "{{session}}"
        profile["request"]["body"] = body
    if args.model:
        profile["model"] = args.model
    for header in args.header or []:
        if ":" in header:
            k, v = header.split(":", 1)
            profile.setdefault("headers", {})[k.strip()] = v.strip()

    if not args.adapter:  # autodetect
        client = HttpClient(timeout=cfg.timeout, verify_tls=cfg.verify_tls)
        _out(f"[*] probing {args.url} ...")
        detected = detect_adapter(client, args.url.rstrip("/"), {"user": "ai-injector", "session": "sess-1"})
        _out(f"[+] adapter: {detected['adapter']} (confidence {detected.get('confidence', 0)})")
        if detected.get("evidence"):
            _out(f"    evidence: {detected['evidence']}")
        profile["adapter"] = detected["adapter"]
        if detected.get("request"):
            profile["request"] = detected["request"]
        if detected.get("response"):
            profile["response"] = detected["response"]

    target = Target.from_dict(profile)
    path = cfg.target_path(args.name)
    target.save(path)
    _out(f"[+] saved: {path}")
    _out(f"[!] confirm authorization: ai-injector scope confirm {args.name} --owned")
    return EXIT_OK


def cmd_targets_list(args: argparse.Namespace) -> int:
    cfg = _config(args)
    if not cfg.targets_dir.exists() or not any(cfg.targets_dir.glob("*.yaml")):
        _out("(no targets yet — add one with: ai-injector targets add <name> --url <url>)")
        return EXIT_OK
    _out(f"{'NAME':<20} {'ADAPTER':<14} {'CONFIRMED':<10} URL")
    for path in sorted(cfg.targets_dir.glob("*.yaml")):
        try:
            t = Target.load(path)
        except AIInjectorError as exc:
            _out(f"{path.stem:<20} (error: {exc})")
            continue
        _out(f"{t.name:<20} {t.adapter:<14} {str(t.confirmed):<10} {t.url}")
    return EXIT_OK


def cmd_targets_show(args: argparse.Namespace) -> int:
    cfg = _config(args)
    t = _load_target(cfg, args.name)
    _out(json.dumps(t.to_dict(), indent=2))
    return EXIT_OK


def cmd_scope_confirm(args: argparse.Namespace) -> int:
    cfg = _config(args)
    t = _load_target(cfg, args.name)
    decision = check(t.url, cfg.scope_allow, confirmed=True, require_confirmation=False)
    if not decision.allowed:
        _err(f"[!] refusing: {decision.reason}")
        return EXIT_ERR
    basis = "owned" if args.owned else (args.basis or "operator-confirmed")
    if not (args.owned or args.basis):
        _err("[!] pass --owned or --basis \"<engagement/program>\" to record why this is authorized")
        return EXIT_ERR
    t.confirm(basis)
    t.save(cfg.target_path(args.name))
    _out(f"[+] {t.name}: authorized ({basis}) at {t.authorization.confirmed_at}")
    return EXIT_OK


def cmd_scope_check(args: argparse.Namespace) -> int:
    cfg = _config(args)
    t = _load_target(cfg, args.name)
    d = check(t.url, cfg.scope_allow, t.confirmed, cfg.require_confirmation)
    _out(f"target : {t.name} ({t.url})")
    _out(f"allowed: {d.allowed}")
    _out(f"reason : {d.reason}")
    return EXIT_OK if d.allowed else EXIT_ERR


def cmd_profile(args: argparse.Namespace) -> int:
    cfg = _config(args)
    t = _load_target(cfg, args.name)
    decision = check(t.url, cfg.scope_allow, t.confirmed, cfg.require_confirmation)
    if not decision.allowed:
        _err(f"[!] scope: {decision.reason}")
        return EXIT_ERR
    client = HttpClient(timeout=cfg.timeout, verify_tls=cfg.verify_tls)
    _out(f"[+] surface map — {t.name} ({t.url})")

    ex = client.send("GET", t.url.rstrip("/") + "/health", headers={"Accept": "application/json"})
    if ex.ok and ex.response:
        _out(f"    /health           HTTP {ex.response.status}")
    else:
        _out(f"    /health           unreachable ({ex.error})")

    try:
        adapter = get_adapter(t.adapter, t.to_dict())
        built = adapter.build("Hello, respond with a short greeting.", {"user": "ai-injector", "session": "probe"})
        ex = client.send(built.method, built.url, headers=built.headers, json_body=built.json_body, data=built.data)
        if ex.ok and ex.response:
            reply = adapter.parse(ex.response.body_text)
            _out(f"    chat probe        HTTP {ex.response.status}, reply={len(reply or '')} chars")
        else:
            _out(f"    chat probe        failed ({ex.error})")
    except Exception as exc:  # noqa: BLE001
        _out(f"    chat probe        error: {exc}")

    has_indirect = bool((t.indirect or {}).get("plant"))
    _out(f"    indirect plant    {'configured' if has_indirect else 'not configured'}")
    _out(f"    identities        {[i.name for i in t.identities] or ['(none defined)']}")
    _out("    candidate modules : direct" + (", indirect" if has_indirect else ""))
    return EXIT_OK


def cmd_attacks_list(args: argparse.Namespace) -> int:
    payloads = load_builtin()
    by_module: dict = {}
    for p in payloads:
        by_module.setdefault(p.module, {}).setdefault(p.technique, 0)
        by_module[p.module][p.technique] += 1
    _out("MODULES AND TECHNIQUES")
    for module in sorted(by_module):
        total = sum(by_module[module].values())
        _out(f"\n  {module}  ({total} payloads)")
        for tech, n in sorted(by_module[module].items()):
            _out(f"    {tech:<34} {n}")
    _out("\nFilter with: ai-injector run <target> --module direct --technique <t> --tag <tag>")
    return EXIT_OK


def cmd_payloads_where(args: argparse.Namespace) -> int:
    _out(str(builtin_pack_dir()))
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _config(args)
    if args.module not in ("direct", "indirect"):
        _err(f"[!] unknown module {args.module!r}; choose 'direct' or 'indirect'")
        return EXIT_ERR

    t = _load_target(cfg, args.target)
    loader = _module_loader(args.module)
    extra = [Path(p) for p in (args.payloads or [])]
    payloads = loader.load_payloads(
        extra_packs=extra,
        technique=args.technique,
        stage=args.stage,
        tag=args.tag,
        payload_id=args.payload_id,
    )
    if not payloads:
        _err("[!] no payloads matched the given filters")
        return EXIT_ERR

    deliverer = None
    if args.module == "indirect":
        from .modules.indirect import PlantTriggerDeliverer

        if not (t.indirect or {}).get("plant"):
            _err("[!] indirect module needs 'indirect.plant' in the target profile")
            _err(f"    edit {cfg.target_path(args.target)} and add an indirect: section")
            return EXIT_ERR
        deliverer = PlantTriggerDeliverer(t)

    options = RunOptions(
        module=args.module,
        dry_run=args.dry_run,
        stop_on_confirm=args.stop_on_confirm,
        identity=args.identity,
        stage=args.stage or "",
        save_raw_evidence=cfg.save_raw_evidence,
    )
    engine = Engine(cfg, t, deliverer=deliverer, log=_out)
    try:
        result = engine.run(payloads, options)
    except ScopeError as exc:
        _err(f"[!] scope blocked: {exc}")
        return EXIT_ERR

    if args.report:
        _emit_report(cfg, t, args.module, result.store)

    confirmed = result.summary["counts"].get("CONFIRMED", 0)
    return EXIT_FINDINGS if confirmed else EXIT_OK


def _emit_report(cfg: Config, t: Target, module: str, store: EvidenceStore) -> None:
    meta = store.meta
    run_id = meta.run_id if meta else ""
    md = write_report(
        store.root,
        fmt="md",
        target_name=t.name,
        target_url=t.url,
        adapter=t.adapter,
        module=module,
        findings=store.findings,
        run_id=run_id,
    )
    write_report(
        store.root,
        fmt="json",
        target_name=t.name,
        target_url=t.url,
        adapter=t.adapter,
        module=module,
        findings=store.findings,
        run_id=run_id,
    )
    _out(f"[+] reports -> {md} , {store.root / 'report.json'}")


def cmd_findings(args: argparse.Namespace) -> int:
    cfg = _config(args)
    run_dir = Path(args.run) if args.run else _latest_run(cfg)
    if run_dir is None or not run_dir.exists():
        _err("[!] no runs found")
        return EXIT_ERR
    findings = _load_findings(run_dir)
    if not findings:
        _out("(no findings in this run)")
        return EXIT_OK
    _out(f"run: {run_dir.name}")
    _out(f"{'ID':<8} {'VERDICT':<13} {'ORACLE':<8} {'SEV':<9} PAYLOAD")
    for f in findings:
        _out(f"{f.finding_id:<8} {f.verdict:<13} {f.oracle:<8} {f.severity:<9} {f.payload_id}")
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    cfg = _config(args)
    run_dir = Path(args.run) if args.run else _latest_run(cfg)
    if run_dir is None or not run_dir.exists():
        _err("[!] run not found")
        return EXIT_ERR
    findings = _load_findings(run_dir)
    match = [f for f in findings if f.finding_id == args.id or f.payload_id == args.id]
    if not match:
        _err(f"[!] finding {args.id!r} not found in {run_dir.name}")
        return EXIT_ERR
    f = match[0]
    _out(json.dumps(f.to_dict(), indent=2))
    if f.evidence_file:
        ev = run_dir / f.evidence_file
        if ev.exists():
            _out("")
            _out(f"--- raw evidence ({f.evidence_file}) ---")
            _out(ev.read_text(encoding="utf-8")[:4000])
    return EXIT_OK


def cmd_replay(args: argparse.Namespace) -> int:
    cfg = _config(args)
    run_dir = Path(args.run) if args.run else _latest_run(cfg)
    if run_dir is None or not run_dir.exists():
        _err("[!] run not found")
        return EXIT_ERR
    findings = _load_findings(run_dir)
    match = [f for f in findings if f.finding_id == args.id or f.payload_id == args.id]
    if not match:
        _err(f"[!] finding {args.id!r} not found")
        return EXIT_ERR
    f = match[0]
    ev_path = run_dir / f.evidence_file if f.evidence_file else None
    if not ev_path or not ev_path.exists():
        _err("[!] no raw evidence stored for this finding; cannot replay")
        return EXIT_ERR
    ev = json.loads(ev_path.read_text(encoding="utf-8"))
    req = ev.get("request") or {}

    t = _load_target(cfg, f.target)
    decision = check(req.get("url", t.url), cfg.scope_allow, t.confirmed, cfg.require_confirmation)
    if not decision.allowed:
        _err(f"[!] scope: {decision.reason}")
        return EXIT_ERR

    client = HttpClient(timeout=cfg.timeout, verify_tls=cfg.verify_tls)
    _out(f"[*] replaying {f.payload_id} -> {req.get('method')} {req.get('url')}")
    ex = client.send(
        req.get("method", "POST"),
        req.get("url", t.url),
        headers=req.get("headers") or {},
        json_body=req.get("body") if not isinstance(req.get("body"), str) else None,
        data=req.get("body") if isinstance(req.get("body"), str) else None,
    )
    if not ex.ok or ex.response is None:
        _err(f"[!] replay transport error: {ex.error}")
        return EXIT_ERR

    adapter = get_adapter(t.adapter, t.to_dict())
    reply = adapter.parse(ex.response.body_text)
    _out(f"[+] HTTP {ex.response.status} · {ex.response.elapsed_ms} ms")
    _out("--- response excerpt ---")
    _out((reply or ex.response.body_text)[:1500])
    if f.matched:
        still = [m for m in f.matched if m in (reply or "")]
        _out(f"[+] originally-matched marker(s) still present: {still or 'NONE'}")
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    cfg = _config(args)
    run_dir = Path(args.run) if args.run else _latest_run(cfg)
    if run_dir is None or not run_dir.exists():
        _err("[!] no runs found")
        return EXIT_ERR
    findings = _load_findings(run_dir)
    meta = {}
    run_json = run_dir / "run.json"
    if run_json.exists():
        meta = json.loads(run_json.read_text(encoding="utf-8"))
    path = write_report(
        run_dir,
        fmt=args.format,
        target_name=meta.get("target", "unknown"),
        target_url=meta.get("target_url", ""),
        adapter=meta.get("adapter", ""),
        module=meta.get("module", ""),
        findings=findings,
        run_id=meta.get("run_id", run_dir.name),
    )
    _out(f"[+] wrote {path}")
    if args.stdout:
        _out("")
        _out(path.read_text(encoding="utf-8"))
    return EXIT_OK


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-injector",
        description=(
            "AI INJECTOR — offensive prompt-injection testing harness "
            "(direct + indirect). Developed by AboBakr Mohamed."
        ),
    )
    parser.add_argument("--version", action="version", version=f"ai-injector {__version__}")
    parser.add_argument("--home", help="workspace directory (default ~/.config/ai-injector)")
    parser.add_argument("--timeout", type=int, help="request timeout in seconds")
    parser.add_argument("--judge", help="optional OpenAI-compatible judge endpoint URL")
    parser.add_argument("--no-banner", action="store_true", help="suppress the banner")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the workspace config")
    p.add_argument("--force", action="store_true", help="overwrite existing config")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("doctor", help="check the environment")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("targets", help="manage target profiles")
    tsub = p.add_subparsers(dest="targets_command", required=True)

    pa = tsub.add_parser("add", help="register a target")
    pa.add_argument("name")
    pa.add_argument("--url", required=True)
    pa.add_argument("--adapter", help="openai-chat|custom-chat|sse-stream|http (default: autodetect)")
    pa.add_argument("--path", help="request path")
    pa.add_argument("--query-field", help="JSON field carrying the prompt (default: query)")
    pa.add_argument("--with-identity", action="store_true", help="also send user_id/session_id from {{user}}/{{session}}")
    pa.add_argument("--reply-path", help="JSON path to the reply field")
    pa.add_argument("--model", help="model name")
    pa.add_argument("--description", help="free-text note")
    pa.add_argument("--header", action="append", help='extra header "Key: Value" (repeatable)')
    pa.set_defaults(func=cmd_targets_add)

    pl = tsub.add_parser("list", help="list targets")
    pl.set_defaults(func=cmd_targets_list)

    ps = tsub.add_parser("show", help="show a target profile")
    ps.add_argument("name")
    ps.set_defaults(func=cmd_targets_show)

    p = sub.add_parser("scope", help="authorization / scope checks")
    ssub = p.add_subparsers(dest="scope_command", required=True)
    sc = ssub.add_parser("confirm", help="record authorization for a target")
    sc.add_argument("name")
    sc.add_argument("--owned", action="store_true", help="target is owned/operated by you")
    sc.add_argument("--basis", help="engagement / program / authorization note")
    sc.set_defaults(func=cmd_scope_confirm)
    sk = ssub.add_parser("check", help="evaluate the scope guard")
    sk.add_argument("name")
    sk.set_defaults(func=cmd_scope_check)

    p = sub.add_parser("profile", help="quick surface probe")
    p.add_argument("name")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("attacks", help="inspect payload coverage")
    asub = p.add_subparsers(dest="attacks_command", required=True)
    al = asub.add_parser("list", help="list modules/techniques")
    al.set_defaults(func=cmd_attacks_list)

    p = sub.add_parser("run", help="execute an attack module")
    p.add_argument("target")
    p.add_argument("--module", required=True, choices=["direct", "indirect"])
    p.add_argument("--technique", help="only this technique")
    p.add_argument("--stage", help="only payloads tagged with this stage")
    p.add_argument("--tag", help="only payloads with this tag")
    p.add_argument("--payload-id", help="run a single payload id")
    p.add_argument("--payloads", action="append", help="extra payload pack file (repeatable)")
    p.add_argument("--identity", help="identity name from the target profile")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--stop-on-confirm", action="store_true")
    p.add_argument("--report", action="store_true", help="write md+json report after the run")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("findings", help="list findings for a run")
    p.add_argument("run", nargs="?", help="run directory (default: latest)")
    p.set_defaults(func=cmd_findings)

    p = sub.add_parser("show", help="show one finding + raw evidence")
    p.add_argument("id")
    p.add_argument("--run", help="run directory (default: latest)")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("replay", help="replay a stored request")
    p.add_argument("id")
    p.add_argument("--run", help="run directory (default: latest)")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("report", help="emit a report")
    p.add_argument("run", nargs="?", help="run directory (default: latest)")
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.add_argument("--stdout", action="store_true", help="also print the report")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("payloads", help="payload library tools")
    psub = p.add_subparsers(dest="payloads_command", required=True)
    pw = psub.add_parser("where", help="print the built-in payload dir")
    pw.set_defaults(func=cmd_payloads_where)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        # Show the banner for the offensive `run` command (not for scripting
        # subcommands, and never when --no-banner is given).
        if getattr(args, "command", None) == "run" and not getattr(args, "no_banner", False):
            _out(banner(_platform()))
            _out("")
        return args.func(args)
    except AIInjectorError as exc:
        _err(f"[!] {exc}")
        return EXIT_ERR
    except KeyboardInterrupt:
        _err("[!] interrupted")
        return EXIT_ERR


if __name__ == "__main__":
    sys.exit(main())
