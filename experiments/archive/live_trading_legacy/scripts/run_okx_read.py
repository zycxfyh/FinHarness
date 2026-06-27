"""Run an allowlisted read-only OKX command (live or demo) via the Python gate.

Replaces the legacy `cargo run -p finharness-cli -- okx ...` read path. Usage:

    uv run python scripts/run_okx_read.py [--demo] <module> <action> [args...]

Read-only commands only; mutations must go through scripts/okx_live_order.py.
"""

from __future__ import annotations

import json
import sys

from finharness.okx_cli import OkxCliError, action_is_read_only, run_okx_command


def main(argv: list[str]) -> int:
    args = list(argv)
    demo = False
    if args and args[0] == "--demo":
        demo = True
        args = args[1:]
    if len(args) < 2:
        print("usage: run_okx_read.py [--demo] <module> <action> [args...]", file=sys.stderr)
        return 2

    module, action, rest = args[0], args[1], args[2:]
    if not action_is_read_only(module, action):
        print(
            json.dumps({"ok": False, "error": f"not a read-only command: {module} {action}"}),
            file=sys.stderr,
        )
        return 1

    try:
        result = run_okx_command(module, action, rest, live=not demo, demo=demo)
    except OkxCliError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "environment": "demo" if demo else "live",
                "module": module,
                "action": action,
                "data": result.data,  # already redacted by okx_cli
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
