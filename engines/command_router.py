"""Multilingual, conservative intent router for Laiba."""
import re
import unicodedata


class CommandRouter:

    @staticmethod
    def _normalize(text):
        value = unicodedata.normalize("NFKC", str(text or "")).casefold()
        value = value.replace("’", "'").replace("ـ", "")
        value = value.translate(str.maketrans({
            "ي": "ی", "ى": "ی", "ك": "ک",
            "ۀ": "ہ", "ة": "ہ"
        }))
        value = "".join(
            c for c in value
            if unicodedata.category(c) != "Mn"
        )
        value = value.replace("۔", " ")
        value = re.sub(r"[،,!?؛:()\[\]{}\"“”]+", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _has(q, phrases):
        for phrase in phrases:
            phrase = phrase.casefold()
            if phrase.isascii():
                if re.search(
                    r"(?<![a-z0-9_])" + re.escape(phrase) +
                    r"(?![a-z0-9_])", q
                ):
                    return True
            elif phrase in q:
                return True
        return False

    def route(self, text):
        q = self._normalize(text)

        if not q:
            return "chat"

        # Explicit approval commands.
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

        # GitHub Actions and APK builds.
        if self._has(q, (
            "github actions status", "github action status",
            "github build status", "check github build",
            "build status", "check build", "build complete",
            "build completed", "latest build", "workflow status",
            "workflow runs", "apk status", "apk ready",
            "apk complete", "apk tayar", "build ka haal",
            "build ka status", "بلڈ اسٹیٹس", "بلڈ چیک",
            "بلڈ مکمل", "بلڈ ہو گئی", "بلڈ کا حال",
            "اے پی کے اسٹیٹس", "اے پی کے تیار",
            "ورک فلو اسٹیٹس"
        )):
            return "build_status"

        # Bug analysis without changing files.
        if self._has(q, (
            "bug analysis", "analyze bugs", "analyse bugs",
            "find bugs", "find errors", "inspect bugs",
            "check for bugs", "debug project", "debug code",
            "project problems", "code problems",
            "bugs batao", "maslay dhoondo",
            "code mein bugs", "bug check",
            "بگز تلاش", "خرابیاں تلاش",
            "غلطیاں تلاش", "کوڈ کی غلطیاں",
            "پروجیکٹ کا تجزیہ", "بگ چیک"
        )):
            return "bug_analysis"

        # Update availability only; never implies installation.
        if self._has(q, (
            "check for update", "check update", "update check",
            "any update", "new update available",
            "latest update", "latest version", "new version",
            "update available", "app update", "apk update",
            "update yourself", "naya update", "nayi update",
            "update aya", "update aaya", "version check",
            "اپ ڈیٹ چیک", "اپڈیٹ چیک", "نیا اپ ڈیٹ",
            "نئی اپ ڈیٹ", "نیا ورژن", "اپ ڈیٹ آیا",
            "اپڈیٹ آیا", "اپ ڈیٹ دستیاب", "ورژن چیک"
        )):
            return "update_check"

        # GitHub commit history.
        if self._has(q, (
            "latest commits", "last commits", "recent commits",
            "show commits", "commit history", "git history",
            "commits dikhao", "commits parho",
            "آخری commits", "کمیٹس دکھاؤ", "کمیٹس پڑھو",
            "کمیٹس کی تاریخ"
        )):
            return "github_commits"

        # Repository file listing before individual file reading.
        if self._has(q, (
            "list repository files", "show repository files",
            "repository files", "repo files", "repo ki files",
            "repository ki files", "github files",
            "فائلوں کی فہرست", "ریپو کی فائلیں دکھاؤ",
            "تمام فائلیں دکھاؤ"
        )):
            return "github_file_list"

        # Repository file reading.
        if self._has(q, (
            "read file", "show file", "open file",
            "read repository file", "file content",
            "file ka code", "فائل پڑھو", "فائل دکھاؤ",
            "فائل کا کوڈ", "فائل کھولو"
        )):
            return "github_file_read"

        # Self-development creates a proposal, never automatic approval.
        if self._has(q, (
            "self develop", "self-development",
            "self development", "self update engine",
            "work on yourself", "improve yourself",
            "improve your code", "upgrade your engine",
            "improve this engine", "fix your code",
            "add a feature", "create a feature",
            "implement a feature", "change your code",
            "laiba improve", "laiba update yourself",
            "engine ko behtar", "engine ko improve",
            "engine par kaam", "engine pe kaam",
            "code ko behtar", "code improve",
            "khud ko behtar", "apne aap ko",
            "apni coding", "feature add", "feature banao",
            "feature shamil", "کوڈ بہتر", "اپنا کوڈ بہتر",
            "اپنی کوڈنگ", "سیلف اپڈیٹ", "سیلف ڈیولپمنٹ",
            "انجن پر کام", "انجن کو بہتر",
            "نیا فیچر", "فیچر شامل", "کوڈ میں تبدیلی",
            "اپنے اندر بہتری"
        )):
            return "development_propose"

        # ZIP export.
        if self._has(q, (
            "export zip", "create zip", "whatsapp zip",
            "zip export", "zip banao", "zip bana",
            "زپ بناؤ", "زپ بنا"
        )):
            return "zip_export"

        # 3D engine.
        if self._has(q, (
            "cube", "pyramid", "3d", "mesh", "obj", "stl",
            "ماڈل", "تھری ڈی"
        )):
            return "3d_status"

        # Local project file listing.
        if self._has(q, (
            "list files", "check files", "show files",
            "project files", "فائلیں چیک",
            "فائلیں دکھاؤ", "پروجیکٹ کی فائلیں"
        )):
            return "file_list"

        # External app opening.
        if self._has(q, (
            "open youtube", "open browser", "open google",
            "یوٹیوب کھولو", "براؤزر کھولو",
            "گوگل کھولو"
        )):
            return "open_link"

        # Natural-language update checks (including plural wording).
        if self._has(q, (
            "check for updates", "check updates", "updates check",
            "any updates", "are there updates", "look for updates",
            "search for updates", "do we have updates",
            "updates available", "update ka pata",
            "اپڈیٹس چیک", "اپ ڈیٹس چیک",
            "کیا اپڈیٹ ہے", "نئی اپڈیٹس"
        )):
            return "update_check"

        return "chat"
