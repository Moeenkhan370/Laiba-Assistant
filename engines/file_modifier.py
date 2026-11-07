"""Constrained project file operations with backups and atomic writes."""
import ast
import os
import shutil
import tempfile
from pathlib import Path


class FileModifierEngine:
    def __init__(self, base_dir=".", backup_dir=".laiba_backups"):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.backup_dir = (self.base_dir / backup_dir).resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, filepath):
        candidate = (self.base_dir / str(filepath)).resolve()
        if candidate != self.base_dir and self.base_dir not in candidate.parents:
            raise ValueError("Path is outside the authorized project directory")
        return candidate

    def _backup(self, target):
        if target.exists() and target.is_file():
            rel = target.relative_to(self.base_dir)
            dest = self.backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(target), str(dest))
            return str(dest)
        return None

    def read_file(self, filepath):
        try:
            target = self._resolve(filepath)
            if not target.is_file():
                return "Error: file does not exist."
            return target.read_text(encoding="utf-8")
        except Exception as exc:
            return "Error reading file: {}".format(exc)

    def write_file(self, filepath, content, confirm=False):
        if not confirm:
            return "Confirmation required before writing or replacing a file."
        try:
            target = self._resolve(filepath)
            if not isinstance(content, str):
                raise TypeError("content must be text")
            if target.suffix == ".py":
                ast.parse(content)
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = self._backup(target)
            fd, temp_name = tempfile.mkstemp(prefix=".laiba_", dir=str(target.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, str(target))
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            return "Success: wrote {} (backup: {}).".format(target.relative_to(self.base_dir), backup or "not needed")
        except Exception as exc:
            return "Error writing file: {}".format(exc)

    def append_to_file(self, filepath, content, confirm=False):
        if not confirm:
            return "Confirmation required before modifying a file."
        old = self.read_file(filepath)
        if old.startswith("Error:"):
            old = ""
        return self.write_file(filepath, old + str(content), confirm=True)

    def modify_line(self, filepath, old_line, new_line, confirm=False):
        if not confirm:
            return "Confirmation required before modifying a file."
        old = self.read_file(filepath)
        if old.startswith("Error"):
            return old
        if old_line not in old:
            return "Error: target text not found."
        return self.write_file(filepath, old.replace(old_line, new_line, 1), confirm=True)

    def delete_file(self, filepath, confirm=False):
        if not confirm:
            return "Confirmation required before deleting a file."
        try:
            target = self._resolve(filepath)
            if not target.is_file():
                return "Error: file does not exist."
            self._backup(target)
            target.unlink()
            return "Success: deleted {} (backup retained).".format(target.relative_to(self.base_dir))
        except Exception as exc:
            return "Error deleting file: {}".format(exc)

    def list_dir(self, directory="."):
        try:
            target = self._resolve(directory)
            if not target.is_dir():
                return "Error: directory does not exist."
            return sorted(p.name for p in target.iterdir())
        except Exception as exc:
            return "Error listing directory: {}".format(exc)
