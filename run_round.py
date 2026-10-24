#!/usr/bin/env python3
"""One round: ask every Codex model (once, no retries) to draw a satirical SVG
about Codex being 'at capacity'. Record per-model duration, token usage and
errors, regenerate the GitHub Pages site (index.html + stats.json), commit & push.

Runs on the Raspberry Pi (songyy-pi), where codex is logged in.
Single instance enforced with flock. Push failures are tolerated: local commits
accumulate and are pushed by the next successful round.
"""
import fcntl
import html
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent
SGT = ZoneInfo("Asia/Singapore")
MODELS = [
    "gpt-6-astra",
    "gpt-6.1-sol",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-reserve",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
]
PER_MODEL_TIMEOUT = 180  # seconds; hard cap, no retry after this
PROMPT = (
    "Draw a satirical cartoon as ONE single self-contained SVG document "
    "(viewBox=\"0 0 800 600\"). Theme: OpenAI Codex keeps refusing work with "
    "\"Selected model is at capacity. Please try a different model.\" Make fun of "
    "that: a robot nightclub bouncer turning away a long queue of tired developers, "
    "a velvet rope and a glowing FULL sign, hamster-wheel servers melting, an "
    "exclusive club where only one model got in — pick ONE scene and make it funny. "
    "Include inside the SVG a bold title and a caption containing the words "
    "\"at capacity\". Output ONLY the SVG code: no markdown fences, no explanation, "
    "no text outside the <svg>...</svg> document."
)


def run_model(model: str, round_id: str) -> dict:
    env = dict(os.environ)
    env["PATH"] = str(Path.home() / ".local" / "bin") + ":" + env.get("PATH", "")
    started = datetime.now(SGT)
    t0 = time.monotonic()
    rec = {
        "round": round_id,
        "time_sgt": started.strftime("%Y-%m-%d %H:%M:%S"),
        "model": model,
        "status": "error",
        "duration_s": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
        "error": None,
        "svg": None,
    }
    try:
        proc = subprocess.run(
            [
                "codex", "exec", "--json",
                "-m", model,
                "-c", 'model_reasoning_effort="low"',
                "--skip-git-repo-check",
                PROMPT,
            ],
            capture_output=True, text=True, timeout=PER_MODEL_TIMEOUT,
            cwd="/tmp", env=env, stdin=subprocess.DEVNULL,
        )
        dur = time.monotonic() - t0
        rec["duration_s"] = round(dur, 2)
        message_text = ""
        err_msgs = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = ev.get("type")
            if et == "item.completed" and ev.get("item", {}).get("type") == "agent_message":
                message_text = ev["item"].get("text", "") or message_text
            elif et == "turn.completed":
                u = ev.get("usage") or {}
                rec["input_tokens"] = u.get("input_tokens")
                rec["cached_input_tokens"] = u.get("cached_input_tokens")
                rec["output_tokens"] = u.get("output_tokens")
                rec["reasoning_tokens"] = u.get("reasoning_output_tokens")
                if u.get("input_tokens") is not None and u.get("output_tokens") is not None:
                    rec["total_tokens"] = u["input_tokens"] + u["output_tokens"]
            elif et == "error":
                err_msgs.append(str(ev.get("message", "")))
            elif et == "turn.failed":
                err_msgs.append(str((ev.get("error") or {}).get("message", "turn.failed")))
        if proc.returncode != 0 or err_msgs:
            msg = " | ".join(m for m in err_msgs if m)
            if not msg:
                tail = (proc.stderr or "").strip().splitlines()
                msg = tail[-1] if tail else f"codex exited {proc.returncode} with no message"
            rec["error"] = msg[:400]
            return rec
        m = re.search(r"<svg[\s\S]*?</svg>", message_text)
        if not m:
            rec["error"] = "model replied without an SVG: " + (message_text[:200] or "(empty reply)")
            return rec
        svg_rel = f"runs/{round_id}/{model}.svg"
        svg_path = REPO / svg_rel
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_text = m.group(0)
        if "xmlns" not in svg_text.split(">", 1)[0]:
            svg_text = svg_text.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
        svg_path.write_text(svg_text, encoding="utf-8")
        rec["svg"] = svg_rel
        rec["status"] = "ok"
        return rec
    except subprocess.TimeoutExpired:
        rec["duration_s"] = round(time.monotonic() - t0, 2)
        rec["error"] = f"timeout after {PER_MODEL_TIMEOUT}s (no retry, per spec)"
        return rec
    except Exception as e:  # noqa: BLE001 - record anything, keep the round going
        rec["duration_s"] = round(time.monotonic() - t0, 2)
        rec["error"] = f"runner exception: {e}"[:400]
        return rec


def build_index(records: list[dict]) -> str:
    rounds = sorted({r["round"] for r in records}, reverse=True)
    latest = rounds[0] if rounds else None
    latest_recs = [r for r in records if r["round"] == latest]
    ok_n = sum(1 for r in latest_recs if r["status"] == "ok")
    cards = []
    for r in latest_recs:
        if r["svg"]:
            art = f'<img src="{html.escape(r["svg"])}" alt="SVG by {html.escape(r["model"])}" loading="lazy">'
        else:
            art = f'<div class="noart">✕ no SVG<br><small>{html.escape((r["error"] or "")[:140])}</small></div>'
        cards.append(
            f'<figure class="card">{art}<figcaption><b>{html.escape(r["model"])}</b> · '
            f'{r["duration_s"]}s · {r["total_tokens"]} tok · {r["status"]}</figcaption></figure>'
        )
    rows = []
    for r in sorted(records, key=lambda x: (x["round"], x["time_sgt"]), reverse=True):
        badge = '<span class="ok">ok</span>' if r["status"] == "ok" else '<span class="err">error</span>'
        svg_link = f'<a href="{html.escape(r["svg"])}">svg</a>' if r["svg"] else "—"
        err = html.escape((r["error"] or "")[:120])
        rows.append(
            f'<tr><td>{html.escape(r["time_sgt"])}</td><td>{html.escape(r["model"])}</td>'
            f'<td>{badge}</td><td class="n">{r["duration_s"]}</td>'
            f'<td class="n">{r["input_tokens"]}</td><td class="n">{r["cached_input_tokens"]}</td>'
            f'<td class="n">{r["output_tokens"]}</td><td class="n">{r["reasoning_tokens"]}</td>'
            f'<td class="n">{r["total_tokens"]}</td><td class="errtxt">{err}</td><td>{svg_link}</td></tr>'
        )
    updated = datetime.now(SGT).strftime("%Y-%m-%d %H:%M:%S SGT")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Selected model is at capacity — a 5-minute SVG census</title>
<style>
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,'Segoe UI',Roboto,'Helvetica Neue',sans-serif;margin:0;padding:24px}}
h1{{font-size:26px;margin:0 0 4px}} .sub{{color:#8b949e;margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px;margin-bottom:28px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;margin:0;overflow:hidden}}
.card img{{width:100%;display:block;background:#fff}}
.card figcaption{{padding:8px 12px;color:#c9d1d9;font-size:13px}}
.noart{{padding:38px 16px;text-align:center;color:#f85149;background:#1c1215}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border-bottom:1px solid #21262d;padding:6px 8px;text-align:left;vertical-align:top}}
th{{color:#8b949e}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.ok{{color:#3fb950}} .err{{color:#f85149}} .errtxt{{color:#f85149;max-width:340px;word-break:break-word}}
a{{color:#58a6ff}}
</style></head><body>
<h1>🚪 Selected model is at capacity.</h1>
<div class="sub">Every 5 minutes, each Codex model on a home Raspberry Pi is asked — once, no retries —
to draw a satirical SVG about exactly that error. Timing, token usage and failures are recorded verbatim.
Latest round: <b>{latest}</b> · {ok_n}/{len(latest_recs)} models produced an SVG · page rebuilt {updated} ·
<a href="stats.json">raw stats.json</a></div>
<div class="sub" style="border:1px solid #30363d;border-radius:10px;padding:12px 16px;background:#161b22">
<b>Why this exists:</b> in October 2026 this Codex account kept hitting two problems — models refusing work
with “Selected model is at capacity” despite barely-used quota, and suspected silent quality degradation
（降智）: the same models answering noticeably worse, with no announcement and no official record of either.
This page is a continuous, public health-check for one specific account: a rising error rate exposes the
capacity problem, while drifting durations, token patterns and sudden task failures are the early-warning
signal for degradation. The satirical SVG is just the probe — the data is the point.<br>
<span style="color:#8b949e">背景：这个账号频繁遇到「at capacity」误拒和疑似模型降智，官方不留任何记录。
本页每 5 分钟轮询一次，给这个账号留一份带时间戳、公开可查的体检档案。</span></div>
<div class="grid">{''.join(cards)}</div>
<h2>All rounds</h2>
<table><thead><tr><th>Time (SGT)</th><th>Model</th><th>Status</th><th>Duration (s)</th>
<th>Input</th><th>Cached</th><th>Output</th><th>Reasoning</th><th>Total tok</th><th>Error</th><th>SVG</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, timeout=120)


def main() -> int:
    lock_path = REPO / ".round.lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another round is still running; skipping", flush=True)
        return 0
    round_id = datetime.now(SGT).strftime("%Y%m%d-%H%M%S")
    print(f"round {round_id}: {len(MODELS)} models, one attempt each", flush=True)
    results = []
    for model in MODELS:
        rec = run_model(model, round_id)
        results.append(rec)
        print(f"  {model}: {rec['status']} {rec['duration_s']}s "
              f"tok={rec['total_tokens']} err={(rec['error'] or '')[:80]}", flush=True)
    stats_path = REPO / "stats.json"
    records = []
    if stats_path.exists():
        records = json.loads(stats_path.read_text(encoding="utf-8"))
    records.extend(results)
    stats_path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    (REPO / "index.html").write_text(build_index(records), encoding="utf-8")
    (REPO / "runs" / round_id / "meta.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    ok_n = sum(1 for r in results if r["status"] == "ok")
    git("add", "-A")
    commit = git("commit", "-m",
                 f"round {round_id}: {ok_n}/{len(results)} SVG ok\n\n"
                 f"Built-By: Codex (per-model, see stats.json) via run_round.py on songyy-pi\n"
                 f"Verified-By: Alberto (Muse Wonder)")
    if commit.returncode != 0:
        print("commit failed:", commit.stdout, commit.stderr, flush=True)
    push = git("push", "origin", "main")
    if push.returncode != 0:
        print("PUSH FAILED (will retry next round):",
              (push.stderr or push.stdout).strip()[:300], flush=True)
    else:
        print("pushed main", flush=True)
        # GitHub Pages is served from the gh-pages branch (same tree as main).
        push_gh = git("push", "origin", "main:gh-pages")
        if push_gh.returncode != 0:
            print("GH-PAGES PUSH FAILED (will retry next round):",
                  (push_gh.stderr or push_gh.stdout).strip()[:300], flush=True)
        else:
            print("pushed gh-pages", flush=True)
    print(f"round {round_id} done: {ok_n}/{len(results)} ok", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
