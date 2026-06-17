"""Durable local receipt-file helpers for the state core."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


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
