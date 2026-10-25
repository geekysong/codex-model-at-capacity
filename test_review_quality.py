"""Offline checks for rejecting fabricated/incomplete scores and active SVG content."""
import unittest
from unittest.mock import patch, MagicMock
import json
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import review_quality as review


class ReviewValidationTests(unittest.TestCase):
    def good(self):
        return {'dimensions': {k: 0 for k in review.DIMENSIONS}, 'severity': 0,
                'confidence': 0.95, 'reasons': ['鸟形自然，骑行动作清楚。']}

    def test_rejects_wrong_severity_and_boolean_scores(self):
        value = self.good()
        value['severity'] = 3
        with self.assertRaises(ValueError):
            review.validate_review(value)
        value = self.good()
        value['dimensions']['bird_shape'] = False
        with self.assertRaises(ValueError):
            review.validate_review(value)

    def test_accepts_valid_score_without_inventing_dimensions(self):
        self.assertEqual(review.validate_review(self.good())['severity'], 0)
        value = self.good()
        del value['dimensions']['riding']
        with self.assertRaises(ValueError):
            review.validate_review(value)

    def test_sanitizes_active_svg_and_external_resources(self):
        svg = b'''<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">
          <script>alert(1)</script><foreignObject/><image href="https://evil.invalid/x"/>
          <use href="#shape"/><circle id="shape"/></svg>'''
        result = review.sanitize_svg(svg)
        self.assertNotIn(b'onload', result)
        self.assertNotIn(b'<script', result)
        self.assertNotIn(b'foreignObject', result)
        self.assertNotIn(b'evil.invalid', result)
        self.assertIn(b'#shape', result)
        with self.assertRaises(ValueError):
            review.sanitize_svg(b'<!DOCTYPE svg [<!ENTITY a "x">]><svg/>')

    def test_incomplete_codex_response_cannot_become_score(self):
        import subprocess
        failed = subprocess.CompletedProcess([], 1, '', 'test failure')
        with patch('review_quality.subprocess.run', return_value=failed):
            with self.assertRaisesRegex(RuntimeError, 'complete review'):
                review.judge_images(b'png', b'png', 'gpt-6-astra', 1)

    def test_codex_uses_images_and_preserves_strict_validation(self):
        import subprocess
        def invoke(args, **kwargs):
            self.assertEqual(args[args.index('-m') + 1], 'gpt-6-astra')
            self.assertEqual(args.count('-i'), 2)
            Path(args[args.index('-o') + 1]).write_text(json.dumps(self.good()))
            return subprocess.CompletedProcess(args, 0, '', '')
        with patch('review_quality.subprocess.run', side_effect=invoke):
            value = review.judge_images(b'png', b'png', 'gpt-6-astra', 600)
            self.assertEqual(value['severity'], 0)
            self.assertEqual(value['judge_provider'], 'codex')

    def test_completed_claude_review_is_not_repeated_after_judge_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'candidate.svg').write_bytes(b'<svg/>')
            baseline = {'svg_sha256': 'reference'}
            previous = {'round': 'r', 'model': 'generated-model', 'status': 'reviewed',
                        'svg_sha256': review.sha(b'<svg/>'), 'baseline_sha256': 'reference',
                        'judge': 'claude-fable-5-1'}
            (root / 'quality_reviews.json').write_text(json.dumps({
                'rubric_version': review.RUBRIC, 'baseline': baseline, 'reviews': [previous]}))
            row = {'round': 'r', 'model': 'generated-model', 'status': 'ok', 'svg': 'candidate.svg'}
            with patch.object(review, 'ROOT', root), patch.object(review, 'baseline_info', return_value=baseline), patch.object(review, 'records', return_value=[row]), patch.object(review, 'Renderer') as renderer:
                review.run(SimpleNamespace(limit=None, model='gpt-6-astra', timeout=600, workers=1))
                renderer.assert_not_called()

    def test_parallel_judges_save_every_result_on_main_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'baseline.svg').write_bytes(b'<svg/>')
            (root / 'candidate.svg').write_bytes(b'<svg/>')
            baseline = {'svg': 'baseline.svg', 'svg_sha256': 'fixed'}
            rows = [{'round': str(i), 'model': 'gpt-test', 'time_sgt': str(i),
                     'svg': 'candidate.svg', 'status': 'ok'} for i in range(4)]
            renderer = MagicMock()
            renderer.__enter__.return_value = renderer
            renderer.render.return_value = b'png'
            guard = threading.Lock()
            counts = {'active': 0, 'peak': 0}
            def judge(*args):
                with guard:
                    counts['active'] += 1
                    counts['peak'] = max(counts['peak'], counts['active'])
                time.sleep(0.02)
                with guard:
                    counts['active'] -= 1
                return self.good()
            saved = []
            main_thread = threading.get_ident()
            def persist(path, value):
                self.assertEqual(threading.get_ident(), main_thread)
                saved.append(json.loads(json.dumps(value)))
            with patch.object(review, 'ROOT', root), patch.object(review, 'baseline_info', return_value=baseline), patch.object(review, 'records', return_value=rows), patch.object(review, 'Renderer', return_value=renderer), patch.object(review, 'judge_images', side_effect=judge), patch.object(review, 'atomic_json', side_effect=persist):
                review.run(SimpleNamespace(limit=None, model='test', timeout=1, workers=2))
            self.assertEqual(counts['peak'], 2)
            self.assertEqual([len(item['reviews']) for item in saved], [1, 2, 3, 4])
            self.assertTrue(all(r['status'] == 'reviewed' for r in saved[-1]['reviews']))


if __name__ == '__main__':
    unittest.main()
