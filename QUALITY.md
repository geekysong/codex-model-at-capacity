# Pelican visual reviews, v1

The fixed reference is an Astra output chosen and visually inspected on 2026-10-25:
`runs/20261025-073001-pelican/gpt-6-astra.svg`. Its frozen copy and SHA-256 are in
`quality/baseline.svg` and `quality/baseline.json`. Future Astra outputs are scored
against this same reference, rather than moving the standard each hour.

A separate Codex `gpt-6-astra` visual judge sees only the reference and the candidate as
three-frame PNG contact sheets (0.4, 1.2, 2.2 seconds). It does not receive model
identifiers. The reviewer rates bird shape, softness, riding, and readability,
allowing good differences in drawing style. These are subjective output scores,
not proof of capacity refusal, silent model substitution or general degradation.
Daily Challenge is not rated by this pelican-specific rubric.

Each dimension and final severity use integers 0–4: 0 acceptable relative to the
reference, 1 minor defect, 2 clear defect, 3 major defect, 4 missing/unrecognizable.
Final severity is the maximum dimension. Same-hour attempts remain individual
records; each model's plotted hourly point is their maximum severity. Clicking a
point shows every attempt, its images and reasons. Hours use Asia/Singapore.
Generation failure, SVG render failure (`render_error`), or incomplete visual review has `severity: null`; none is
silently converted to zero. Lines do not cross hours with no reviewed data.

`quality_reviews.json` has the machine-readable contract in
`quality_reviews.schema.json`. Reviews record the source round, model, timestamp,
SVG hash, frozen baseline hash, rubric version, judge, confidence, four dimensions,
Chinese reasons and review time. Completed results are cached by image hash and fixed baseline; changing the
judge does not trigger historical re-evaluation. Each record retains the original
judge identity; errors remain pending and can be retried. Each complete review is saved
atomically, so interrupted runs retain completed assessments.

Historical prompts evolved: older images were not asked to animate or show a date.
The v1 rubric therefore rates bird form and composition, not timestamp or animation
compliance. Compare those historical scores with that limit in mind.

## Run

```
python3 -m venv .venv-quality
.venv-quality/bin/pip install -r requirements-quality.txt
.venv-quality/bin/playwright install chromium
.venv-quality/bin/python -B review_quality.py
python3 -B -m unittest test_review_quality
```

Uses the existing authenticated Codex CLI, with `gpt-6-astra` as the default judge. No Anthropic key is used for visual review. Existing Claude reviews remain attributed to Claude.
The scheduled Codex runner reviews pending results after saving raw generation
records, with an overall 600-second review budget and a limit of eight pending
items per execution. Timeouts or review failures still allow raw results to publish.
Codex generation and visual review run sequentially. Completed historical
reviews are preserved and not submitted again merely because the judge changed. The reviewer has a separate `.quality.lock`.
