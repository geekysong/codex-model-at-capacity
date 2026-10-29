# Selected model is at capacity — a 30-minute SVG census

**English** | [中文](README.zh-CN.md)

> **Census resumed 2026-10-29**, every 30 minutes through November 12, 2026 (SGT inclusive). Previous closeout and excluded records remain documented in `closeout.json`; new attempts retain errors as evidence.

Account region: earlier runs used a Philippines-region account. Resumed runs from October 29, 2026 use a Singapore-region account. Account and region changed together; consider this when comparing the two periods.

## Why this exists

In October 2026, this Codex account kept running into two problems:

1. **"Selected model is at capacity."** Models refuse work with that error even
   though the account's quota is barely touched — no warning, no recourse, and
   no official record that it ever happened.
2. **Suspected silent degradation.** The same models seem to answer
   noticeably worse than they used to — slower, dumber, or failing tasks they
   previously handled — with no announcement and no way to prove it.

So this project exists to **monitor one specific account, continuously and in
public**: is it being refused at capacity, and is it quietly getting dumber?
Every attempt is timestamped and published. A rising error rate exposes the
capacity problem; drifting durations, token patterns and sudden task failures
are the early-warning signal for degradation. The satirical SVG is just the
probe — the data is the point.

## How it works

Every 30 minutes, a job on a home Raspberry Pi runs two benchmarks —
**Pelican** (a fixed prompt) and **Daily Challenge** (one shared prompt
generated fresh each day) — and asks each surveyed OpenAI Codex model,
**once, with no retries**, to draw an SVG for each benchmark. Models run
sequentially so a round resembles ordinary account use.

For every attempt we record, verbatim:

- the model name
- wall-clock execution time (seconds)
- token usage from `codex exec --json` (`input`, `cached input`, `output`, `reasoning`, `total`)
- the exact error, if any (capacity refusals included)

Results are published on GitHub Pages: **https://geekysong.github.io/codex-model-at-capacity/**

- `index.html` — gallery of the latest round (regenerated each round)
- `history.html` — the full history table (regenerated each round)
- `stats.json` — the raw, append-only record of every attempt
- `runs/<round-id>-<variant>/<model>.svg` — the SVGs themselves
- `run_round.py` — the whole pipeline (Pi → codex exec → stats → page → commit → push)

Models surveyed: `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-luna`
(the `codex-auto-review` internal model is excluded). Reasoning effort is pinned
to `low` for all models so timings are comparable.

**Terra upgrade (2026-10-27):** `gpt-6.1-terra` replaced `gpt-5.6-terra` as the
surveyed Terra model, matching the latest Terra generation available in Codex
(verified against the Pi's `~/.codex/models_cache.json`, fetched 2026-10-27,
and with a live probe call). Earlier rounds in `stats.json` that used
`gpt-5.6-terra` remain untouched as historical data.

The small cross-provider panel on the site compares only these four pairs.
Claude outputs are produced separately (see *Local Claude comparison* below):

| Codex model | Claude control |
| --- | --- |
| `gpt-6-astra` | `claude-fable-5-1` (Fable 5.1) |
| `gpt-6.1-sol` | `claude-opus-5-5` (Opus 5.5) |
| `gpt-6.1-terra` | `claude-sonnet-5-5` (Sonnet 5.5) |
| `gpt-6-luna` | `claude-haiku-5-5` (Haiku 5.5) |

Commits are authored as geekysong <geekysong@gmail.com>.

## What "degradation" means here

This project deliberately does **not** trust Codex with important work. The
probe is a small, reversible drawing task; it measures availability and a few
observable cost signals without putting a real deliverable at risk. A passing
SVG is therefore not evidence that a model is intelligent, and a slow round is
not by itself evidence of a regression.

Pelican results now receive an independent visual review against a frozen Astra
reference. The image judge scores bird shape, softness, cycling coherence and
readability from 0 (acceptable) to 4 (major visual failure), with source images,
Chinese reasons and versioned hashes. The hourly interactive graph shows each
model's worst reviewed score in that hour. Missing reviews and generation failures
are unscored. This is a subjective image-quality series, not a measure of general
intelligence. See [QUALITY.md](QUALITY.md) for the schema, rubric and setup.

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

Each benchmark in a round also has `runs/<round>-<variant>/meta.json`,
containing the four records from that benchmark run. The SVG files are kept
as the original public artifacts.

## Reproduce or operate it

The Raspberry Pi uses one shared daily prompt. Codex runs every thirty minutes;
Claude runs once per day as the control group:

```cron
0 0 * * * /usr/bin/python3 /home/songyy/codex-model-at-capacity/generate_daily_prompt.py >> /home/songyy/codex-model-at-capacity/claude_round.log 2>&1
*/30 * * * * /usr/bin/python3 /home/songyy/codex-model-at-capacity/run_round.py >> /home/songyy/codex-model-at-capacity/round.log 2>&1
5 0 * * * /usr/bin/python3 /home/songyy/codex-model-at-capacity/run_claude_round.py >> /home/songyy/codex-model-at-capacity/claude_round.log 2>&1
```

The Codex runner acquires `.round.lock`, invokes the four surveyed models once
sequentially per benchmark with reasoning effort `low`, waits at most 600 seconds
per model, appends the results, rebuilds `index.html` and `history.html`, writes
the round metadata, then commits and pushes `main` and `main:gh-pages`. Push
failures are left for the next round to retry. To check the runner without
making model calls, use:

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
there or printed. The scheduled Claude control publishes these artifacts through the existing
GitHub Pages path; a standalone invocation only writes local artifacts.

`daily_prompt_meta.json` is the dated source of truth for the current question,
with `daily_prompt.txt` as its readable mirror. Both providers receive the same prompt; its SGT date and SHA-256 prefix are recorded in
every result so a Codex observation is compared only with Claude's same-day
control. The scheduled generator creates one atomic snapshot each day. The page keeps
older Pelican, substitution, and physics experiments as historical rounds.

### Active benchmarks and visible timestamps

Each scheduled Codex execution now runs Pelican and Daily Challenge sequentially, with four models per benchmark. Claude control runs also cover both benchmarks. Each request includes its own timestamp and requires a visible SVG footer with the date and time in Asia/Singapore (SGT, UTC+08:00). Existing historical images are unchanged. Physics and substitution remain archived rather than separate active benchmarks.

### Daily control reliability

The operational contract and regression checklist are in
[specs/claude-daily.md](specs/claude-daily.md). The existing Pi jobs run in
Asia/Singapore: prompt generation at 00:00 and Claude at 00:05. Claude waits up to
two hours for the shared Codex lock and attempts each challenge/model only once.
The dated JSON prompt snapshot is authoritative; the `.txt` file is a mirror.
The live comparison panel requires the same challenge date and hash.

```bash
python3 -m unittest -v test_claude_daily
python3 run_claude_round.py --dry-run
python3 run_claude_round.py --publish-only  # no model calls
```

A failed/uncertain request remains in ignored `.claude-state/` for operator
inspection; rerunning the daily job does not repeat it. Publication failures exit
nonzero and keep local artifacts. API outputs retain their actual provider and
model provenance.
