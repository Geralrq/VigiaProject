from importlinter import cli


def test_import_linter_contracts_hold() -> None:
    # lint_imports returns the process exit code (0 = all contracts kept).
    assert cli.lint_imports() == 0
