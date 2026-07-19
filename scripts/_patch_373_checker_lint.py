from pathlib import Path
from textwrap import dedent

path = Path("scripts/check_capital_import_entrypoints.py")
text = path.read_text(encoding="utf-8")
start = text.index("def _marker_strings(")
end = text.index("def _import_like(", start)
replacement = dedent('''
def _dict_marker_strings(node: ast.Dict) -> set[str]:
    markers: set[str] = set()
    for key, value in zip(node.keys, node.values, strict=True):
        key_text = _constant_string(key)
        value_text = _constant_string(value)
        if key_text in MARKER_KEYS and value_text:
            markers.add(value_text)
    return markers


def _call_marker_strings(node: ast.Call) -> set[str]:
    return {
        value_text
        for keyword in node.keywords
        if keyword.arg in MARKER_KEYS
        and (value_text := _constant_string(keyword.value)) is not None
    }


def _assignment_marker(node: ast.Assign | ast.AnnAssign) -> str | None:
    value_text = _constant_string(node.value)
    if value_text is None:
        return None
    targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
    if any(
        isinstance(target, ast.Name)
        and any(token in target.id.lower() for token in ("source", "kind"))
        for target in targets
    ):
        return value_text
    return None


def _marker_strings(nodes: tuple[ast.AST, ...]) -> set[str]:
    markers: set[str] = set()
    for root in nodes:
        for node in ast.walk(root):
            if isinstance(node, ast.Dict):
                markers.update(_dict_marker_strings(node))
            elif isinstance(node, ast.Call):
                markers.update(_call_marker_strings(node))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                if marker := _assignment_marker(node):
                    markers.add(marker)
    return markers
''').strip()
path.write_text(text[:start] + replacement + "\n\n" + text[end:], encoding="utf-8")
