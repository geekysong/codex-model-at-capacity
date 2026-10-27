# Claude standalone fallback correction — 2026-10-27

- Target: `/home/songyy/codex-model-at-capacity` on `songyy-pi`.
- Authorized change: replace only the standalone `compare_claude.py` fallback
  `claude-sonnet-4-20250514` with the supplier-confirmed `claude-sonnet-5-5`.
- Scheduled runner remains explicit: Fable 5.1, Opus 5.5, Haiku 5.5, Sonnet 5.5.
- Supplier read-only `/v1/models` check returned `claude-sonnet-5-5`; no paid
  generation or retry was performed.
- Claude cron remains 00:00/00:05 SGT; Codex cron remains `*/30`.
- Validation and commit details are recorded with the resulting commit.
