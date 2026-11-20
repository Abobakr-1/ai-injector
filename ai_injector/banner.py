"""ASCII banner and version metadata for the CLI.

The wordmark is a pre-rendered "AI INJECTOR" in the ``ansi_shadow`` figlet font.
It is stored as literal art (no runtime dependency on ``pyfiglet``) so the banner
is identical on every platform and costs nothing to print.
"""

from __future__ import annotations

from . import __version__

AUTHOR = "AboBakr Mohamed"
VERSION = __version__

#: "AI INJECTOR" — ansi_shadow figlet, 6 lines, max width 78 columns.
_ART = (
    " █████╗ ██╗    ██╗███╗   ██╗     ██╗███████╗ ██████╗████████╗ ██████╗ ██████╗\n"
    "██╔══██╗██║    ██║████╗  ██║     ██║██╔════╝██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗\n"
    "███████║██║    ██║██╔██╗ ██║     ██║█████╗  ██║        ██║   ██║   ██║██████╔╝\n"
    "██╔══██║██║    ██║██║╚██╗██║██   ██║██╔══╝  ██║        ██║   ██║   ██║██╔══██╗\n"
    "██║  ██║██║    ██║██║ ╚████║╚█████╔╝███████╗╚██████╗   ██║   ╚██████╔╝██║  ██║\n"
    "╚═╝  ╚═╝╚═╝    ╚═╝╚═╝  ╚═══╝ ╚════╝ ╚══════╝ ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝"
)

#: Width of the wordmark, used to centre the tagline beneath it.
_WIDTH = 78

_TAGLINE_TEXT = "[ AI PROMPT INJECTION FRAMEWORK ]"

_BOX = """┌──────────────────────────────────────────────────────┐
│  DIRECT INJECTION  |  INDIRECT INJECTION             │
│  PAYLOAD ENGINE    |  VULNERABILITY DETECTION        │
│  EVIDENCE CAPTURE  |  SECURITY REPORTING             │
└──────────────────────────────────────────────────────┘"""


def _centre(text: str, width: int = _WIDTH) -> str:
    pad = max(0, (width - len(text)) // 2)
    return " " * pad + text


def banner(platform: str = "") -> str:
    """Return the full branded banner."""
    lines = [
        _ART,
        "",
        _centre(_TAGLINE_TEXT),
        "",
        *("       " + line for line in _BOX.splitlines()),
        "",
        f"       [!] Developed by : {AUTHOR}",
        f"       [!] Version      : {VERSION}",
    ]
    if platform:
        lines.append(f"       [!] Platform     : {platform}")
    return "\n".join(lines)


def short_banner() -> str:
    return f"AI INJECTOR v{VERSION} — direct + indirect prompt-injection testing | by {AUTHOR}"