"""Scan ALL verifier modules for dead code: constants/variables defined but never used."""
import ast
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

NAVI_DIR = "navi_bench"
SKIP = {"__pycache__", ".git"}

def find_dead_constants(filepath):
    """Find module-level constants that are never referenced elsewhere in the file."""
    with open(filepath, encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    # Collect module-level assignments (uppercase = constant convention)
    module_level_names = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    module_level_names[name] = node.lineno
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            module_level_names[name] = node.lineno

    if not module_level_names:
        return []

    # Count references to each name (excluding the definition itself)
    dead = []
    for name, def_line in module_level_names.items():
        # Count how many times this name appears in the source as a reference
        ref_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == name:
                if node.lineno != def_line:
                    ref_count += 1
            # Also check attribute access like module.CONST
            elif isinstance(node, ast.Attribute) and node.attr == name:
                ref_count += 1

        if ref_count == 0:
            dead.append((name, def_line))

    return dead


def scan_all():
    total_dead = 0
    for root, dirs, files in os.walk(NAVI_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            dead = find_dead_constants(fpath)
            if dead:
                rel = os.path.relpath(fpath)
                for name, line in dead:
                    print(f"  DEAD: {rel}:{line:4d}  {name}")
                    total_dead += 1

    print(f"\nTotal dead constants/variables: {total_dead}")


if __name__ == "__main__":
    scan_all()
