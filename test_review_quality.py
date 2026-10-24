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

    def test_truncated_response_cannot_become_score(self):
        reply = {'stop_reason': 'max_tokens', 'content': [{'type': 'text', 'text': json.dumps(self.good())}]}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(reply).encode()
        with patch('compare_claude.read_key', return_value='test-placeholder'), patch('review_quality.urlopen', return_value=response):
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                review.judge_images(b'png', b'png', 'test', 1)

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
