"""ASCII banner and version metadata for the CLI."""

from __future__ import annotations

from . import __version__

AUTHOR = "AboBakr Mohamed"
VERSION = __version__

_BANNER = r"""
 █████╗ ██╗    ███████╗███╗   ██╗     ██╗███╗   ██╗     ██╗███████╗ ██████╗████████╗ ██████╗ ██████╗
██╔══██╗██║    ██╔════╝████╗  ██║     ██║████╗  ██║     ██║██╔════╝██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗
███████║██║    █████╗  ██╔██╗ ██║     ██║██╔██╗ ██║     ██║█████╗  ██║        ██║   ██║   ██║██████╔╝
██╔══██║██║    ██╔══╝  ██║╚██╗██║██   ██║██║╚██╗██║██   ██║██╔══╝  ██║        ██║   ██║   ██║██╔══██╗
██║  ██║██║    ███████╗██║ ╚████║╚█████╔╝██║ ╚████║╚█████╔╝███████╗╚██████╗   ██║   ╚██████╔╝██║  ██║
╚═╝  ╚═╝╚═╝    ╚══════╝╚═╝  ╚═══╝ ╚════╝ ╚═╝  ╚═══╝ ╚════╝ ╚══════╝ ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
"""

_TAGLINE = "              [ AI INJECTOR ]  —  AI PROMPT INJECTION FRAMEWORK"

_BOX = """       ┌──────────────────────────────────────────────────────┐
       │  AI INJECTOR                                         │
       │  DIRECT INJECTION  |  INDIRECT INJECTION             │
       │  PAYLOAD ENGINE    |  VULNERABILITY DETECTION        │
       │  EVIDENCE CAPTURE  |  SECURITY REPORTING             │
       └──────────────────────────────────────────────────────┘"""


def banner(platform: str = "") -> str:
    lines = [
        _BANNER,
        _TAGLINE,
        "",
        _BOX,
        "",
        f"       [!] Developed by : {AUTHOR}",
        f"       [!] Version      : {VERSION}",
    ]
    if platform:
        lines.append(f"       [!] Platform     : {platform}")
    return "\n".join(lines)


def short_banner() -> str:
    return f"AI INJECTOR v{VERSION} — direct + indirect prompt-injection testing | by {AUTHOR}"
