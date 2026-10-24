# Selected model is at capacity — a 5-minute SVG census

## Why this exists — 背景

In October 2026, this Codex account kept running into two problems:

1. **"Selected model is at capacity."** Models refuse work with that error even
   though the account's quota is barely touched — no warning, no recourse, and
   no official record that it ever happened.
2. **Suspected silent degradation （降智）.** The same models seem to answer
   noticeably worse than they used to — slower, dumber, or failing tasks they
   previously handled — with no announcement and no way to prove it.

So this project exists to **monitor one specific account, continuously and in
public**: is it being refused at capacity, and is it quietly getting dumber?
Every attempt is timestamped and published. A rising error rate exposes the
capacity problem; drifting durations, token patterns and sudden task failures
are the early-warning signal for degradation. The satirical SVG is just the
probe — the data is the point.

## How it works

Every 5 minutes, a job on a home Raspberry Pi asks each OpenAI Codex model —
**once, with no retries** — to draw a satirical SVG about Codex's own
"Selected model is at capacity. Please try a different model." error.

For every attempt we record, verbatim:

- the model name
- wall-clock execution time (seconds)
- token usage from `codex exec --json` (`input`, `cached input`, `output`, `reasoning`, `total`)
- the exact error, if any (capacity refusals included)

Results are published on GitHub Pages: **https://geekysong.github.io/codex-model-at-capacity/**

- `index.html` — gallery of the latest round + full history table (regenerated each round)
- `stats.json` — the raw, append-only record of every attempt
- `runs/<round-id>/<model>.svg` — the SVGs themselves
- `run_round.py` — the whole pipeline (Pi → codex exec → stats → page → commit → push)

Models surveyed: `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-luna`,
`gpt-reserve`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`
(the `codex-auto-review` internal model is excluded). Reasoning effort is pinned
to `low` for all models so timings are comparable.

Commits are authored as geekysong <geekysong@gmail.com>.

## What “degradation” means here

This project deliberately does **not** trust Codex with important work. The
probe is a small, reversible drawing task; it measures availability and a few
observable cost signals without putting a real deliverable at risk. A passing
SVG is therefore not evidence that a model is intelligent, and a slow round is
not by itself evidence of a regression.

The stronger signal we want to add is an independent, subjective review. For a
fixed set of benchmark prompts, Claude Code can judge each Codex answer using
the same rubric and a 0–4 score for: instruction following, factual accuracy,
reasoning, completeness, and usefulness. The judge must receive the prompt and
answer, not the model name or timing, and the prompt set and rubric must remain
versioned. We will store one record per judged answer with the prompt-set
version, Codex model, judge model, rubric scores, total score, and a short
reason. This creates a separate “quality” series alongside the operational
series in `stats.json`; it must never be inferred from SVG success alone.

Until those benchmark reviews are collected, the site should describe the
subjective quality signal as planned rather than display an invented score.

## Data format

`stats.json` is an append-only JSON array. Each attempt has these fields:

| Field | Meaning |
| --- | --- |
| `round` | SGT round identifier, `YYYYMMDD-HHMMSS` |
| `time_sgt` | Timestamp when that model attempt started |
| `model` | Codex model passed to `codex exec` |
| `status` | `ok` when a complete SVG was extracted, otherwise `error` |
| `duration_s` | Wall-clock seconds, including failed attempts and timeouts |
| `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_tokens`, `total_tokens` | Usage reported by the JSON event stream; unavailable values are `null` |
| `error` | Truncated error text, when present |
| `svg` | Relative path to the generated SVG, or `null` |

Each round also has `runs/<round>/meta.json`, containing the four records from
that invocation. The SVG files are kept as the original public artifacts.

## Reproduce or operate it

The Raspberry Pi uses one shared daily prompt. Codex runs every thirty minutes;
Claude runs once per day as the control group:

```cron
*/30 * * * * /usr/bin/python3 /home/songyy/codex-model-at-capacity/run_round.py >> /home/songyy/codex-model-at-capacity/round.log 2>&1
5 0 * * * /usr/bin/python3 /home/songyy/codex-model-at-capacity/run_claude_round.py >> /home/songyy/codex-model-at-capacity/claude_round.log 2>&1
```

The Codex runner acquires `.round.lock`, invokes the four paired models once in
parallel with reasoning effort `low`, waits at most 600 seconds per model, appends the results, rebuilds
`index.html`, writes the round metadata, then commits and pushes `main` and
`main:gh-pages`. Push failures are left for the next round to retry. To run a
local page build without making model calls, use:

```bash
python3 -m py_compile run_round.py
```

The generated page is intentionally self-contained: it has no CDN or build
step, so GitHub Pages can serve it directly. `index.html` is generated output;
make UI changes in `build_index()` inside `run_round.py`, otherwise the next
cron run will overwrite them.

## Local Claude comparison

`compare_claude.py` sends the exact same SVG probe directly to Anthropic's
official Messages API. Put the API key by itself in the ignored file
`.secrets/anthropic_api_key` (mode `600`), then run:

```bash
python3 compare_claude.py
```

The model can be selected without changing the script, for example with
`CLAUDE_MODEL=claude-sonnet-5-5`. The output and non-secret request
metadata are written to `comparisons/<timestamp>/`; the key is never written
there or printed. This comparison is intentionally separate from the cron
health series and is not automatically published to GitHub Pages.

`daily_prompt.txt` is the single source of truth for the current question. Both
providers receive it unchanged; its SGT date and SHA-256 prefix are recorded in
every result so a Codex observation is compared only with Claude's same-day
control. Change that file once per day to start a new question. The page keeps
older Pelican, substitution, and physics experiments as historical rounds.
