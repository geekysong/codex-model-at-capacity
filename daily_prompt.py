"""The single prompt shared by the Codex and Claude daily control runs."""
import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
PROMPT_FILE = ROOT / "daily_prompt.txt"
SGT = ZoneInfo("Asia/Singapore")


def load_daily_prompt() -> tuple[str, str, str]:
    text = PROMPT_FILE.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"daily prompt is empty: {PROMPT_FILE}")
    day = datetime.now(SGT).strftime("%Y-%m-%d")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return text, day, digest
