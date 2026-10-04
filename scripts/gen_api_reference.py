#!/usr/bin/env python3
"""Generate the locked API reference for the whole repository.

Walks every module under the shipped packages, extracts public constants,
functions, async functions, classes and their public methods with real
signatures and first docstring lines, and groups the result by subsystem.
Routes, CLI verbs and DB tables are extracted too so the reference cannot
silently drift from the code.

Usage:
    .venv/bin/python scripts/gen_api_reference.py [--out docs/API-REFERENCE.md]
"""
from __future__ import annotations

import argparse
import ast
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (subsystem title, ordered module globs). Order is the reading order of the
# product: loop machinery first, then the departments that use it.
GROUPS: list[tuple[str, list[str]]] = [
    ("Core state and models", ["core/*.py"]),
    ("Support services", ["services/*.py"]),
    ("Video pipeline package", ["services/video/*.py"]),
    ("Agents", ["agents/*.py"]),
    ("HTTP surface", ["app/*.py"]),
    ("Operations scripts", ["scripts/*.py"]),
]

SKIP_DIR_PARTS = {"__pycache__", "tests", "node_modules", ".git", "migrations"}
ROUTE_DECORATORS = re.compile(r"@\w+\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)")
CLI_SUBCOMMANDS = re.compile(r"add_parser\(\s*[\"']([^\"']+)")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _modules(patterns: list[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        for path in sorted(ROOT.glob(pattern)):
            if any(part in SKIP_DIR_PARTS for part in path.parts):
                continue
            if path.name.startswith("_") and path.name != "__init__.py":
                continue
            if path not in found:
                found.append(path)
    return found


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = ast.unparse(node.args)
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix}{node.name}({args}){returns}"


def _summary(node: ast.AST) -> str:
    doc = (ast.get_docstring(node) or "").strip()
    first = doc.split("\n")[0].strip() if doc else ""
    return first.rstrip(".")


def _decorators(node: ast.AST) -> list[str]:
    return [ast.unparse(d) for d in getattr(node, "decorator_list", [])]


def _render_module(path: Path, tree: ast.Module) -> list[str]:
    lines: list[str] = [f"### `{_rel(path)}`", ""]
    body: list[str] = []

    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                [el.id for el in node.targets if isinstance(el, ast.Name)]
                if isinstance(node, ast.Assign)
                else ([node.target.id] if isinstance(node.target, ast.Name) else [])
            )
            for name in targets:
                if name.isupper() and not name.startswith("_"):
                    body.append(f"- const `{name}`")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith("_"):
                continue
            note = _summary(node)
            flags = [d for d in _decorators(node) if not d.startswith("app.")]
            flag = f" [{', '.join(flags)}]" if flags else ""
            body.append(
                f"- `{_signature(node)}`{flag}" + (f" — {note}" if note else "")
            )
        elif isinstance(node, ast.ClassDef):
            doc = _summary(node)
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            header = f"- class `{node.name}`" + (f"({bases})" if bases else "")
            body.append(header + (f" — {doc}" if doc else ""))
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                    if sub.name.startswith("_"):
                        continue
                    sdoc = _summary(sub)
                    body.append(
                        f"  - `{_signature(sub)}`" + (f" — {sdoc}" if sdoc else "")
                    )
                elif isinstance(sub, ast.ClassDef) and not sub.name.startswith("_"):
                    body.append(f"  - class `{sub.name}` — {_summary(sub)}")

    if not body:
        body = ["- (no public module-level names)"]
    lines.extend(body)
    lines.append("")
    return lines


def _routes_and_tables() -> tuple[list[str], list[str]]:
    routes: list[str] = []
    tables: list[str] = []
    for path in sorted((ROOT / "app").glob("*.py")) + sorted((ROOT / "core").glob("*.py")):
        text = path.read_text()
        module = _rel(path)
        for method, route in ROUTE_DECORATORS.findall(text):
            routes.append(f"| `{method.upper()} {route}` | `{module}` |")
        for match in re.finditer(
            r"CREATE TABLE(?: IF NOT EXISTS)?\s+(\w+)", text, re.IGNORECASE
        ):
            tables.append(f"| `{match.group(1)}` | `{module}` |")
        for match in re.finditer(
            r"CREATE TABLE(?: IF NOT EXISTS)?\s+(\w+)\s*\(", text, re.IGNORECASE
        ):
            pass
    return routes, tables


def _cli_verbs() -> list[str]:
    verbs: list[str] = []
    for path in sorted((ROOT / "scripts").glob("*.py")):
        text = path.read_text()
        module = _rel(path)
        for verb in CLI_SUBCOMMANDS.findall(text):
            verbs.append(f"| `{verb}` | `{module}` |")
    return verbs


def _counts(tree: ast.Module) -> dict[str, int]:
    """Public-name counts for one module tree (dunders and privates excluded)."""
    functions = methods = classes = constants = 0
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if not node.name.startswith("_"):
                functions += 1
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            classes += 1
            methods += sum(
                1
                for sub in node.body
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef)
                and not sub.name.startswith("_")
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            constants += 1
    return {
        "functions": functions,
        "methods": methods,
        "classes": classes,
        "constants": constants,
    }


def build() -> str:
    trees: dict[Path, ast.Module] = {}
    modules: list[Path] = []
    for _, patterns in GROUPS:
        for path in _modules(patterns):
            try:
                trees[path] = ast.parse(path.read_text())
            except SyntaxError:
                continue
            modules.append(path)

    routes, tables = _routes_and_tables()
    verbs = _cli_verbs()

    out: list[str] = []
    out.append("# AutoEvolve locked API reference")
    out.append("")
    out.append(
        f"Generated from source by `scripts/gen_api_reference.py` at commit "
        f"`{_git_head()}` on {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}."
    )
    out.append("")
    out.append(
        "Every public constant, function, class and method in the shipped "
        "packages, with its real signature. Read this as the contract: if a "
        "name here disagrees with the code, the code is authoritative and this "
        "file must be regenerated."
    )
    out.append("")

    totals = {"modules": 0, "functions": 0, "methods": 0, "classes": 0,
              "constants": 0}
    per_group: list[tuple[str, dict[str, int]]] = []
    for title, patterns in GROUPS:
        group = {"modules": 0, "functions": 0, "methods": 0, "classes": 0,
                 "constants": 0}
        for path in _modules(patterns):
            tree = trees.get(path)
            if tree is None:
                continue
            counts = _counts(tree)
            for key, value in counts.items():
                group[key] += value
        group["modules"] = sum(
            1 for path in _modules(patterns) if path in trees
        )
        if not group["modules"]:
            continue
        for key in totals:
            totals[key] += group[key]
        per_group.append((title, group))

    out.append("## Totals")
    out.append("")
    out.append(
        "| subsystem | modules | functions | classes | methods | constants |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(
            f"| {title} | {g['modules']} | {g['functions']} | {g['classes']} | "
            f"{g['methods']} | {g['constants']} |"
            for title, g in per_group
        )
        + f"\n| **all** | **{totals['modules']}** | **{totals['functions']}** | "
        f"**{totals['classes']}** | **{totals['methods']}** | "
        f"**{totals['constants']}** |"
    )
    out.append("")
    out.append(
        f"Plus {len(routes)} HTTP routes, {len(tables)} database tables and "
        f"{len(verbs)} CLI subcommands, listed at the end."
    )
    out.append("")

    for title, _ in per_group:
        out.append(f"## {title}")
        out.append("")
        for path in _modules(dict(GROUPS)[title]):
            tree = trees.get(path)
            if tree is None:
                continue
            out.extend(_render_module(path, tree))

    out.append("## HTTP routes")
    out.append("")
    out.append("| route | module |\n|---|---|")
    out.extend(sorted(set(routes)))
    out.append("")

    out.append("## CLI verbs")
    out.append("")
    out.append("| verb | module |\n|---|---|")
    out.extend(sorted(set(verbs)))
    out.append("")

    out.append("## Database tables")
    out.append("")
    out.append("| table | declared in |\n|---|---|")
    out.extend(sorted(set(tables)))
    out.append("")

    out.append("## Regenerate")
    out.append("")
    out.append("```bash")
    out.append(".venv/bin/python scripts/gen_api_reference.py")
    out.append("```")
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/API-REFERENCE.md")
    args = parser.parse_args()
    target = ROOT / args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build())
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
