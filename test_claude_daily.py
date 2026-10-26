import fcntl
import hashlib
import importlib.util
import json
import multiprocessing
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import claude_daily as helpers
import daily_prompt
import generate_daily_prompt as generator
import run_claude_round as claude
import run_round as runner


def release_later(path, ready):
    with open(path, 'a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        ready.set()
        time.sleep(.2)


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.day = datetime.now(daily_prompt.SGT).date().isoformat()
        self.prompt = 'Output SVG: knight moves from square 6.'
        self.sha = hashlib.sha256(self.prompt.encode()).hexdigest()[:12]
        self.snapshot = (self.prompt, self.day, self.sha)

    def tearDown(self):
        self.tmp.cleanup()

    def artifact(self, day=None, sha=None, provider='anthropic'):
        path = self.root / 'comparisons/20261026-120000/daily/test-model'
        path.mkdir(parents=True, exist_ok=True)
        (path / 'meta.json').write_text(json.dumps(dict(provider=provider, variant='daily',
            requested_model='test-model', model='actual-model', prompt_date=day or self.day,
            prompt_sha=sha or self.sha, status='ok', time_sgt='2026-10-26 12:00:00')))
        (path / 'claude.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        return path

    def test_snapshot_uses_generated_date_not_wall_clock_or_txt(self):
        (self.root / 'daily_prompt_meta.json').write_text(json.dumps({'date_sgt':'2020-01-01','prompt':self.prompt}))
        with patch.object(daily_prompt, 'ROOT', self.root):
            self.assertEqual(daily_prompt.load_daily_prompt(), (self.prompt, '2020-01-01', self.sha))

    def test_artifact_requires_challenge_provider_requested_model_and_valid_svg(self):
        p = self.artifact()
        def matches():
            return helpers.matching_artifacts(self.root, 'daily', 'test-model', self.day, self.sha)
        self.assertEqual(len(matches()), 1)
        self.artifact(sha='old'); self.assertEqual(matches(), [])
        self.artifact(day='2020-01-01'); self.assertEqual(matches(), [])
        self.artifact(provider='codex'); self.assertEqual(matches(), [])
        self.artifact(); (p / 'claude.svg').write_text('<svg>'); self.assertEqual(matches(), [])

    def test_prior_success_and_failed_attempts_never_call_again(self):
        with patch.object(claude, 'REPO', self.root), patch.object(claude, 'MODELS', ['test-model']), patch.object(claude, 'load_prompt', return_value=self.snapshot), patch.object(claude, 'call', return_value=1) as call:
            self.assertFalse(claude.generate(('daily',)))
            self.assertFalse(claude.generate(('daily',)))
            call.assert_called_once()
            self.artifact()
            self.assertTrue(claude.generate(('daily',)))
            call.assert_called_once()

    def test_stale_challenge_fails_before_api_call(self):
        with patch.object(claude, 'load_prompt', return_value=(self.prompt, '2020-01-01', self.sha)), patch.object(claude, 'call') as call:
            with self.assertRaisesRegex(RuntimeError, 'stale'):
                claude.generate(('daily',))
            call.assert_not_called()

    def test_lock_waits_then_enters_and_timeout_is_failure(self):
        lock = self.root / '.round.lock'
        ready = multiprocessing.Event()
        process = multiprocessing.Process(target=release_later, args=(lock, ready))
        process.start(); self.assertTrue(ready.wait(3))
        with self.assertRaises(TimeoutError):
            with helpers.bounded_lock(lock, 0):
                pass
        with helpers.bounded_lock(lock, 3):
            pass
        process.join(3); self.assertEqual(process.exitcode, 0)

    def test_page_rejects_old_claude_for_new_prompt(self):
        self.artifact(day='2020-01-01')
        with patch.object(runner, 'REPO', self.root), patch.object(runner, 'ACTIVE_VARIANTS', ('daily',)), patch.object(runner, 'load_prompt', return_value=self.snapshot), patch.object(runner, 'PAIRINGS', [('codex-model','test-model','Test')]):
            page = runner.build_index([])
            self.assertNotIn('comparisons/20261026', page)
            self.assertIn('awaiting daily run', page)
            self.artifact()
            self.assertIn('comparisons/20261026', runner.build_index([]))

    def test_prompt_generator_is_daily_idempotent(self):
        with patch.object(generator, 'load_daily_prompt', return_value=self.snapshot), patch.object(generator, 'urlopen') as api:
            self.assertEqual(generator.generate(), 0)
            api.assert_not_called()

    def test_dry_run_never_generates_or_publishes(self):
        with patch.object(claude, 'load_prompt', return_value=self.snapshot), patch.object(claude, 'generate') as gen, patch.object(claude, 'publish') as pub:
            self.assertEqual(claude.main(['--dry-run']), 0)
            gen.assert_not_called(); pub.assert_not_called()

    def test_publish_only_reports_failure_without_generation(self):
        with patch.object(claude, 'REPO', self.root), patch.object(claude, 'publish', return_value=False), patch.object(claude, 'generate') as gen:
            self.assertEqual(claude.main(['--publish-only']), 1)
            gen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
