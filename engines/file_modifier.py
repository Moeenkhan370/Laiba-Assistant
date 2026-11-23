"""Safe, project-root constrained file operations for Laiba."""
import ast
import os
import shutil
import stat
import tempfile
import time
import uuid
from pathlib import Path


class FileModifierEngine:
    """Read, write, append, edit, delete and restore project files safely."""

    MAX_FILE_BYTES = 5 * 1024 * 1024

    BLOCKED_DIRS = {
        ".git", ".laiba_backups", ".ssh",
        "secrets", "credentials", "__pycache__"
    }
    BLOCKED_NAMES = {
        "id_rsa", "id_ed25519", "authorized_keys",
        "known_hosts", "credentials.json", "secrets.json"
    }
    BLOCKED_SUFFIXES = {
        ".pem", ".key", ".p12", ".pfx",
        ".keystore", ".jks"
    }

    def __init__(self, base_dir=".", backup_dir=".laiba_backups",
                 max_file_bytes=None):
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

        backup_candidate = Path(backup_dir).expanduser()
        if not backup_candidate.is_absolute():
            backup_candidate = self.base_dir / backup_candidate

        self.backup_dir = backup_candidate.resolve()
        if (self.backup_dir == self.base_dir
                or self.base_dir not in self.backup_dir.parents):
            raise ValueError("Backup directory must be inside project root.")

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_bytes = int(
            max_file_bytes or self.MAX_FILE_BYTES
        )
        if self.max_file_bytes < 1:
            raise ValueError("Maximum file size must be positive.")

    def _is_protected(self, relative):
        parts = [part.casefold() for part in relative.parts]
        backup_parts = [
            part.casefold()
            for part in self.backup_dir.relative_to(self.base_dir).parts
        ]

        if any(
            parts[:index + 1] == backup_parts[:index + 1]
            for index in range(len(backup_parts))
        ):
            return True

        for part in parts:
            if part in self.BLOCKED_DIRS:
                return True
            if part == ".env" or part.startswith(".env."):
                return True
            if part in self.BLOCKED_NAMES:
                return True
            if Path(part).suffix.casefold() in self.BLOCKED_SUFFIXES:
                return True
        return False

    def _resolve(self, filepath, allow_root=False):
        raw = Path(str(filepath)).expanduser()
        candidate = raw if raw.is_absolute() else self.base_dir / raw
        candidate = candidate.resolve()

        if candidate != self.base_dir and self.base_dir not in candidate.parents:
            raise ValueError("Path is outside the authorized project directory.")

        if candidate == self.base_dir:
            if allow_root:
                return candidate
            raise ValueError("Project root is not a file.")

        relative = candidate.relative_to(self.base_dir)
        if self._is_protected(relative):
            raise ValueError("Access to protected project data is denied.")

        return candidate

    def _read_text(self, filepath):
        target = self._resolve(filepath)
        if not target.is_file():
            raise FileNotFoundError("File does not exist.")

        size = target.stat().st_size
        if size > self.max_file_bytes:
            raise ValueError("File exceeds the configured size limit.")

        return target.read_text(encoding="utf-8")

    def _backup(self, target):
        if not target.exists():
            return None
        if not target.is_file():
            raise ValueError("Target is not a regular file.")

        relative = target.relative_to(self.base_dir)
        folder = time.strftime("%Y%m%d_%H%M%S_%f")
        folder += "_" + uuid.uuid4().hex[:8]
        destination = self.backup_dir / folder / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        temporary = destination.with_name(
            destination.name + "." + uuid.uuid4().hex + ".tmp"
        )
        try:
            shutil.copy2(target, temporary)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

        return destination

    def read_file(self, filepath):
        try:
            return self._read_text(filepath)
        except Exception as exc:
            return "Error reading file: {}".format(exc)

    def write_file(self, filepath, content, confirm=False):
        if not confirm:
            return "Confirmation required before writing or replacing a file."

        temporary_name = None
        try:
            if not isinstance(content, str):
                raise TypeError("Content must be text.")

            encoded = content.encode("utf-8")
            if len(encoded) > self.max_file_bytes:
                raise ValueError("Content exceeds the configured size limit.")

            target = self._resolve(filepath)
            if target.suffix.casefold() == ".py":
                ast.parse(content)

            target.parent.mkdir(parents=True, exist_ok=True)
            target = self._resolve(filepath)

            if target.exists() and not target.is_file():
                raise ValueError("Target is not a regular file.")

            backup = self._backup(target)
            old_mode = (
                stat.S_IMODE(target.stat().st_mode)
                if target.exists() else None
            )

            fd, temporary_name = tempfile.mkstemp(
                prefix=".laiba_write_", dir=str(target.parent)
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())

            if old_mode is not None:
                os.chmod(temporary_name, old_mode)

            os.replace(temporary_name, target)
            temporary_name = None

            try:
                directory_fd = os.open(str(target.parent), os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass

            relative = target.relative_to(self.base_dir)
            backup_text = (
                str(backup.relative_to(self.base_dir))
                if backup else "not needed"
            )
            return "Success: wrote {} (backup: {}).".format(
                relative, backup_text
            )

        except Exception as exc:
            return "Error writing file: {}".format(exc)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def append_to_file(self, filepath, content, confirm=False):
        if not confirm:
            return "Confirmation required before modifying a file."
        try:
            old = self._read_text(filepath)
            if not isinstance(content, str):
                raise TypeError("Content must be text.")
            return self.write_file(
                filepath, old + content, confirm=True
            )
        except Exception as exc:
            return "Error appending to file: {}".format(exc)

    def modify_line(self, filepath, old_line, new_line, confirm=False):
        if not confirm:
            return "Confirmation required before modifying a file."
        if not isinstance(old_line, str) or not old_line:
            return "Error: target text must be a non-empty string."
        if not isinstance(new_line, str):
            return "Error: replacement text must be a string."

        try:
            old = self._read_text(filepath)
            if old_line not in old:
                return "Error: target text not found."
            updated = old.replace(old_line, new_line, 1)
            return self.write_file(filepath, updated, confirm=True)
        except Exception as exc:
            return "Error modifying file: {}".format(exc)

    def delete_file(self, filepath, confirm=False):
        if not confirm:
            return "Confirmation required before deleting a file."
        try:
            target = self._resolve(filepath)
            if not target.is_file():
                return "Error: file does not exist."

            backup = self._backup(target)
            target.unlink()
            return "Success: deleted {} (backup retained: {}).".format(
                target.relative_to(self.base_dir),
                backup.relative_to(self.base_dir)
            )
        except Exception as exc:
            return "Error deleting file: {}".format(exc)

    def restore_last_backup(self, filepath, confirm=False):
        if not confirm:
            return "Confirmation required before restoring a backup."

        try:
            target = self._resolve(filepath)
            relative = target.relative_to(self.base_dir)
            folders = sorted(
                (
                    item for item in self.backup_dir.iterdir()
                    if item.is_dir() and not item.is_symlink()
                ),
                key=lambda item: item.name,
                reverse=True
            )

            for folder in folders:
                candidate = folder / relative
                if candidate.is_file() and not candidate.is_symlink():
                    content = candidate.read_text(encoding="utf-8")
                    result = self.write_file(
                        filepath, content, confirm=True
                    )
                    if result.startswith("Success:"):
                        return "Restored latest backup. " + result
                    return result

            return "Error: no backup found for this file."
        except Exception as exc:
            return "Error restoring backup: {}".format(exc)

    def list_dir(self, directory="."):
        try:
            target = self._resolve(directory, allow_root=True)
            if not target.is_dir():
                return "Error: directory does not exist."

            visible = []
            for item in target.iterdir():
                try:
                    resolved = self._resolve(item)
                    if resolved.is_dir() or resolved.is_file():
                        visible.append(item.name)
                except (ValueError, OSError):
                    continue

            return sorted(visible, key=str.casefold)
        except Exception as exc:
            return "Error listing directory: {}".format(exc)
