import subprocess
import json

def _extract_metadata(file_path: str) -> dict:
    meta = {"width": None, "height": None}
    if not file_path: return meta
    try:
        cmd_probe = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", file_path
        ]
        out = subprocess.check_output(cmd_probe, text=True, timeout=10)
        data = json.loads(out)
        stream = data.get("streams", [{}])[0]
        meta["width"] = int(stream.get("width")) if stream.get("width") else None
        meta["height"] = int(stream.get("height")) if stream.get("height") else None
    except Exception:
        pass
    return meta
