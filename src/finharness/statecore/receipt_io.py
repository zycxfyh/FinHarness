"""Durable local receipt-file helpers for the state core."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class ReceiptPathError(ValueError):
    """Raised when a receipt path would resolve outside its allowed root."""


def resolve_under(root: str | Path, *parts: str | Path) -> Path:
    """Resolve ``root / parts...`` and guarantee the result stays within ``root``.

    Defense-in-depth against path injection: even if an upstream id sanitizer is
    bypassed, a path that escapes the allowed root raises ``ReceiptPathError`` instead of
    writing outside it. Uses ``os.path.realpath`` + a containment ``startswith`` check —
    the canonical normalize-then-verify barrier. This is a project-level allowed-root
    barrier; CodeQL does not currently model it, so its py/path-injection alerts on these
    flows are dismissed as false positives with this guard (and the regression tests) as
    the justification.
    """
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(Path(root_real).joinpath(*[str(part) for part in parts]))
    if candidate != root_real and not candidate.startswith(root_real + os.sep):
        raise ReceiptPathError(
            f"receipt path {candidate} escapes its allowed root {root_real}"
        )
    return Path(candidate)


def atomic_write_text(path: str | Path, content: str) -> Path:
    """Write text by replacing the target with a complete temp file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
        temp_path.replace(target)
    except Exception:
        if temp_path is not None:
            remove_file_best_effort(temp_path)
        raise
    return target


def atomic_write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    """Write JSON by replacing the target with a complete temp file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
                + "\n"
            )
            temp_file.flush()
        temp_path.replace(target)
    except Exception:
        if temp_path is not None:
            remove_file_best_effort(temp_path)
        raise
    return target


def remove_file_best_effort(path: str | Path) -> bool:
    """Remove a file if possible; return whether a file was removed."""
    try:
        Path(path).unlink()
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True
