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

中文：2026 年 10 月，这个账号用 Codex 时频繁遇到两个问题：一是额度明明没用多少，
却反复报 “Selected model is at capacity”；二是怀疑模型「降智」——回答质量悄悄变差。
两个问题官方都不留任何可查的记录。这个项目就给这个账号做持续、公开的体检：
每 5 分钟用同一个小任务轮询每个模型，如实记录耗时、token 和错误。错误率上升
说明有容量问题；耗时/token 漂移、任务突然失败，就是降智的早期信号。讽刺 SVG
只是探针，数据才是本体。

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
