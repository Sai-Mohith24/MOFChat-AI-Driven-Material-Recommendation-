"""
py_to_ipynb.py - save Python files as Jupyter notebooks (.ipynb) next to them.

  python tools/py_to_ipynb.py FILE_OR_FOLDER [...] [--project-root DIR] [--overwrite]

The .py files stay the source of truth (the app, tests and scripts import them);
rerun this script after editing a .py file to refresh its notebook.

How a file is split into cells
  * the module docstring becomes a markdown cell (verbatim, with a header naming the source file)
  * every top-level function and class gets its own code cell, together with the
    comments and decorators directly above it
  * other top-level code is grouped into cells of roughly 25 lines, split at blank lines
  * `if __name__ == "__main__":` is the last cell (in Jupyter __name__ is "__main__",
    so running the notebook runs the script, exactly like `python file.py`)

Small changes so the notebook runs from its own folder (files under --project-root only)
  * package-relative imports (`from .config import X`) become absolute (`from mofchat.config import X`)
  * a setup cell puts the project root on sys.path and defines __file__ (used by config.py)
  * `parser.parse_args()` becomes `parser.parse_known_args()[0]`, because Jupyter passes its
    own command-line arguments to the kernel

Existing notebooks are skipped unless --overwrite is given (they may contain outputs).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

KERNEL = {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"}
MAX_GROUP_LINES = 25


def _cell_id(path: Path, i: int) -> str:
    return hashlib.sha1(f"{path.name}:{i}".encode()).hexdigest()[:8]


def _lines(text: str) -> list[str]:
    out = text.splitlines(keepends=True)
    if out and out[-1].endswith("\n"):
        out[-1] = out[-1][:-1]
    return out


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": _lines(text)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": _lines(text)}


def _is_main_guard(node: ast.stmt) -> bool:
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__")


def split_cells(src: str) -> tuple[str | None, list[tuple[str, str]]]:
    """Return (module docstring, [(kind, code_text), ...]) for a Python source."""
    tree = ast.parse(src)
    lines = src.splitlines()
    body = list(tree.body)
    doc = None
    start_line = 1
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        doc = ast.get_docstring(tree, clean=True)
        start_line = body[0].end_lineno + 1
        body = body[1:]

    # each node owns the comment/blank lines above it (back to the previous node)
    segments = []
    prev_end = start_line - 1
    for node in body:
        first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        seg_start = prev_end + 1
        text = "\n".join(lines[seg_start - 1:node.end_lineno]).strip("\n")
        kind = "def" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else \
               "main" if _is_main_guard(node) else "stmt"
        segments.append((kind, text, first))
        prev_end = node.end_lineno
    tail = "\n".join(lines[prev_end:]).strip("\n")
    if tail.strip():
        segments.append(("stmt", tail, prev_end + 1))

    cells: list[tuple[str, str]] = []
    group: list[str] = []

    def flush():
        if group:
            cells.append(("code", "\n\n".join(g.strip("\n") for g in group if g.strip())))
            group.clear()

    for kind, text, _ in segments:
        if kind in ("def", "main"):
            flush()
            cells.append((kind, text))
        else:
            size = sum(g.count("\n") + 1 for g in group)
            if group and size + text.count("\n") + 1 > MAX_GROUP_LINES and text.lstrip("\n") != text:
                flush()                                   # new paragraph and the cell is long enough
            elif group and size >= MAX_GROUP_LINES:
                flush()
            group.append(text)
    flush()
    return doc, [(k, t) for k, t in cells if t.strip()]


def adapt(text: str, package: str | None) -> str:
    if package:
        text = re.sub(r"^(\s*)from \.(\w[\w.]*) import", rf"\1from {package}.\2 import", text, flags=re.M)
        text = re.sub(r"^(\s*)from \. import", rf"\1from {package} import", text, flags=re.M)
    return re.sub(r"\.parse_args\(\)", ".parse_known_args()[0]", text)


def is_generated(nb_path: Path) -> bool:
    """True for notebooks made by this script (safe to regenerate); False for hand-made ones."""
    try:
        cells = json.loads(nb_path.read_text()).get("cells", [])
        return bool(cells) and "Notebook version of `" in "".join(cells[0].get("source", []))
    except (OSError, ValueError):
        return False


def convert(py: Path, project_root: Path | None, overwrite: bool = False, sync: bool = False) -> Path | None:
    nb_path = py.with_suffix(".ipynb")
    if nb_path.exists() and not overwrite and not (sync and is_generated(nb_path)):
        print(f"skip (notebook exists): {nb_path}")
        return None
    src = py.read_text()
    doc, parts = split_cells(src)

    inside = project_root is not None and project_root in py.resolve().parents
    rel = py.resolve().relative_to(project_root) if inside else Path(py.name)
    package = None
    if inside and len(rel.parts) > 1 and (project_root / rel.parts[0] / "__init__.py").exists():
        package = rel.parts[0]

    cells = []
    header = f"# `{rel.as_posix()}`\n\nNotebook version of `{rel.as_posix()}`. The `.py` file is the source of truth"
    header += (" (the app and the other scripts import it); after editing it, regenerate this notebook with "
               "`python tools/py_to_ipynb.py " + rel.as_posix() + " --overwrite`." if inside else ".")
    if doc:
        header += "\n\n```text\n" + doc.strip("\n") + "\n```"   # docstrings are aligned plain text
    cells.append(markdown(header))

    if inside:
        depth = len(rel.parts) - 1
        root_expr = "Path.cwd()" + ".parent" * depth
        setup = ("# Notebook setup: make the project root importable and define __file__,\n"
                 "# so the code behaves as if run as a script (run Jupyter from this file's folder).\n"
                 "import sys\nfrom pathlib import Path\n\n"
                 f"ROOT = {root_expr}\n"
                 "if str(ROOT) not in sys.path:\n    sys.path.insert(0, str(ROOT))\n"
                 f"__file__ = str(ROOT / {rel.as_posix()!r})")
        cells.append(code(setup))

    if rel.parts and rel.parts[0] == "app_pages" or "import streamlit" in src and "st.set_page_config" in src:
        cells.append(markdown("This file is a **Streamlit page**. Run the app with `streamlit run app.py` from the "
                              "project root; executing the cells here only runs the page logic without a UI."))

    for kind, text in parts:
        cells.append(code(adapt(text, package)))

    if rel.parts and rel.parts[0] == "tests":
        cells.append(markdown("These are pytest tests: the cells above only define them. Run them with:"))
        cells.append(code("import subprocess\n"
                          "subprocess.run([sys.executable, '-m', 'pytest', '-q', str(ROOT / 'tests')], cwd=ROOT)"))

    for i, c in enumerate(cells):
        c["id"] = _cell_id(py, i)
    nb = {"cells": cells,
          "metadata": {"kernelspec": KERNEL,
                       "language_info": {"name": "python", "version": ".".join(map(str, sys.version_info[:3]))}},
          "nbformat": 4, "nbformat_minor": 5}
    nb_path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {nb_path}  ({len(cells)} cells)")
    return nb_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--sync", action="store_true",
                    help="create missing notebooks and refresh generated ones; never touch hand-made notebooks")
    ap.add_argument("--from-hook", action="store_true",
                    help="Claude Code hook mode: read the edited file path from the hook JSON on stdin")
    args = ap.parse_args()
    root = args.project_root.resolve()
    if args.from_hook:
        try:
            data = json.load(sys.stdin)
            f = Path((data.get("tool_input") or {}).get("file_path", ""))
            skip = {"venv", ".venv", "site-packages", "__pycache__", ".git"}
            if f.suffix == ".py" and f.exists() and f.stat().st_size and not skip & set(f.parts):
                convert(f, root, sync=True)
        except Exception as e:                        # a hook must never block editing
            print(f"py_to_ipynb hook: {e}", file=sys.stderr)
        return
    files = []
    for p in args.paths:
        if p.is_dir():
            files += sorted(f for f in p.rglob("*.py")
                            if not any(part in ("venv", ".venv", "__pycache__", "site-packages") for part in f.parts))
        elif p.suffix == ".py":
            files.append(p)
    for f in files:
        if f.stat().st_size == 0:
            print(f"skip (empty file): {f}")
            continue
        convert(f, root, args.overwrite, args.sync)


if __name__ == "__main__":
    main()
