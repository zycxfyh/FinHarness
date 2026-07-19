from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected one match, found {text.count(old)}")
    path.write_text(text.replace(old, new), encoding="utf-8")


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

personal = ROOT / "src" / "finharness" / "personal_finance.py"
text = personal.read_text(encoding="utf-8")
function_start = text.index("def ingest_personal_finance_export(")
prepared_start = text.index("    prepared = prepare_import(", function_start)
source_refs_start = text.index("    source_refs = ", prepared_start)
receipt_index_start = text.index("    receipt_index = ReceiptIndex(", source_refs_start)
records_start = text.index("    records = _records_from_rows(", receipt_index_start)
delta_start = text.index("    delta_base_batch_id:", records_start)
prepare_block = text[prepared_start:source_refs_start]
source_refs_block = text[source_refs_start:receipt_index_start]
receipt_index_block = text[receipt_index_start:records_start]
records_block = text[records_start:delta_start]
replacement = source_refs_block + records_block + prepare_block + receipt_index_block
personal.write_text(
    text[:prepared_start] + replacement + text[delta_start:],
    encoding="utf-8",
)
