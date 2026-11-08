"""Conservative multilingual intent router for supported local engine actions."""

class CommandRouter:
    def route(self, text):
        q = (text or "").strip().lower()
        if any(x in q for x in (
            "remind me", "set reminder", "set a reminder", "reminder",
            "یاد دلانا", "یاد دلاؤ", "یاد دہانی", "یاد دلا دینا",
            "yaad dilana", "yaad dila", "mujhe yaad"
        )):
            return "reminder_schedule"
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
