#!/usr/bin/env python3
"""Generate the as-built half of docs/data_dictionary.md from the module source.

BRD §8.3.4 requires a data dictionary carrying field label, technical name,
model, type, selection values, mandatory condition, default, validation and the
rest, and says no proposed field is approved until it appears there. A
dictionary typed by hand starts accurate and ends fiction: this project has
already shipped three defects whose shape was "two lists that must agree, with
nothing asserting it".

So the as-built section is derived from the Python field definitions by parsing
the AST — no Odoo installation needed, and no trusting a model name from
memory. The to-build section, which describes fields that do not exist yet,
stays hand-written above the generated marker and is left untouched.

    python tools/gen_data_dictionary.py            # rewrite the generated section
    python tools/gen_data_dictionary.py --check    # fail if it is stale (CI)
"""

import argparse
import ast
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
DICTIONARY = REPO / "docs" / "data_dictionary.md"
NON_ADDON_DIRS = {".git", ".github", "conf", "docs", "tools", ".ruff_cache"}

BEGIN = "<!-- BEGIN GENERATED: as-built fields -->"
END = "<!-- END GENERATED -->"


def addons():
    return sorted(
        p for p in REPO.iterdir() if p.is_dir() and p.name not in NON_ADDON_DIRS and (p / "__manifest__.py").is_file()
    )


def literal(node):
    """Best-effort render of a keyword value; never raises on an expression."""
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return ast.unparse(node)


def selection_values(node):
    """Render a Selection's values as `key`/`key` when they are literal."""
    value = literal(node)
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out.append(str(item[0]))
            else:
                return ""
        return ", ".join(out)
    return "dynamic" if isinstance(value, str) else ""


def parse_model(class_node, module_path):
    """Return (model_name, inherited, [field dicts]) for one Odoo model class."""
    name = inherit = None
    fields = []

    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if not isinstance(target, ast.Name):
                continue

            if target.id == "_name":
                name = literal(stmt.value)
                continue
            if target.id == "_inherit":
                inherit = literal(stmt.value)
                continue

            call = stmt.value
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "fields"
            ):
                continue

            kw = {k.arg: k.value for k in call.keywords if k.arg}
            ftype = call.func.attr

            # The first positional means different things by field type:
            # Selection takes its value list there, relational fields take the
            # comodel name. Reading only keywords misses both, because neither
            # is normally passed by keyword.
            comodel = ""
            selection_node = kw.get("selection")
            if call.args:
                if ftype == "Selection" and selection_node is None:
                    selection_node = call.args[0]
                else:
                    first = literal(call.args[0])
                    if isinstance(first, str):
                        comodel = first
            if "comodel_name" in kw:
                comodel = literal(kw["comodel_name"]) or comodel

            fields.append(
                {
                    "name": target.id,
                    "type": ftype,
                    "label": literal(kw["string"]) if "string" in kw else "",
                    "comodel": comodel,
                    "required": "yes" if kw.get("required") and literal(kw["required"]) is True else "",
                    "default": "" if "default" not in kw else str(literal(kw["default"])),
                    "selection": selection_values(selection_node) if selection_node is not None else "",
                    "compute": literal(kw["compute"]) if "compute" in kw else "",
                    "stored": "yes" if kw.get("store") and literal(kw["store"]) is True else "",
                    "related": literal(kw["related"]) if "related" in kw else "",
                    "tracked": "yes" if kw.get("tracking") and literal(kw["tracking"]) is True else "",
                    "help": (literal(kw["help"]) if "help" in kw else "") or "",
                    "module": module_path.parts[-3],
                }
            )

    model = name or (inherit if isinstance(inherit, str) else None)
    return model, (name is None and model is not None), fields


def collect():
    models = {}
    for addon in addons():
        for path in sorted((addon / "models").glob("*.py")) + sorted((addon / "wizard").glob("*.py")):
            if path.name == "__init__.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                model, is_inherit, fields = parse_model(node, path)
                if not model or not fields:
                    continue
                entry = models.setdefault(model, {"inherited": is_inherit, "fields": []})
                entry["fields"].extend(fields)
                entry["inherited"] = entry["inherited"] and is_inherit
    return models


def escape(text):
    return str(text).replace("|", r"\|").replace("\n", " ").strip()


def render(models):
    lines = [BEGIN, ""]
    lines.append(
        "Generated by `tools/gen_data_dictionary.py` from the module source. "
        "Do not edit between the markers — edit the field definition and regenerate."
    )
    lines.append("")
    total = sum(len(m["fields"]) for m in models.values())
    lines.append(f"**{len(models)} models, {total} fields** as built today.")
    lines.append("")

    for model in sorted(models):
        entry = models[model]
        kind = "extension of a standard model" if entry["inherited"] else "custom model"
        lines.append(f"### `{model}`")
        lines.append("")
        lines.append(f"{kind} — `{entry['fields'][0]['module']}`")
        lines.append("")
        lines.append(
            "| Technical name | Label | Type | Req | Default | Selection / comodel | Stored compute | Tracked |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for f in sorted(entry["fields"], key=lambda x: x["name"]):
            detail = f["selection"] or f["comodel"] or ""
            if f["related"]:
                detail = f"related: {f['related']}"
            compute = ""
            if f["compute"]:
                compute = f"{f['compute']}" + (" (stored)" if f["stored"] else " (not stored)")
            lines.append(
                "| `{}` | {} | {} | {} | {} | {} | {} | {} |".format(
                    f["name"],
                    escape(f["label"]),
                    f["type"],
                    f["required"],
                    escape(f["default"]),
                    escape(detail),
                    escape(compute),
                    f["tracked"],
                )
            )
        lines.append("")

    lines.append(END)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if the generated section is out of date")
    args = ap.parse_args(argv)

    if not DICTIONARY.is_file():
        print(f"{DICTIONARY} not found. Create it with the {BEGIN} / {END} markers first.")
        return 1

    text = DICTIONARY.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        print(f"{DICTIONARY} is missing the generated-section markers.")
        return 1

    generated = render(collect())
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    updated = head + generated + tail

    if args.check:
        if updated != text:
            print("data_dictionary.md is stale - run: python tools/gen_data_dictionary.py")
            return 1
        print("data dictionary: generated section matches the source")
        return 0

    DICTIONARY.write_text(updated, encoding="utf-8")
    print(f"regenerated the as-built section of {DICTIONARY.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
