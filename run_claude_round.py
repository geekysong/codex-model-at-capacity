#!/usr/bin/env python3
"""Once daily at 00:05 Asia/Singapore; wait for Codex, never silently skip.

One API attempt per challenge/variant/requested model. Failed or interrupted
attempts require operator review; publication retries never regenerate images.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from daily_prompt import SGT
from probe_prompts import ACTIVE_VARIANTS, load_prompt
from claude_daily import bounded_lock, matching_artifacts, write_json

REPO = Path(__file__).resolve().parent
MODELS = ['claude-fable-5-1', 'claude-opus-5-5', 'claude-haiku-5-5', 'claude-sonnet-5-5']


def call(model, variant, snapshot):
    env = dict(os.environ, CLAUDE_MODEL=model, CLAUDE_MAX_TOKENS='16384',
               PROBE_VARIANT=variant, CLAUDE_PROMPT_SNAPSHOT=json.dumps(snapshot))
    try:
        proc = subprocess.run([sys.executable, str(REPO / 'compare_claude.py')],
                              cwd=REPO, env=env, capture_output=True, text=True, timeout=240)
        # compare_claude only emits safe HTTP codes/configuration categories.
        detail = (proc.stdout if proc.returncode == 0 else proc.stderr).strip()[-500:]
        print(f'{variant}/{model}: exit={proc.returncode} {detail}', flush=True)
        return proc.returncode
    except subprocess.TimeoutExpired:
        print(f'{variant}/{model}: timeout after 240s; outcome uncertain, no automatic retry', flush=True)
        return 1


def generate(variants):
    today = datetime.now(SGT).date().isoformat()
    snapshots = {v: load_prompt(v) for v in variants}
    if any(s[1] != today for s in snapshots.values()):
        raise RuntimeError('daily challenge is stale; inspect the 00:00 prompt-generation log; no API calls made')
    ok = True
    for variant, snapshot in snapshots.items():
        _, day, sha = snapshot
        for model in MODELS:
            identity = f'{day}-{sha}/{variant}/{model}'
            if matching_artifacts(REPO, variant, model, day, sha):
                print(f'{identity}: already complete; no API call', flush=True)
                continue
            state = REPO / '.claude-state' / identity / 'attempt.json'
            if state.exists():
                print(f'{identity}: prior attempt without valid artifact; inspect {state.relative_to(REPO)}; no paid retry', flush=True)
                ok = False
                continue
            write_json(state, {'identity': identity, 'status': 'started', 'started_at': datetime.now(SGT).isoformat()})
            code = call(model, variant, snapshot)
            complete = code == 0 and bool(matching_artifacts(REPO, variant, model, day, sha))
            write_json(state, {'identity': identity, 'status': 'complete' if complete else 'failed_or_uncertain', 'exit_code': code})
            ok = complete and ok
    return ok


def publish():
    spec = importlib.util.spec_from_file_location('runner', REPO / 'run_round.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    records = json.loads((REPO / 'stats.json').read_text())
    (REPO / 'index.html').write_text(runner.build_index(records))
    (REPO / 'history.html').write_text(runner.build_history(records))
    if runner.git('add', 'comparisons', 'index.html', 'history.html').returncode:
        raise RuntimeError('publication staging failed; artifacts retained')
    if runner.git('diff', '--cached', '--quiet').returncode:
        if runner.git('commit', '-m', 'Publish Claude API daily controls (source metadata preserved)').returncode:
            raise RuntimeError('publication commit failed; artifacts retained')
    if not runner.sync_publication():
        return False
    ok = True
    for ref in ('main', 'main:gh-pages'):
        result = runner.git('push', 'origin', ref)
        print(f'publication {ref}: exit={result.returncode}', flush=True)
        if result.returncode:
            print('push failed; local artifacts/commit retained. Check git authentication or remote divergence; rerun --publish-only.', flush=True)
            ok = False
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--publish-only', action='store_true')
    parser.add_argument('--variant', choices=ACTIVE_VARIANTS)
    parser.add_argument('--lock-wait-seconds', type=int, default=7200)
    args = parser.parse_args(argv)
    if not 0 <= args.lock_wait_seconds <= 7200:
        parser.error('lock wait must be between 0 and 7200 seconds')
    variants = (args.variant,) if args.variant else ACTIVE_VARIANTS
    try:
        if args.dry_run:
            for variant in variants:
                _, day, sha = load_prompt(variant)
                current = day == datetime.now(SGT).date().isoformat()
                for model in MODELS:
                    done = bool(matching_artifacts(REPO, variant, model, day, sha))
                    print(f'{day}/{sha}/{variant}/{model}: current={current} complete={done}')
            return 0
        with bounded_lock(REPO / '.round.lock', args.lock_wait_seconds):
            generated = True if args.publish_only else generate(variants)
            published = publish()
            return 0 if generated and published else 1
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f'Claude daily failed: {exc}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
