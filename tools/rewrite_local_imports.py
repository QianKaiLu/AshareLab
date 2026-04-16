import ast
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path("/Users/qianqian/stock/AshareLab")

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "output",
    "logs",
    "database",
    ".pytest_cache",
    ".mypy_cache",
}

BACKUP_DIR = ROOT / ".import_rewrite_backup"


def iter_py_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        yield path


def path_to_module(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        return ".".join(parts[:-1])
    return ".".join(parts).removesuffix(".py")


def build_module_index(root: Path) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for path in iter_py_files(root):
        if path.name == "__init__.py":
            continue
        module_name = path_to_module(root, path)
        short_name = path.stem
        index.setdefault(short_name, []).append(module_name)
    return index


def choose_target_module(
    short_name: str,
    current_module: str,
    module_index: Dict[str, List[str]],
) -> str | None:
    candidates = module_index.get(short_name, [])
    if not candidates:
        return None

    filtered = [m for m in candidates if m != current_module]
    if not filtered:
        return None

    if len(filtered) == 1:
        return filtered[0]

    current_top = current_module.split(".")[0]
    same_top = [m for m in filtered if m.split(".")[0] == current_top]
    if len(same_top) == 1:
        return same_top[0]

    return None


def collect_replacements(
    source: str,
    current_module: str,
    module_index: Dict[str, List[str]],
) -> List[Tuple[int, int, str, str]]:
    tree = ast.parse(source)
    replacements: List[Tuple[int, int, str, str]] = []
    lines = source.splitlines(keepends=True)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            start = node.lineno - 1
            end = node.end_lineno
            old_text = "".join(lines[start:end])

            new_parts = []
            changed = False

            for alias in node.names:
                original = alias.name
                target = None

                if "." not in original:
                    target = choose_target_module(
                        short_name=original,
                        current_module=current_module,
                        module_index=module_index,
                    )

                if target:
                    changed = True
                    if alias.asname:
                        new_parts.append(f"import {target} as {alias.asname}")
                    else:
                        new_parts.append(f"import {target}")
                else:
                    if alias.asname:
                        new_parts.append(f"import {original} as {alias.asname}")
                    else:
                        new_parts.append(f"import {original}")

            if changed:
                indent = re.match(r"^\s*", lines[start]).group(0)
                new_text = "\n".join(indent + part.replace("import ", "", 1) for part in [])
                new_text = "\n".join(
                    indent + part for part in [p.replace("import ", "import ", 1) for p in new_parts]
                )
                new_text += "\n"
                replacements.append((start, end, old_text, new_text))

        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue
            if not node.module:
                continue
            if "." in node.module:
                continue

            target = choose_target_module(
                short_name=node.module,
                current_module=current_module,
                module_index=module_index,
            )
            if not target:
                continue

            start = node.lineno - 1
            end = node.end_lineno
            old_text = "".join(lines[start:end])

            indent = re.match(r"^\s*", lines[start]).group(0)
            imported_names = []
            for alias in node.names:
                if alias.asname:
                    imported_names.append(f"{alias.name} as {alias.asname}")
                else:
                    imported_names.append(alias.name)

            new_text = f"{indent}from {target} import {', '.join(imported_names)}\n"
            replacements.append((start, end, old_text, new_text))

    replacements.sort(key=lambda x: x[0], reverse=True)
    return replacements


def apply_replacements(source: str, replacements: List[Tuple[int, int, str, str]]) -> str:
    lines = source.splitlines(keepends=True)
    for start, end, _old_text, new_text in replacements:
        lines[start:end] = [new_text]
    return "".join(lines)


def backup_file(path: Path):
    backup_path = BACKUP_DIR / path.relative_to(ROOT)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)


def main(dry_run: bool = True):
    module_index = build_module_index(ROOT)
    changed_files = []

    if not dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    for path in iter_py_files(ROOT):
        source = path.read_text(encoding="utf-8")
        current_module = path_to_module(ROOT, path)
        replacements = collect_replacements(source, current_module, module_index)

        if not replacements:
            continue

        new_source = apply_replacements(source, replacements)
        if new_source == source:
            continue

        changed_files.append((path, replacements))

        print(f"\n[{path.relative_to(ROOT)}]")
        for _start, _end, old_text, new_text in reversed(replacements):
            print("  OLD:", old_text.strip())
            print("  NEW:", new_text.strip())

        if not dry_run:
            backup_file(path)
            path.write_text(new_source, encoding="utf-8")

    print(f"\nChanged files: {len(changed_files)}")
    if dry_run:
        print("Dry-run only. No files were modified.")
    else:
        print(f"Backup saved to: {BACKUP_DIR}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rewrite local imports to absolute package imports.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually modify files. Default is dry-run.",
    )
    args = parser.parse_args()
    main(dry_run=not args.write)