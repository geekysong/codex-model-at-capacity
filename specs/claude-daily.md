# Claude daily control contract

## Schedule and ownership

The existing Pi crontab is the only scheduler. Host: `songyy-pi`; checkout:
`/home/songyy/codex-model-at-capacity`; timezone: `Asia/Singapore`.

- 00:00: `generate_daily_prompt.py`, once per SGT date.
- 00:05: `run_claude_round.py`, once daily, existing Pelican + Daily variants and four configured Claude models.
- Codex remains every 30 minutes. Do not install a second Claude scheduler.

The daily Claude job waits for the existing shared `.round.lock` for at most
7200 seconds. A lock timeout is a nonzero operational failure, never a successful
skip. This covers the existing Codex round's eight 600-second model deadlines,
600-second quality-review deadline and bounded publication work. Claude requests
have a 240-second process deadline, 180-second HTTP timeout and 16384 output-token
cap. There are no automatic paid retries.

## Challenge and identity

`daily_prompt_meta.json` is the atomically replaced authoritative snapshot
(`date_sgt`, exact prompt, generator-reported model); `daily_prompt.txt` is its
readable mirror. Loading an old snapshot preserves its original date. A new day
must never be inferred from the wall clock and applied to old prompt text.
Claude refuses a stale snapshot before API calls. Each invocation freezes the
prompt/date/SHA before any generation and passes it to each child request.

A control's identity is `(prompt_date, prompt_sha, variant, requested_model)`.
A reusable result must have Anthropic provenance, matching identity, success
status and a parseable SVG. Record both requested model and returned model,
actual prompt, timestamp, usage and cost estimate; never label Codex work Claude.
`comparisons/` keeps historical artifacts. The main comparison panel only shows
artifacts matching the displayed challenge date/hash; absence is explicit.

Ignored `.claude-state/` records an attempt *before* API submission. A failed or
interrupted attempt without a valid artifact blocks further paid attempts for
that identity, including after process restart. Inspect provider outcome and
logs before any operator-authorized reset; do not blindly delete this state.
The prompt generator also locks, checks the existing date and records attempts.

## Publication and recovery

Under the shared lock, rebuild both pages, commit comparison artifacts and pages,
sync existing remote history, and push `main` and `main:gh-pages` independently.
Return failure on either push failure; preserve generated artifacts and commits.
`python3 run_claude_round.py --publish-only` retries publication without model calls.
`--dry-run` only reports current identities/artifact presence; it does not call a
model, mutate state or publish. `--variant daily` limits a controlled recovery run
to today's daily challenge. Never backfill historical billable requests by default.

## Regression checks

Run `python3 -m unittest -v test_claude_daily` and the existing quality tests.
Check: generated date survives wall-clock rollover; wrong date/hash/provider or
malformed SVG cannot dedupe; success and failed/uncertain attempts cannot trigger
another paid call; stale prompts fail before calling API; lock waits and times out;
old Claude images are not shown under a new challenge; generator is idempotent;
dry-run and publication-only cannot invoke generation; publication failure exits
nonzero. Use fixtures first, then at most one authorized current-challenge run.

## Incident evidence, 2026-10-26

The 00:05 Claude job logged `another round is still running; skipping` while
Codex held the shared nonblocking lock. Latest successful Claude daily artifacts
were 2026-10-25 (`12ae10ce6a68`), while the current challenge was 2026-10-26.
The old page selected the newest file path without matching prompt date/hash.
The loader also used today's date even when reading an old prompt.
October 25 Claude push failures had already been recovered by subsequent Codex
publication: both remote branches reached the October 26 16:00 round before the
repair. The original Claude push log omitted diagnostics, so its historical
failure reason cannot be established. API failure is not the established cause.

## Repair verification, 2026-10-26 16:42 SGT

- Fix commit `8c2fa56`, integrated to Pi main by merge `07cc127`.
- 9 daily-control regression checks plus 7 existing quality checks passed on Pi.
- Controlled recovery: only today's Daily variant, one API request per model;
  4/4 successful, no Pelican/history backfill. Snapshot date `2026-10-26`, SHA
  `83e3cc3e6646`, exact prompt verified in all four metadata records.
- Artifacts: `comparisons/20261026-163840/daily/claude-fable-5-1/claude.svg`,
  `comparisons/20261026-163901/daily/claude-opus-5-5/claude.svg`,
  `comparisons/20261026-163918/daily/claude-haiku-5-5/claude.svg`,
  `comparisons/20261026-163929/daily/claude-sonnet-5-5/claude.svg`.
- Publication commit `11f2a73`, followed by existing sync rebuild `ae795ac`;
  pushes to both main and gh-pages returned success. After normal Pages build
  propagation, the public page contained all four paths and every public SVG
  returned HTTP 200 with a SHA-256 matching its Pi artifact. Browser inspection
  showed the new Daily Challenge images and their source timestamps.
- SVG text independently matched the knight challenge (4 reachable squares:
  4, 12, 13, 15); this is a pipeline acceptance check, not a general model rating.
- Total estimated API cost from existing versioned rates: USD 0.171884, not a
  provider invoice. Repeat dry-run reports all four complete; repeated generator
  invocation reports today's prompt already exists and makes no API call.
- Existing crontab unchanged. Next prompt: 2026-10-27 00:00 SGT; next Claude job:
  2026-10-27 00:05 SGT (2026-10-26 16:05 UTC). This future scheduled execution has
  not yet been observed. No new daemon, account, credential or scheduler installed.
