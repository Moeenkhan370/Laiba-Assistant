"""Private, redacted runtime diagnostics for Laiba."""
import collections
import json
import os
import re
import sys
import threading
import traceback
from datetime import datetime, timezone


class RuntimeDiagnostics:
    MAX_ENTRIES = 300
    MAX_FILE_BYTES = 2 * 1024 * 1024

    def __init__(self, directory):
        self.directory = os.path.abspath(str(directory))
        os.makedirs(self.directory, exist_ok=True)
        self.path = os.path.join(
            self.directory, "laiba_runtime_errors.jsonl"
        )
        self.lock = threading.RLock()
        self.entries = collections.deque(maxlen=self.MAX_ENTRIES)
        self._old_sys_hook = None
        self._old_thread_hook = None
        self._load()

    @staticmethod
    def sanitize(value):
        text = str(value or "")
        text = re.sub(
            r"AIza[0-9A-Za-z_-]{20,}",
            "[REDACTED_API_KEY]", text
        )
        text = re.sub(
            r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+",
            r"\1[REDACTED]", text
        )
        text = re.sub(
            r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+",
            r"\1[REDACTED]", text
        )
        text = re.sub(
            r"(?i)(bearer\s+)[A-Za-z0-9._-]{16,}",
            r"\1[REDACTED]", text
        )
        return text[:7000]

    def _load(self):
        try:
            if not os.path.isfile(self.path):
                return
            with open(self.path, "r", encoding="utf-8") as stream:
                lines = stream.readlines()[-self.MAX_ENTRIES:]
            for line in lines:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        self.entries.append(item)
                except Exception:
                    continue
        except Exception:
            pass

    def record(self, category, event, details="", severity="INFO",
               traceback_text=""):
        item = {
            "time": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
            "severity": str(severity).upper()[:12],
            "category": self.sanitize(category)[:40],
            "event": self.sanitize(event)[:100],
            "details": self.sanitize(details)[:700],
            "traceback": self.sanitize(traceback_text)[:6000],
        }
        try:
            line = json.dumps(item, ensure_ascii=False) + "\n"
            with self.lock:
                self.entries.append(item)
                with open(self.path, "a", encoding="utf-8") as stream:
                    stream.write(line)
                if os.path.getsize(self.path) > self.MAX_FILE_BYTES:
                    keep = list(self.entries)
                    with open(self.path, "w", encoding="utf-8") as stream:
                        for entry in keep:
                            stream.write(
                                json.dumps(entry, ensure_ascii=False) + "\n"
                            )
        except Exception:
            pass

    def record_exception(self, category, event, exc,
                         severity="ERROR"):
        try:
            trace = "".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__
            ))
        except Exception:
            trace = repr(exc)
        self.record(
            category, event, repr(exc), severity=severity,
            traceback_text=trace
        )

    def recent(self, count=40):
        with self.lock:
            return list(self.entries)[-max(1, int(count)):]

    def format_text(self, count=100):
        lines = []
        for item in self.recent(count):
            lines.append(
                "[{time}] {severity} | {category} | {event}\n{details}".format(
                    **item
                )
            )
            if item.get("traceback"):
                lines.append(item["traceback"])
            lines.append("-" * 42)
        return "\n".join(lines) or "No runtime events recorded yet."

    def clear(self):
        with self.lock:
            self.entries.clear()
            try:
                with open(self.path, "w", encoding="utf-8"):
                    pass
            except Exception:
                pass

    def export_report(self):
        destination = os.path.join(
            self.directory,
            "laiba_diagnostic_report_{}.json".format(
                datetime.now().strftime("%Y%m%d_%H%M%S")
            )
        )
        report = {
            "created": datetime.now(timezone.utc).isoformat(),
            "application": "Laiba Assistant",
            "entries": self.recent(self.MAX_ENTRIES),
        }
        with open(destination, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        return destination

    def install_hooks(self):
        if self._old_sys_hook is not None:
            return

        self._old_sys_hook = sys.excepthook

        def system_hook(exc_type, exc_value, exc_tb):
            try:
                trace = "".join(traceback.format_exception(
                    exc_type, exc_value, exc_tb
                ))
                self.record(
                    "python", "Uncaught main-thread exception",
                    repr(exc_value), severity="CRITICAL",
                    traceback_text=trace
                )
            finally:
                self._old_sys_hook(exc_type, exc_value, exc_tb)

        sys.excepthook = system_hook

        if hasattr(threading, "excepthook"):
            self._old_thread_hook = threading.excepthook

            def thread_hook(args):
                try:
                    trace = "".join(traceback.format_exception(
                        args.exc_type, args.exc_value, args.exc_traceback
                    ))
                    self.record(
                        "python", "Uncaught background-thread exception",
                        repr(args.exc_value), severity="CRITICAL",
                        traceback_text=trace
                    )
                finally:
                    self._old_thread_hook(args)

            threading.excepthook = thread_hook


_DIAGNOSTICS = None


def configure_diagnostics(directory):
    global _DIAGNOSTICS
    _DIAGNOSTICS = RuntimeDiagnostics(directory)
    _DIAGNOSTICS.install_hooks()
    _DIAGNOSTICS.record("app", "Runtime diagnostics initialized")
    return _DIAGNOSTICS


def get_diagnostics():
    return _DIAGNOSTICS
