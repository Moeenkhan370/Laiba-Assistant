"""Conservative multilingual intent router for supported local engine actions."""
import re

class CommandRouter:
    def route(self, text):
        q = (text or "").strip().lower()
        if q in ("build status", "check build", "apk status", "بلڈ اسٹیٹس", "اے پی کے اسٹیٹس"):
            return "build_status"
        if re.fullmatch(r"run workflow\s+[a-zA-Z0-9_.-]+", q):
            return "workflow_dispatch"
        if re.fullmatch(r"(?:approve|apply)\s+(?:(?:proposal|development)\s+)?[0-9]{10,}-[0-9a-f]{8}", q):
            return "development_apply"
        if re.match(r"^(?:approve|apply)\s+(?:(?:proposal|development)\s+)?[0-9]{10,}-[0-9a-f]{8}$", q):
            return "development_apply"
        if any(x in q for x in ("self develop", "self-development", "develop yourself", "improve yourself", "add feature", "create feature", "implement feature", "خود کو بہتر بناؤ", "نیا فیچر بناؤ", "فیچر شامل کرو", "کوڈ میں تبدیلی")):
            return "development_propose"
        if any(x in q for x in ("check update", "update yourself", "اپ ڈیٹ", "اپڈیٹ", "نیا ورژن")):
            return "update_check"
        if any(x in q for x in ("export zip", "create zip", "whatsapp zip", "zip export", "zip بنا", "زپ بنا")):
            return "zip_export"
        if any(x in q for x in ("cube", "pyramid", "3d", "mesh", "obj", "stl", "ماڈل", "تھری ڈی")):
            return "3d_status"
        if any(x in q for x in ("list files", "check files", "فائلیں چیک", "فائلیں دکھاؤ")):
            return "file_list"
        if any(x in q for x in ("open youtube", "open browser", "open google", "یوٹیوب کھولو", "براؤزر کھولو")):
            return "open_link"
        return "chat"
