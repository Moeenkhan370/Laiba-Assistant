"""Offline repository scanner and static coding intelligence agent."""
import ast
import json
import re
from pathlib import Path

class LocalCodingAgent:
    ALLOWED = {
        ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
        ".ini", ".cfg", ".kv", ".spec", ".sh", ".xml", ".java",
        ".gradle", ".properties"
    }
    EXCLUDED_DIRS = {
        ".git", ".laiba_backups", "__pycache__", ".buildozer",
        "bin", "venv", ".venv", "env", "node_modules", "dist",
        "build", ".pytest_cache"
    }
    SECRET_NAMES = {
        ".env", "laiba_config.json", "secrets.json",
        "credentials.json", "id_rsa", "id_ed25519"
    }
    MAX_FILE_BYTES = 5 * 1024 * 1024
    MAX_TOTAL_BYTES = 50 * 1024 * 1024

    def __init__(self, project_root="."):
        self.root = Path(project_root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError("Project root is not a directory.")
        self.files = {}
        self.records = {}
        self.findings = []
        self.dependencies = []

    def scan(self):
        """Read eligible text files; never follow symlinks or enter protected dirs."""
        found = {}
        total = 0
        for current, dirs, names in __import__("os").walk(str(self.root), followlinks=False):
            current_path = Path(current)
            dirs[:] = sorted(
                d for d in dirs
                if d not in self.EXCLUDED_DIRS
                and not d.startswith(".")
                and not (current_path / d).is_symlink()
            )
            for name in sorted(names):
                path = current_path / name
                if path.is_symlink() or name.casefold() in self.SECRET_NAMES:
                    continue
                if name.casefold().startswith((".env.", "secret", "credential")):
                    continue
                if path.suffix.lower() not in self.ALLOWED:
                    continue
                try:
                    size = path.stat().st_size
                    if size > self.MAX_FILE_BYTES:
                        continue
                    if total + size > self.MAX_TOTAL_BYTES:
                        raise RuntimeError("Repository exceeds the 50 MB scan limit.")
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                relative = path.relative_to(self.root).as_posix()
                found[relative] = content
                total += size
        self.files = dict(sorted(found.items()))
        return {
            "root": str(self.root),
            "file_count": len(self.files),
            "total_bytes": total,
            "files": list(self.files)
        }

    @staticmethod
    def _module_name(path):
        value = path[:-3].replace("/", ".")
        if value.endswith(".__init__"):
            value = value[:-9]
        return value

    def analyze(self):
        """Build AST inventory, local dependency map, and conservative bug signals."""
        if not self.files:
            self.scan()

        module_paths = {
            self._module_name(path): path
            for path in self.files if path.endswith(".py")
        }
        records, findings, dependencies = {}, [], []

        for path, source in self.files.items():
            if not path.endswith(".py"):
                continue
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError as exc:
                findings.append({
                    "kind": "syntax_error", "severity": "high",
                    "path": path, "line": exc.lineno or 1,
                    "message": exc.msg
                })
                continue

            symbols, imports = [], []

            class ScopeVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.scope = []

                def _visit_definition(self, node, kind):
                    qualified = ".".join(self.scope + [node.name])
                    symbols.append({
                        "kind": kind,
                        "name": node.name,
                        "qualified_name": qualified,
                        "parent": ".".join(self.scope) or None,
                        "line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno)
                    })
                    self.scope.append(node.name)
                    self.generic_visit(node)
                    self.scope.pop()

                def visit_ClassDef(self, node):
                    self._visit_definition(node, "class")

                def visit_FunctionDef(self, node):
                    self._visit_definition(node, "function")

                def visit_AsyncFunctionDef(self, node):
                    self._visit_definition(node, "async_function")

                def visit_Import(self, node):
                    for alias in node.names:
                        imports.append((alias.name, node.lineno))
                    self.generic_visit(node)

                def visit_ImportFrom(self, node):
                    module = "." * node.level + (node.module or "")
                    imports.append((module, node.lineno))
                    self.generic_visit(node)

            visitor = ScopeVisitor()
            visitor.visit(tree)
            symbols.sort(key=lambda x: (x["line"], x["name"]))
            records[path] = {
                "symbols": sorted(symbols, key=lambda x: (x["line"], x["name"])),
                "imports": [{"module": m, "line": n} for m, n in imports]
            }

            for module, line in imports:
                resolved = module_paths.get(module, "external_or_unresolved")
                dependencies.append({
                    "source": path, "line": line,
                    "module": module, "target": resolved
                })

            findings.extend(self._inspect_ast(path, tree))

        self.records = records
        self.findings = sorted(findings, key=lambda x: (x["path"], x["line"]))
        self.dependencies = dependencies
        return self.report()

    def _inspect_ast(self, path, tree):
        """Report concrete suspicious constructs, not speculative bug claims."""
        results = []
        for node in ast.walk(tree):
            line = getattr(node, "lineno", 1)

            if isinstance(node, ast.ExceptHandler) and node.type is None:
                results.append(self._finding(
                    path, line, "broad_exception", "medium",
                    "Bare except catches every exception and can hide failures."
                ))
            elif isinstance(node, ast.ExceptHandler):
                if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        results.append(self._finding(
                            path, line, "ignored_exception", "medium",
                            "Exception is silently ignored with pass."
                        ))
            elif isinstance(node, ast.Call):
                name = self._call_name(node.func)
                if name in {"eval", "exec"}:
                    results.append(self._finding(
                        path, line, "dynamic_execution", "high",
                        "{} executes dynamically supplied code; verify input trust.".format(name)
                    ))
                if name.endswith("Popen") or name.endswith("run") or name.endswith("call"):
                    if any(k.arg == "shell" and isinstance(k.value, ast.Constant)
                           and k.value.value is True for k in node.keywords):
                        results.append(self._finding(
                            path, line, "shell_true", "high",
                            "Subprocess uses shell=True; review command construction."
                        ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defaults = list(node.args.defaults) + [
                    d for d in node.args.kw_defaults if d is not None
                ]
                for default in defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        results.append(self._finding(
                            path, node.lineno, "mutable_default", "medium",
                            "Function has a mutable default argument."
                        ))
                        break
        return results

    @staticmethod
    def _call_name(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""

    @staticmethod
    def _finding(path, line, kind, severity, message):
        return {
            "kind": kind, "severity": severity,
            "path": path, "line": line, "message": message
        }

    def report(self):
        inventory = []
        for path, content in self.files.items():
            inventory.append({
                "path": path,
                "bytes": len(content.encode("utf-8")),
                "lines": len(content.splitlines())
            })
        return {
            "root": str(self.root),
            "files": inventory,
            "python_files_parsed": len(self.records),
            "symbols": self.records,
            "dependencies": self.dependencies,
            "findings": self.findings
        }

    @staticmethod
    def _terms(text):
        return {
            token.casefold() for token in
            re.findall(r"[A-Za-z_][A-Za-z_0-9]{2,}|[ء-ی]{3,}", str(text or ""))
        }

    def find_feature_locations(self, request, limit=30):
        """Locate likely implementation files and symbols for a requested feature."""
        if not self.records:
            self.analyze()
        terms = self._terms(request)
        ranked = []
        for path, source in self.files.items():
            lower_path = path.casefold()
            lower_source = source.casefold()
            score = sum(3 for term in terms if term in lower_path)
            score += sum(1 for term in terms if term in lower_source)
            matching_symbols = []
            for symbol in self.records.get(path, {}).get("symbols", []):
                if any(term in symbol["name"].casefold() for term in terms):
                    matching_symbols.append(symbol)
                    score += 4
            if score:
                ranked.append({
                    "path": path, "score": score,
                    "matching_symbols": matching_symbols
                })
        return sorted(ranked, key=lambda x: (-x["score"], x["path"]))[:limit]

    def build_context(self, request, max_chars=14000, limit=12):
        """Return only relevant code excerpts with exact source line numbers."""
        matches = self.find_feature_locations(request, limit=limit)
        terms = self._terms(request)
        sections, used = [], 0

        for match in matches:
            path = match["path"]
            lines = self.files[path].splitlines()
            selected = set()

            for symbol in match["matching_symbols"]:
                start = max(1, symbol["line"] - 2)
                end = min(len(lines), symbol["end_line"] + 2)
                selected.update(range(start, end + 1))

            if not selected:
                for number, line in enumerate(lines, 1):
                    if any(term in line.casefold() for term in terms):
                        selected.update(range(max(1, number - 2),
                                               min(len(lines), number + 2) + 1))

            if not selected:
                selected.update(range(1, min(len(lines), 12) + 1))

            excerpt = "\n".join(
                "{}: {}".format(number, lines[number - 1])
                for number in sorted(selected)
            )
            section = "\n--- {} ---\n{}".format(path, excerpt)
            if used + len(section) > max_chars:
                remaining = max_chars - used
                if remaining > 100:
                    sections.append(section[:remaining])
                break
            sections.append(section)
            used += len(section)

        return {
            "request": str(request),
            "matches": matches,
            "context": "\n".join(sections),
            "characters": used
        }

    def analyze_feature(self, request, max_chars=14000):
        return {
            "feature_locations": self.find_feature_locations(request),
            "relevant_context": self.build_context(request, max_chars=max_chars)
        }

    def save_report(self, destination):
        destination = Path(destination)
        if not destination.is_absolute():
            destination = self.root / destination
        destination = destination.resolve()
        if self.root not in destination.parents:
            raise ValueError("Report destination must be inside project root.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.report(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return str(destination)
