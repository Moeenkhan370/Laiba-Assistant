
"""Additional offline hardening for the independent coding agent."""
import ast
import os
from pathlib import Path
from .agent import LocalCodingAgent as BaseAgent


class LocalCodingAgent(BaseAgent):
    HIDDEN_ALLOWED = {".github", ".vscode", ".devcontainer"}

    def __init__(self, project_root="."):
        super().__init__(project_root)
        self.warnings = []

    def scan(self):
        found, total = {}, 0
        self.records, self.findings, self.dependencies = {}, [], []
        self.warnings = []
        for current, dirs, names in os.walk(str(self.root), followlinks=False):
            here = Path(current)
            dirs[:] = sorted(
                d for d in dirs
                if d not in self.EXCLUDED_DIRS
                and (not d.startswith(".") or d in self.HIDDEN_ALLOWED)
                and not (here / d).is_symlink()
            )
            for name in sorted(names):
                path = here / name
                if path.is_symlink() or name.casefold() in self.SECRET_NAMES:
                    continue
                if name.casefold().startswith((".env.", "secret", "credential")):
                    continue
                if path.suffix.lower() not in self.ALLOWED:
                    continue
                relative = path.relative_to(self.root).as_posix()
                try:
                    size = path.stat().st_size
                    if size > self.MAX_FILE_BYTES:
                        self.warnings.append({
                            "path": relative, "kind": "file_size_limit",
                            "message": "File skipped: exceeds per-file scan limit."
                        })
                        continue
                    if total + size > self.MAX_TOTAL_BYTES:
                        self.warnings.append({
                            "path": relative, "kind": "repository_size_limit",
                            "message": "Remaining files skipped: repository scan-size limit reached."
                        })
                        dirs[:] = []
                        break
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    self.warnings.append({
                        "path": relative, "kind": "file_read_warning",
                        "message": "File could not be read as UTF-8."
                    })
                    continue
                found[relative] = content
                total += size
        self.files = dict(sorted(found.items()))
        return {"root": str(self.root), "file_count": len(self.files),
                "total_bytes": total, "files": list(self.files),
                "warnings": list(self.warnings)}

    def _inspect_ast(self, path, tree):
        results = super()._inspect_ast(path, tree)
        seen = set()

        def add(node, kind, message, severity="medium"):
            key = (kind, getattr(node, "lineno", 1))
            if key not in seen:
                seen.add(key)
                results.append(self._finding(
                    path, key[1], kind, severity, message
                ))

        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                comparators = [node.left] + list(node.comparators)
                for op, right in zip(node.ops, node.comparators):
                    if isinstance(op, (ast.Is, ast.IsNot)):
                        pair = (node.left, right)
                        literal = next((x for x in pair
                            if isinstance(x, ast.Constant)
                            and x.value is not None), None)
                        if literal is not None:
                            add(node, "identity_literal",
                                "Use == or != for value comparison; identity checks are intended for singleton objects such as None.")
            if isinstance(node, ast.Call):
                name = self._call_name(node.func)
                if name == "load" and isinstance(node.func, ast.Attribute):
                    if node.func.value and isinstance(node.func.value, ast.Name):
                        if node.func.value.id in {"yaml", "yml"}:
                            safe = any(k.arg == "Loader" and
                                isinstance(k.value, ast.Attribute) and
                                k.value.attr in {"SafeLoader", "CSafeLoader"}
                                for k in node.keywords)
                            if not safe:
                                add(node, "unsafe_yaml_load",
                                    "yaml.load without an explicit safe loader can construct unsafe objects.",
                                    "high")
                if any(k.arg == "verify" and isinstance(k.value, ast.Constant)
                       and k.value.value is False for k in node.keywords):
                    add(node, "tls_verification_disabled",
                        "TLS certificate verification is disabled.", "high")

        def inspect_body(body):
            definitions = {}
            terminated = False
            for statement in body:
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef,
                                          ast.ClassDef)):
                    if statement.name in definitions:
                        add(statement, "duplicate_definition",
                            "A definition with this name already exists in the same scope.")
                    definitions[statement.name] = statement
                if terminated:
                    add(statement, "unreachable_code",
                        "Statement follows an unconditional return, raise, break, or continue.")
                if isinstance(statement, (ast.Return, ast.Raise,
                                          ast.Break, ast.Continue)):
                    terminated = True
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef,
                                          ast.ClassDef)):
                    inspect_body(statement.body)
                elif isinstance(statement, (ast.If, ast.For, ast.AsyncFor,
                                            ast.While, ast.With, ast.AsyncWith)):
                    inspect_body(statement.body)
                    if getattr(statement, "orelse", None):
                        inspect_body(statement.orelse)
                elif isinstance(statement, ast.Try):
                    inspect_body(statement.body)
                    for handler in statement.handlers:
                        inspect_body(handler.body)
                    inspect_body(statement.orelse)
                    inspect_body(statement.finalbody)

        inspect_body(tree.body)
        return results

    def report(self):
        result = super().report()
        result["warnings"] = list(self.warnings)
        return result

    def find_feature_locations(self, request, limit=30):
        results = super().find_feature_locations(request, limit=limit)
        terms = self._terms(request)
        # Improve matches for CamelCase names and underscore-separated identifiers.
        extra = {}
        for path, source in self.files.items():
            score = 0
            symbols = []
            for symbol in self.records.get(path, {}).get("symbols", []):
                name = symbol["name"]
                pieces = set(self._terms(name.replace("_", " ")))
                if terms and terms.intersection(pieces):
                    symbols.append(symbol)
                    score += 5
            if score:
                extra[path] = {"path": path, "score": score,
                               "matching_symbols": symbols}
        merged = {item["path"]: item for item in results}
        for path, item in extra.items():
            if path in merged:
                merged[path]["score"] += item["score"]
                known = {s["qualified_name"] for s in merged[path]["matching_symbols"]}
                merged[path]["matching_symbols"].extend(
                    s for s in item["matching_symbols"]
                    if s["qualified_name"] not in known
                )
            else:
                merged[path] = item
        return sorted(merged.values(),
                      key=lambda x: (-x["score"], x["path"]))[:limit]

    def build_context(self, request, max_chars=14000, limit=12):
        result = super().build_context(request, max_chars=max_chars, limit=limit)
        included = {x["path"] for x in result["matches"]}
        additions = []
        for dep in self.dependencies:
            target = dep.get("target")
            if dep.get("kind") != "local" or target in included:
                continue
            source = self.files.get(target)
            if source is None:
                continue
            lines = source.splitlines()
            excerpt = "\n".join(
                "{}: {}".format(i, line)
                for i, line in enumerate(lines[:12], 1)
            )
            additions.append("--- dependency: {} ---\n{}".format(target, excerpt))
            included.add(target)
        context = result["context"]
        for section in additions:
            candidate = (context + "\n" + section).strip()
            if len(candidate) > max_chars:
                result["truncated"] = True
                break
            context = candidate
        result["context"] = context
        result["characters"] = len(context)
        return result
