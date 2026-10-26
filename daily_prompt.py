"""Read the dated challenge snapshot; never relabel yesterday's prompt as today."""
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
PROMPT_FILE = ROOT / "daily_prompt.txt"
SGT = ZoneInfo("Asia/Singapore")


def load_daily_prompt() -> tuple[str, str, str]:
    # Metadata is atomically replaced by the generator. The txt file is a mirror.
    meta = json.loads((ROOT / "daily_prompt_meta.json").read_text(encoding="utf-8"))
    text = meta["prompt"].strip()
    day = meta["date_sgt"]
    from datetime import date
    date.fromisoformat(day)
    if not text:
        raise RuntimeError("daily prompt snapshot is empty")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return text, day, digest
