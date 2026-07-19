from pathlib import Path

path = Path("src/finharness/capital_import_recovery.py")
text = path.read_text(encoding="utf-8")
anchor = "\n\ndef audit_capital_imports("
helper = """


def _optional_receipt_payload(
    store: ArtifactStore,
    descriptor: ArtifactDescriptor | None,
) -> dict[str, Any] | None:
    if descriptor is None:
        return None
    try:
        return _receipt_payload(store, descriptor)
    except CapitalImportRecoveryError:
        return None
"""
text = text.replace(anchor, helper + anchor, 1)
text = text.replace(
    """        current_payload: dict[str, Any] | None = None
        if current_descriptor is not None:
            try:
                current_payload = _receipt_payload(store, current_descriptor)
            except CapitalImportRecoveryError:
                current_payload = None
""",
    "        current_payload = _optional_receipt_payload(store, current_descriptor)\n",
    1,
)
path.write_text(text, encoding="utf-8")
