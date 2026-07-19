from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected one match, found {text.count(old)}")
    path.write_text(text.replace(old, new), encoding="utf-8")


core = ROOT / "scripts" / "_patch_373_core.py"
text = core.read_text(encoding="utf-8")
start = text.index('replace_once(\n    "src/finharness/capital_import_registry.py"')
end = text.index('replace_once(\n    "src/finharness/statecore/store.py"', start)
core.write_text(text[:start] + text[end:], encoding="utf-8")

subprocess.run(["python", str(core)], cwd=ROOT, check=True)
subprocess.run(
    ["python", str(ROOT / "scripts" / "_patch_373_recovery_lint.py")],
    cwd=ROOT,
    check=True,
)

checker = ROOT / "scripts" / "check_capital_import_entrypoints.py"
replace_once(
    checker,
    """            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                if marker := _assignment_marker(node):
                    markers.add(marker)
""",
    """            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and (
                marker := _assignment_marker(node)
            ):
                markers.add(marker)
""",
)

store = ROOT / "src" / "finharness" / "statecore" / "store.py"
replace_once(
    store,
    """    if any(snapshot.payload.get(key) != value for key, value in expected_payload.items()):
        raise StateCoreStoreError("snapshot does not bind the canonical import envelope")
""",
    """    mismatches = {
        key: {"actual": snapshot.payload.get(key), "expected": value}
        for key, value in expected_payload.items()
        if snapshot.payload.get(key) != value
    }
    if mismatches:
        raise StateCoreStoreError(
            f"snapshot does not bind the canonical import envelope: {mismatches}"
        )
""",
)

for path in (
    ROOT / "scripts" / "_patch_373_core.py",
    ROOT / "scripts" / "_patch_373_checker.py",
    ROOT / "scripts" / "_patch_373_tests.py",
    ROOT / "scripts" / "_patch_373_checker_lint.py",
    ROOT / "scripts" / "_patch_373_recovery_lint.py",
    ROOT / "scripts" / "sitecustomize.py",
):
    path.unlink(missing_ok=True)
shutil.rmtree(ROOT / ".ci" / "issue373-bundle", ignore_errors=True)

subprocess.run(["uv", "sync", "--frozen"], cwd=ROOT, check=True)
subprocess.run(
    [
        "uv",
        "run",
        "ruff",
        "format",
        "scripts/check_capital_import_entrypoints.py",
        "src/finharness/capital_import_recovery.py",
        "src/finharness/personal_finance.py",
        "src/finharness/beancount_adapter.py",
        "src/finharness/statecore/store.py",
    ],
    cwd=ROOT,
    check=True,
)
subprocess.run(
    [
        "uv",
        "run",
        "python",
        "-m",
        "unittest",
        "tests.test_capital_import_recovery.CapitalImportRecoveryTest.test_clean_materialization_is_verified",
    ],
    cwd=ROOT,
    env={**dict(__import__("os").environ), "PYTHONPATH": "src"},
    check=True,
)
