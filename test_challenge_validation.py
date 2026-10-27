import tempfile
import unittest
from pathlib import Path

from challenge_validation import validate_daily_artifact
from run_round import apply_artifact_validation

DAY = "2026-10-27"
SHA = "194611015ee3"
PROMPT = (
    "Draw a 600x400 SVG showing a 4x4 grid of squares where cells are numbered "
    "1-16; shade every cell whose number is a prime in blue and every cell whose "
    "number is a perfect square in orange."
)
EXPECTED = {
    1: "orange", 2: "blue", 3: "blue", 4: "orange",
    5: "blue", 6: "white", 7: "blue", 8: "white",
    9: "orange", 10: "white", 11: "blue", 12: "white",
    13: "blue", 14: "white", 15: "white", 16: "orange",
}


def svg_for(colors=None, date=DAY):
    colors = colors or EXPECTED
    chunks = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400">']
    for number in range(1, 17):
        x = 120 + ((number - 1) % 4) * 60
        y = 60 + ((number - 1) // 4) * 60
        chunks.append(f'<rect x="{x}" y="{y}" width="60" height="60" fill="{colors[number]}"/>')
        chunks.append(f'<text x="{x + 30}" y="{y + 30}">{number}</text>')
    chunks.extend([
        '<text x="120" y="330">Blue cells (primes): 6</text>',
        '<text x="120" y="355">Orange cells (perfect squares): 4</text>',
        f'<text x="120" y="385">{date} 13:00:01 SGT (UTC+08:00)</text>',
        '</svg>',
    ])
    return "".join(chunks)


class ChallengeValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "daily.svg"
        self.path.write_text(svg_for())
        self.record = {"variant": "daily", "prompt_date": DAY, "prompt_sha": SHA, "status": "ok"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_correct_prime_square_grid_is_accepted(self):
        self.assertIsNone(validate_daily_artifact(self.path, self.record, DAY, SHA, PROMPT))

    def test_missing_square_is_semantic_error(self):
        colors = dict(EXPECTED); colors[1] = "white"
        self.path.write_text(svg_for(colors))
        error = validate_daily_artifact(self.path, self.record, DAY, SHA, PROMPT)
        self.assertIn("1: expected orange, got white", error)
        rec = dict(self.record)
        apply_artifact_validation(rec, self.path, PROMPT, DAY, SHA)
        self.assertEqual(rec["status"], "semantic_error")

    def test_wrong_fill_is_semantic_error(self):
        colors = dict(EXPECTED); colors[11] = "orange"
        self.path.write_text(svg_for(colors))
        error = validate_daily_artifact(self.path, self.record, DAY, SHA, PROMPT)
        self.assertIn("11: expected blue, got orange", error)

    def test_date_and_hash_identity_mismatch_is_rejected(self):
        rec = dict(self.record, prompt_date="2026-10-26", prompt_sha="wrong")
        error = validate_daily_artifact(self.path, rec, DAY, SHA, PROMPT)
        self.assertIn("prompt_date", error)
        self.assertIn("prompt_sha", error)
        self.path.write_text(svg_for(date="2026-10-26"))
        error = validate_daily_artifact(self.path, self.record, DAY, SHA, PROMPT)
        self.assertIn("visible date label", error)

    def test_pelican_is_unaffected(self):
        self.path.write_text("<svg><text>not a daily grid</text></svg>")
        rec = {"variant": "pelican", "prompt_date": "wrong", "prompt_sha": "wrong", "status": "ok"}
        self.assertIsNone(validate_daily_artifact(self.path, rec, DAY, SHA, PROMPT))
        apply_artifact_validation(rec, self.path, PROMPT, DAY, SHA)
        self.assertEqual(rec["status"], "ok")


if __name__ == "__main__":
    unittest.main()
