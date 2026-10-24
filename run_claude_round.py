#!/usr/bin/env python3
"""Run the four Claude comparison probes for today's shared prompt.

This is intentionally separate from the five-minute Codex census. Schedule it
every 30 minutes; it uses the ignored Anthropic key through compare_claude.py,
then rebuilds and publishes the same static Pages site.
"""
import fcntl
import importlib.util
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent
MODELS = ["claude-fable-5-1", "claude-opus-5-5", "claude-haiku-5-5", "claude-sonnet-5-5"]
SGT = ZoneInfo("Asia/Singapore")


def call(model: str, variant: str = "daily") -> tuple[str, int]:
    env = dict(os.environ, CLAUDE_MODEL=model, CLAUDE_MAX_TOKENS="16384", PROBE_VARIANT=variant)
    proc = subprocess.run(["python3", str(REPO / "compare_claude.py")], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=240)
    return f"{variant}/{model}", proc.returncode


def main() -> int:
    lock_fd = open(REPO / ".round.lock", "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another round is still running; skipping", flush=True)
        return 0
    results = [call(model, variant) for variant in ("pelican", "daily") for model in MODELS]
    for model, code in results:
        print(f"  {model}: {'ok' if code == 0 else 'error'}", flush=True)
    spec = importlib.util.spec_from_file_location("runner", REPO / "run_round.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    records = json.loads((REPO / "stats.json").read_text(encoding="utf-8"))
    (REPO / "index.html").write_text(runner.build_index(records), encoding="utf-8")
    stamp = datetime.now(SGT).strftime("%Y%m%d-%H%M%S")
    runner.git("add", "-A")
    commit = runner.git("commit", "-m", f"Claude daily control {stamp}")
    if commit.returncode != 0:
        print("commit failed:", (commit.stderr or commit.stdout).strip()[:300], flush=True)
    if not runner.sync_publication():
        return 1
    for ref in [("main",), ("main:gh-pages",)]:
        pushed = runner.git("push", "origin", *ref)
        print("pushed" if pushed.returncode == 0 else "push failed", ref[0], flush=True)
    return 0 if all(code == 0 for _, code in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
