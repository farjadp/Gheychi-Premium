with open("tg_link_handler.py", "r") as f:
    code = f.read()

size_patch = """
    if error.startswith("file_too_large:"):
        parts = error.split(":")
        size = parts[1] if len(parts) > 1 else "50+"
        limit = parts[2] if len(parts) > 2 else "50"
        return get_text("telegram_size_limit", user_lang, size_mb=size, max_size_mb=limit)

    if error.startswith("flood_wait:"):
"""

code = code.replace("    if error.startswith(\"flood_wait:\"):\n", size_patch)

with open("tg_link_handler.py", "w") as f:
    f.write(code)
