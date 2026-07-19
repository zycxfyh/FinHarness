from pathlib import Path

HERE = Path(__file__).resolve().parent
target = HERE / "_patch_373_tests.py"
text = target.read_text(encoding="utf-8")
text = text.replace("TESTS = '''", 'TESTS = r"""', 1)
text = text.replace(
    "\n'''\n\n(ROOT / \"tests\" / \"test_capital_import_entrypoints.py\")",
    '\n"""\n\n(ROOT / "tests" / "test_capital_import_entrypoints.py")',
    1,
)
target.write_text(text, encoding="utf-8")
Path(__file__).unlink()
