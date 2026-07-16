import ast
from pathlib import Path


def test_source_parses_as_python_39() -> None:
    for source_path in Path("backend").rglob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path), feature_version=(3, 9))
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                assert not (
                    isinstance(node.annotation, ast.BinOp)
                    and isinstance(node.annotation.op, ast.BitOr)
                ), f"{source_path} uses a Python 3.10 union annotation"
