# Selected model is at capacity — a 5-minute SVG census

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
