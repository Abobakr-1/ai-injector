"""ASCII banner and version metadata for the CLI.

Renders:

* **AI INJECTOR** -- the tool wordmark (ansi_shadow figlet)
* **AboBakr Mohamed** -- the developer, shown in the banner (small figlet)

All art is stored as literals, so there is no runtime figlet dependency and the
banner is identical on Kali, Ubuntu, Windows and macOS.
"""

from __future__ import annotations

from . import __version__

AUTHOR = "AboBakr Mohamed"
VERSION = __version__

#: "AI INJECTOR" -- ansi_shadow, 6 lines, 78 cols.
_NAME_ART = (
    " █████╗ ██╗    ██╗███╗   ██╗     ██╗███████╗ ██████╗████████╗ ██████╗ ██████╗\n"
    "██╔══██╗██║    ██║████╗  ██║     ██║██╔════╝██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗\n"
    "███████║██║    ██║██╔██╗ ██║     ██║█████╗  ██║        ██║   ██║   ██║██████╔╝\n"
    "██╔══██║██║    ██║██║╚██╗██║██   ██║██╔══╝  ██║        ██║   ██║   ██║██╔══██╗\n"
    "██║  ██║██║    ██║██║ ╚████║╚█████╔╝███████╗╚██████╗   ██║   ╚██████╔╝██║  ██║\n"
    "╚═╝  ╚═╝╚═╝    ╚═╝╚═╝  ╚═══╝ ╚════╝ ╚══════╝ ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝"
)

#: "AboBakr Mohamed" -- small, 4 lines, 73 cols.
_AUTHOR_ART = (
    "   _   _         ___       _         __  __     _                      _\n"
    "  /_\\ | |__  ___| _ ) __ _| |___ _  |  \\/  |___| |_  __ _ _ __  ___ __| |\n"
    " / _ \\| '_ \\/ _ \\ _ \\/ _` | / / '_| | |\\/| / _ \\ ' \\/ _` | '  \\/ -_) _` |\n"
    "/_/ \\_\\_.__/\\___/___/\\__,_|_\\_\\_|   |_|  |_\\___/_||_\\__,_|_|_|_\\___\\__,_|"
)

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
        _NAME_ART,
        "",
        _centre(_TAGLINE_TEXT),
        "",
        *("       " + line for line in _BOX.splitlines()),
        "",
        f"       [!] Developed by : {AUTHOR}",
        _AUTHOR_ART,
        "",
        f"       [!] Version      : {VERSION}",
    ]
    if platform:
        lines.append(f"       [!] Platform     : {platform}")
    return "\n".join(lines)


def short_banner() -> str:
    return f"AI INJECTOR v{VERSION} — direct + indirect prompt-injection testing | by {AUTHOR}"