from pathlib import Path

path = Path("src/finharness/statecore/store.py")
text = path.read_text(encoding="utf-8")
old = '''    try:
        receipt_payload = json.loads(receipt_content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateCoreStoreError("receipt artifact is not valid JSON") from exc
    expected_receipt_fields = {
'''
new = '''    try:
        raw_receipt_payload = json.loads(receipt_content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateCoreStoreError("receipt artifact is not valid JSON") from exc
    if not isinstance(raw_receipt_payload, dict):
        raise StateCoreStoreError("receipt artifact must contain a JSON object")
    receipt_payload = cast(dict[str, Any], raw_receipt_payload)
    expected_receipt_fields = {
'''
if text.count(old) != 1:
    raise RuntimeError(f"expected one receipt parsing block, found {text.count(old)}")
path.write_text(text.replace(old, new), encoding="utf-8")
