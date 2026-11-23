"""Multilingual intent router for Laiba's supported engine actions."""
import re
import unicodedata


class CommandRouter:
    """Normalize mixed Urdu, Roman Urdu and English commands."""

    @staticmethod
    def _normalize(text):
        value = unicodedata.normalize("NFKC", str(text or "")).casefold()
        value = value.replace("’", "'").replace("۔", " ")
        value = re.sub(r"[،,!?؛:()\[\]{}]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _has(q, phrases):
        return any(phrase in q for phrase in phrases)

    def route(self, text):
        q = self._normalize(text)

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
            "build status", "check build", "apk status",
            "workflow status", "بلڈ اسٹیٹس", "اے پی کے اسٹیٹس",
            "بلڈ چیک کرو", "بلڈ کا حال"
        )):
            return "build_status"

        if self._has(q, (
            "self develop", "self-development", "develop yourself",
            "improve yourself", "add feature", "create feature",
            "implement feature", "fix your code", "improve your code",
            "خود کو بہتر بناؤ", "اپنا کوڈ بہتر کرو",
            "نیا فیچر بناؤ", "فیچر شامل کرو", "کوڈ میں تبدیلی",
            "اپنے اندر بہتری لاؤ"
        )):
            return "development_propose"

        if self._has(q, (
            "check update", "update yourself", "check for update",
            "اپ ڈیٹ", "اپڈیٹ", "نیا ورژن", "اپ ڈیٹ چیک کرو"
        )):
            return "update_check"

        if self._has(q, (
            "export zip", "create zip", "whatsapp zip", "zip export",
            "zip بنا", "زپ بنا"
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
