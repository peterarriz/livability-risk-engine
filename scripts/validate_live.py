#!/usr/bin/env python3
"""
Deprecated compatibility wrapper for scripts/demo_smoke_check.py.

This file intentionally no longer contains its old live-validation logic. The
old implementation assumed DB readiness fields lived on public /health and
called unauthenticated /debug/score, both of which are stale assumptions.
"""

from __future__ import annotations

import sys
from pathlib import Path


DEPRECATION_MESSAGE = (
    "scripts/validate_live.py is deprecated; use scripts/demo_smoke_check.py."
)


def _rewrite_args(argv: list[str]) -> list[str]:
    """Translate legacy validate_live.py args into demo_smoke_check.py args."""
    rewritten: list[str] = []
    has_help = False
    has_require_live = False

    for arg in argv:
        if arg in ("-h", "--help"):
            has_help = True
        if arg == "--require-live":
            has_require_live = True

        if arg == "--backend":
            rewritten.append("--backend-url")
        elif arg.startswith("--backend="):
            rewritten.append("--backend-url=" + arg.split("=", 1)[1])
        else:
            rewritten.append(arg)

    # validate_live.py historically meant "live only"; preserve that behavior
    # while allowing --help to show the delegated script's help unchanged.
    if not has_help and not has_require_live:
        rewritten.append("--require-live")

    return rewritten


def main() -> int:
    print(DEPRECATION_MESSAGE, file=sys.stderr)

    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    from demo_smoke_check import main as demo_smoke_main

    original_argv = sys.argv[:]
    try:
        sys.argv = [str(script_dir / "demo_smoke_check.py"), *_rewrite_args(sys.argv[1:])]
        return demo_smoke_main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    sys.exit(main())
