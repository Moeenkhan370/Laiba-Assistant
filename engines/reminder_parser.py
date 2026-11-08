"""Basic Urdu, Roman Urdu and English relative-time reminder parser."""
import re
import time

def parse_reminder(text):
    original = str(text or "").strip()
    q = original.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    q = q.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).lower()

    patterns = [
        (r'(\d+)\s*(?:seconds?|secs?|سیکنڈ)\s*(?:بعد|میں|later|from now)?', 1),
        (r'(\d+)\s*(?:minutes?|mins?|منٹ)\s*(?:بعد|میں|later|from now)?', 60),
        (r'(\d+)\s*(?:hours?|hrs?|گھنٹے|گھنٹہ)\s*(?:بعد|میں|later|from now)?', 3600),
        (r'(\d+)\s*(?:days?|دن)\s*(?:بعد|میں|later|from now)?', 86400),
    ]

    match = None
    seconds = 0
    for pattern, multiplier in patterns:
        match = re.search(pattern, q)
        if match:
            seconds = int(match.group(1)) * multiplier
            break

    if not match or seconds <= 0:
        return None, "براہِ کرم وقت بتائیں، مثلاً 10 منٹ بعد یا 2 گھنٹے بعد۔"

    if seconds < 10:
        return None, "یاددہانی کے لیے کم از کم 10 سیکنڈ کا وقت رکھیں۔"

    message = q[:match.start()] + " " + q[match.end():]
    message = re.sub(
        r'\b(?:remind me|reminder|please|to|in|after|later|mujhe|mera|meri|yaad|dilana|dila dena|yaad karana|baad|mein|minute|minutes|hour|hours|day|days)\b',
        ' ', message
    )
    message = re.sub(
        r'(مجھے|یاد دلانا|یاد دلادینا|یاد دلاؤ|یاد دہانی|براہ کرم|بعد|میں|منٹ|گھنٹے|گھنٹہ|دن)',
        ' ', message
    )
    message = re.sub(r'\s+', ' ', message).strip(" ،,۔.!")

    if not message:
        message = "آپ کی یاددہانی کا وقت ہو گیا ہے۔"

    title = "Laiba Reminder"
    time_ms = int((time.time() + seconds) * 1000)
    return (title, message, time_ms, 0), None
