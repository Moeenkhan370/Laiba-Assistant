"""Multilingual, conservative intent router for Laiba."""
import re
import unicodedata


class CommandRouter:
    """Recognize common English, Urdu and Roman-Urdu action requests."""

    @staticmethod
    def _normalize(text):
        value = unicodedata.normalize("NFKC", str(text or "")).casefold()
        value = value.replace("’", "'").replace("۔", " ")
        value = re.sub(r"[،,!?؛:()\[\]{}\"“”]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _has(q, phrases):
        return any(phrase in q for phrase in phrases)

    def route(self, text):
        q = self._normalize(text)

        if "github actions" in q and any(x in q for x in ("status", "state", "haal")):
            return "build_status"

        if any(x in q for x in ("naya update", "new update")) and any(
            x in q for x in ("aya", "aaya", "available", "hai", "ha", "check")
        ):
            return "update_check"

        # Explicit approvals only. Never infer approval from a vague reply.
        if re.fullmatch(
            r"(?:approve|apply)\s+(?:(?:proposal|development)\s+)?"
            r"[0-9]{10,}-[0-9a-f]{8}", q
        ):
            return "development_apply"

        if re.fullmatch(
            r"(?:approve|confirm)\s+(?:workflow|run)\s+"
            r"[a-zA-Z0-9_.-]+", q
        ):
            return "workflow_approve"

        if re.fullmatch(
            r"(?:run|start|dispatch)\s+workflow\s+"
            r"[a-zA-Z0-9_.-]+", q
        ):
            return "workflow_dispatch"

        # Build and GitHub Actions status.
        if self._has(q, (
            "build status", "check build", "build complete",
            "build completed", "is build done", "build hua",
            "build ho gayi", "build ban gayi", "build ka status",
            "build ka haal", "apk status", "apk ready",
            "apk ban gai", "apk ban gayi", "apk tayar",
            "apk complete", "workflow status", "workflow run",
            "github action status", "github actions status",
            "latest build", "meri build", "mera build",
            "بلڈ اسٹیٹس", "بلڈ چیک", "بلڈ مکمل", "بلڈ ہو گئی",
            "بلڈ بن گئی", "بلڈ کا حال", "اے پی کے اسٹیٹس",
            "اے پی کے بن گئی", "اے پی کے تیار", "ورک فلو اسٹیٹس"
        )):
            return "build_status"

        # Self-development requests create a reviewable proposal only.
        if self._has(q, (
            "self develop", "self-development", "self development",
            "self update engine", "work on yourself",
            "work on self update", "work on the engine",
            "improve yourself", "improve your code",
            "make yourself better", "develop yourself",
            "upgrade your engine", "improve this engine",
            "fix your code", "add a feature", "create a feature",
            "implement a feature", "change your code",
            "laiba improve", "laiba update yourself",
            "engine ko behtar", "engine ko improve",
            "engine par kaam", "engine pe kaam",
            "code ko behtar", "code improve",
            "apna code", "apne code", "khud ko behtar",
            "apne aap ko", "apni coding", "naya feature",
            "feature add", "feature banao", "feature shamil",
            "is engine ko", "iss engine ko",
            "خود کو بہتر", "اپنا کوڈ بہتر", "اپنے کوڈ",
            "اپنی کوڈنگ", "سیلف اپڈیٹ", "سیلف ڈیولپمنٹ",
            "انجن پر کام", "انجن کو بہتر", "نیا فیچر",
            "فیچر شامل", "کوڈ میں تبدیلی", "اپنے اندر بہتری"
        )):
            return "development_propose"

        # Update check is read-only; it does not install anything.
        if self._has(q, (
            "check update", "check for update", "update check",
            "any update", "is there an update", "new update",
            "latest update", "latest version", "new version",
            "update available", "app update", "apk update",
            "update yourself", "اپ ڈیٹ چیک", "اپڈیٹ چیک",
            "نیا اپ ڈیٹ", "نئی اپ ڈیٹ", "نیا ورژن",
            "اپ ڈیٹ آیا", "اپڈیٹ آیا", "اپ ڈیٹ دستیاب",
            "اپڈیٹ دستیاب", "ورژن چیک"
        )):
            return "update_check"

        if self._has(q, (
            "latest commits", "last commits", "recent commits",
            "show latest", "show last", "commit history",
            "commits dikhao", "commits parho", "آخری commits",
            "کمیٹس دکھاؤ", "کمیٹس پڑھو"
        )):
            return "github_commits"

        if self._has(q, (
            "list repository files", "show repository files",
            "repository files", "repo files", "repo ki files",
            "repository ki files", "فائلوں کی فہرست",
            "ریپو کی فائلیں دکھاؤ"
        )):
            return "github_file_list"

        if self._has(q, (
            "read file", "show file", "read repository file",
            "file content", "file ka code", "فائل پڑھو",
            "فائل دکھاؤ", "فائل کا کوڈ"
        )):
            return "github_file_read"

        if self._has(q, (
            "export zip", "create zip", "whatsapp zip", "zip export",
            "zip bana", "zip banao", "zip بنا", "زپ بنا"
        )):
            return "zip_export"

        if self._has(q, (
            "cube", "pyramid", "3d", "mesh", "obj", "stl",
            "ماڈل", "تھری ڈی"
        )):
            return "3d_status"

        if self._has(q, (
            "list files", "check files", "فائلیں چیک",
            "فائلیں دکھاؤ"
        )):
            return "file_list"

        if self._has(q, (
            "open youtube", "open browser", "open google",
            "یوٹیوب کھولو", "براؤزر کھولو"
        )):
            return "open_link"

        return "chat"
