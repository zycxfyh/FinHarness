"""Read live OKX account, position, order, and configuration status."""

from __future__ import annotations

import json
from typing import Any

from finharness.okx_cli import OkxCliError, run_okx_live_read_command

CHECKS: tuple[tuple[str, str, list[str]], ...] = (
    ("account", "balance", []),
    ("account", "positions", []),
    ("account", "config", []),
    ("spot", "orders", []),
    ("swap", "positions", []),
    ("swap", "orders", []),
    ("futures", "positions", []),
    ("futures", "orders", []),
    ("option", "positions", []),
    ("option", "orders", []),
)

REDACT_KEYS = frozenset({"uid", "mainUid", "ip", "label"})


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key in REDACT_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def compact(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return {
            "type": "list",
            "count": len(data),
            "first": redact(data[0]) if data else None,
        }
    if isinstance(data, dict):
        return {"type": "dict", "keys": sorted(data.keys()), "data": redact(data)}
    return {"type": type(data).__name__, "data": data}


def main() -> int:
    checks = []
    for module, action, args in CHECKS:
        try:
            result = run_okx_live_read_command(module, action, args)
            checks.append(
                {
                    "module": module,
                    "action": action,
                    "ok": True,
                    "summary": compact(result.data),
                }
            )
        except OkxCliError as exc:
            checks.append(
                {
                    "module": module,
                    "action": action,
                    "ok": False,
                    "error": str(exc),
                }
            )

    print(json.dumps({"environment": "live", "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if all(check["ok"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
