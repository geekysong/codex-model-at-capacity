#!/usr/bin/env python3
"""Run scheduled census jobs through November 12 inclusive, Singapore time."""
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
END = datetime(2026, 11, 13, tzinfo=ZoneInfo("Asia/Singapore"))
JOBS = {"round": "run_round.py", "prompt": "generate_daily_prompt.py", "claude": "run_claude_round.py"}

def main():
    if datetime.now(END.tzinfo) >= END:
        print("Census schedule ended after November 12 SGT.", flush=True)
        return 0
    return subprocess.call([sys.executable, str(ROOT / JOBS[sys.argv[1]])], cwd=ROOT)

if __name__ == "__main__":
    raise SystemExit(main())
