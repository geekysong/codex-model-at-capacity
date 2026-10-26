#!/usr/bin/env python3
"""Generate one compact, testable SVG benchmark prompt for the new day."""
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from daily_prompt import PROMPT_FILE, SGT, load_daily_prompt
from claude_daily import bounded_lock, write_json

ROOT = Path(__file__).resolve().parent
KEY_FILE = ROOT / ".secrets" / "anthropic_api_key"
MODEL = "claude-fable-5-1"
GENERATOR_PROMPT = """Write one concise benchmark instruction for an AI that must output a single self-contained SVG. The task should fit a 600x400 canvas and test a varied daily visual reasoning challenge with an objectively checkable answer. Vary topics across geometry, spatial puzzles, patterns, data visualization, and everyday reasoning; do not limit challenges to physics. Prefer 2-4 clear constraints. Return only the instruction, no markdown, no solution, and no SVG. It must explicitly require output only SVG code and readable non-overlapping labels."""


def generate() -> int:
    today = datetime.now(SGT).date().isoformat()
    try:
        if load_daily_prompt()[1] == today:
            print(f"daily prompt already generated for {today}; no API call", flush=True)
            return 0
    except (OSError, ValueError, KeyError, RuntimeError):
        pass
    key = os.environ.get("ANTHROPIC_API_KEY") or (KEY_FILE.read_text(encoding="utf-8").strip() if KEY_FILE.exists() else "")
    if not key:
        print("daily prompt generation skipped: no Anthropic key")
        return 2
    attempt = ROOT / ".claude-state" / f"prompt-{today}.json"
    if attempt.exists():
        print("daily prompt prior attempt failed/uncertain; inspect state before any paid retry", flush=True)
        return 1
    write_json(attempt, {"date_sgt": today, "status": "started"})
    body = json.dumps({"model": MODEL, "max_tokens": 500, "messages": [{"role": "user", "content": GENERATOR_PROMPT}]}).encode()
    req = Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"
    })
    try:
        with urlopen(req, timeout=90) as response:
            result = json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"daily prompt generation failed: {type(exc).__name__}")
        return 1
    prompt = "\n".join(x.get("text", "") for x in result.get("content", []) if x.get("type") == "text").strip()
    if not prompt or "svg" not in prompt.lower():
        print("daily prompt generation failed: invalid response")
        return 1
    PROMPT_FILE.write_text(prompt + "\n", encoding="utf-8")
    meta = {
        "date_sgt": today,
        "model": result.get("model", MODEL),
        "input_tokens": (result.get("usage") or {}).get("input_tokens"),
        "output_tokens": (result.get("usage") or {}).get("output_tokens"),
        "prompt": prompt,
    }
    write_json(ROOT / "daily_prompt_meta.json", meta)
    write_json(attempt, {"date_sgt": today, "status": "complete"})
    print(f"generated daily prompt for {meta['date_sgt']}")
    return 0


def main() -> int:
    try:
        with bounded_lock(ROOT / ".daily-prompt.lock", 120):
            return generate()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"daily prompt generation failed: {type(exc).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
