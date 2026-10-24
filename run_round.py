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
from concurrent.futures import ThreadPoolExecutor

REPO = Path(__file__).resolve().parent
SGT = ZoneInfo("Asia/Singapore")
MODELS = [
    "gpt-6-astra",
    "gpt-6.1-sol",
    "gpt-6-luna",
    "gpt-5.6-terra",
]
PER_MODEL_TIMEOUT = 180  # seconds; hard cap, no retry after this
PROMPTS = {
"pelican": (
    "Draw a satirical cartoon as ONE single self-contained SVG document "
    "(viewBox=\"0 0 800 600\"). Theme: a pelican riding a bicycle. Make it funny "
    "and visually expressive, with a clear single scene, readable characters, and "
    "a bold title plus a short caption about the pelican on the bicycle. Output ONLY "
    "the SVG code: no markdown fences, no explanation, no text outside the document."
),
"substitution": (
    "Draw a satirical cartoon as ONE single self-contained SVG document "
    "(viewBox=\"0 0 800 600\"). Theme: a service promises a premium model but quietly "
    "substitutes a cheap weak model. Show the bait-and-switch clearly and humorously, "
    "with a bold title and short caption. Output ONLY the SVG code: no markdown fences, "
    "no explanation, no text outside the <svg>...</svg> document."
),
}
PROMPT_VARIANT = os.environ.get("PROBE_VARIANT", "pelican")
if PROMPT_VARIANT not in PROMPTS:
    raise ValueError(f"unknown PROBE_VARIANT: {PROMPT_VARIANT}")
PROMPT = PROMPTS[PROMPT_VARIANT]

# The small cross-provider panel on the site compares only these four pairs.
# Claude outputs are produced separately by compare_claude.py via Anthropic's API.
PAIRINGS = [
    ("gpt-6-astra", "claude-fable-5-1", "Fable 5.1"),
    ("gpt-6.1-sol", "claude-opus-5-5", "Opus 5.5"),
    ("gpt-6-luna", "claude-haiku-5-5", "Haiku 5.5"),
    ("gpt-5.6-terra", "claude-sonnet-5-5", "Sonnet 5.5"),
]


def run_model(model: str, round_id: str) -> dict:
    env = dict(os.environ)
    env["PATH"] = str(Path.home() / ".local" / "bin") + ":" + env.get("PATH", "")
    started = datetime.now(SGT)
    t0 = time.monotonic()
    rec = {
        "round": round_id,
        "variant": PROMPT_VARIANT,
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
    attempts = len(records)
    all_ok = sum(1 for r in records if r["status"] == "ok")
    durations = sorted(r["duration_s"] for r in records if isinstance(r.get("duration_s"), (int, float)))
    median = durations[len(durations) // 2] if durations else None
    if durations and len(durations) % 2 == 0:
        median = round((durations[len(durations) // 2 - 1] + durations[len(durations) // 2]) / 2, 2)
    cards = []
    for r in latest_recs:
        if r["svg"]:
            art = f'<img src="{html.escape(r["svg"])}" alt="SVG by {html.escape(r["model"])}" loading="lazy">'
        else:
            art = f'<div class="noart">✕ no SVG<small>{html.escape((r["error"] or "")[:140])}</small></div>'
        state = "PASS" if r["status"] == "ok" else "FAIL"
        cards.append(
            f'<figure class="card"><div class="art">{art}</div><figcaption><div><b>{html.escape(r["model"])}</b>'
            f'<span class="state {"pass" if state == "PASS" else "fail"}">{state}</span></div>'
            f'<small>{r["duration_s"] or "—"}s · {r["total_tokens"] or "—"} tokens</small></figcaption></figure>'
        )
    pair_cards = []
    comparison_root = REPO / "comparisons"
    comparison_files = sorted(comparison_root.glob("*/claude-*/claude.svg")) if comparison_root.exists() else []
    for codex_model, claude_id, claude_label in PAIRINGS:
        codex = next((r for r in latest_recs if r["model"] == codex_model and r.get("svg")), None)
        claude_paths = [p for p in comparison_files if p.parent.name == claude_id]
        claude = claude_paths[-1] if claude_paths else None
        if not codex and not claude:
            continue
        left = (f'<img src="{html.escape(codex["svg"])}" alt="{html.escape(codex_model)}" loading="lazy">'
                if codex else '<div class="noart">No Codex image</div>')
        if claude:
            rel = claude.relative_to(REPO).as_posix()
            right = f'<img src="{html.escape(rel)}" alt="{html.escape(claude_label)}" loading="lazy">'
        else:
            right = '<div class="noart">No Claude image yet</div>'
        pair_cards.append(f'<article class="pair"><div><small>CODEX · {html.escape(codex_model)}</small>{left}</div>'
                          f'<div><small>CLAUDE API · {html.escape(claude_label)}</small>{right}</div></article>')
    prompt_text = html.escape(PROMPT)
    payload = html.escape(json.dumps(sorted(records, key=lambda x: (x["round"], x["time_sgt"]), reverse=True), ensure_ascii=False), quote=False)
    # The JSON is inserted into a script tag; escaping '<' prevents a data value from closing it.
    payload = payload.replace("&lt;", "\\u003c").replace("&gt;", "\\u003e").replace("&amp;", "&")
    updated = datetime.now(SGT).strftime("%Y-%m-%d %H:%M:%S SGT")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>At capacity census · Codex account monitor</title>
<style>
*{{box-sizing:border-box}} :root{{color-scheme:dark;--bg:#0b0f14;--panel:#121923;--line:#263241;--muted:#8b99a8;--ink:#edf3f8;--cyan:#6ee7f9;--green:#73e2a3;--red:#ff7b86;--amber:#f7c66a}}
body{{background:radial-gradient(circle at 80% -20%,#163346 0,#0b0f14 38rem);color:var(--ink);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}}
main{{max-width:1440px;margin:auto;padding:34px 24px 64px}} header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-end;margin-bottom:28px}}
h1{{font-size:clamp(28px,4vw,52px);letter-spacing:-.045em;line-height:1.02;margin:0 0 9px}} h1 span{{color:var(--cyan)}}
.eyebrow{{color:var(--cyan);font:700 11px/1.2 ui-monospace,monospace;letter-spacing:.16em;text-transform:uppercase}} .lede{{color:var(--muted);max-width:760px;margin:0}}
a{{color:var(--cyan)}} .links{{white-space:nowrap}} .links a{{border:1px solid var(--line);border-radius:999px;padding:8px 12px;text-decoration:none;margin-left:6px}}
.panel{{background:rgba(18,25,35,.86);border:1px solid var(--line);border-radius:16px;padding:18px;margin:18px 0;box-shadow:0 14px 40px #0002}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}} .metric{{padding:14px 16px;border-left:2px solid var(--cyan);background:#0e151e;border-radius:10px}} .metric b{{display:block;font-size:25px;letter-spacing:-.04em}} .metric small,.muted{{color:var(--muted)}}
.section-head{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:32px 0 12px}} h2{{font-size:20px;margin:0}} .section-head p{{color:var(--muted);margin:0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}} .card{{background:#0e151e;border:1px solid var(--line);border-radius:12px;margin:0;overflow:hidden}} .art{{aspect-ratio:4/3;background:#fff;display:grid;place-items:center}} .card img{{width:100%;height:100%;object-fit:contain;display:block}} .card figcaption{{padding:11px 13px}} .card figcaption div{{display:flex;justify-content:space-between;gap:8px}} .card small{{color:var(--muted)}} .state{{font:700 10px ui-monospace,monospace;letter-spacing:.08em}} .pass{{color:var(--green)}} .fail{{color:var(--red)}} .noart{{padding:20px;text-align:center;color:var(--red)}} .noart small{{display:block;color:var(--muted);margin-top:8px}}
.pairs{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}} .pair{{display:grid;grid-template-columns:1fr 1fr;gap:8px;background:#0e151e;border:1px solid var(--line);border-radius:12px;padding:9px}} .pair small{{display:block;color:var(--muted);font:10px ui-monospace,monospace;margin:2px 3px 7px}} .pair img{{width:100%;aspect-ratio:4/3;object-fit:contain;background:#fff;border-radius:7px;display:block}} details summary{{cursor:pointer;color:var(--cyan);font-weight:700}} .prompt{{white-space:pre-wrap;color:#c8d5e0;background:#0b1118;border:1px solid var(--line);padding:14px;border-radius:8px;font:12px/1.55 ui-monospace,monospace;margin:14px 0 0}}
.chart{{display:flex;gap:8px;align-items:flex-end;height:150px;padding:14px 4px 0;overflow:auto}} .bar-wrap{{min-width:42px;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:6px}} .bar{{width:26px;min-height:3px;background:linear-gradient(#6ee7f9,#347d9a);border-radius:5px 5px 2px 2px}} .bar.zero{{background:var(--red)}} .bar-label{{color:var(--muted);font:10px ui-monospace,monospace;writing-mode:vertical-rl;transform:rotate(180deg)}}
.toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}} input,select{{background:#0b1118;border:1px solid var(--line);border-radius:8px;color:var(--ink);padding:9px 11px;font:inherit}} input{{min-width:240px;flex:1}} .table-wrap{{overflow:auto}} table{{border-collapse:collapse;width:100%;font-size:12px;min-width:1000px}} th,td{{border-bottom:1px solid #202b38;padding:9px 8px;text-align:left;vertical-align:top}} th{{color:var(--muted);font-size:11px;letter-spacing:.04em;text-transform:uppercase;position:sticky;top:0;background:#121923}} td.n{{text-align:right;font-variant-numeric:tabular-nums}} td.errtxt{{color:var(--red);max-width:300px;word-break:break-word}} .pager{{display:flex;justify-content:space-between;align-items:center;margin-top:12px;color:var(--muted)}} button{{background:#172331;border:1px solid var(--line);border-radius:7px;color:var(--ink);padding:7px 11px;cursor:pointer}} button:disabled{{opacity:.4;cursor:not-allowed}}
@media(max-width:760px){{main{{padding:24px 14px 48px}}header{{display:block}}.links{{margin-top:18px}}.metrics{{grid-template-columns:repeat(2,1fr)}}.panel{{padding:14px}}}}
</style></head><body><main>
<header><div><div class="eyebrow">PUBLIC ACCOUNT MONITOR · 5 MINUTE CENSUS</div><h1>When the door says <span>at capacity</span>.</h1><p class="lede">One Codex account, eight models in parallel, one attempt each. The SVGs are the probe; timestamps, latency, token drift and failures are the evidence.</p></div><div class="links"><a href="stats.json">raw stats.json</a><a href="https://github.com/geekysong/codex-model-at-capacity">source ↗</a></div></header>
<section class="metrics"><div class="metric"><small>Latest round</small><b>{ok_n}/{len(latest_recs)}</b><small>models returned an SVG</small></div><div class="metric"><small>All attempts</small><b>{attempts}</b><small>{len(rounds)} rounds · {all_ok / attempts * 100 if attempts else 0:.1f}% success</small></div><div class="metric"><small>Median latency</small><b>{median if median is not None else "—"}<small> s</small></b><small>across recorded attempts</small></div><div class="metric"><small>Last seen</small><b style="font-size:16px">{latest or "—"}</b><small>{updated}</small></div></section>
<section class="panel"><div class="section-head"><h2>Latest round · {latest or "—"}</h2><p>{ok_n}/{len(latest_recs)} passed · once per model · no retries</p></div><div class="grid">{''.join(cards)}</div></section>
<section class="panel"><div class="section-head"><h2>Cross-provider pairs</h2><p>Codex subscription vs Claude API · same prompt</p></div><div class="pairs">{''.join(pair_cards) or '<p class="muted">Claude comparison images are not available yet.</p>'}</div></section>
<section class="panel"><details><summary>Probe prompt used for every image</summary><pre class="prompt">{prompt_text}</pre></details></section>
<section class="panel"><div class="section-head"><h2>Capacity signal by round</h2><p>bar height = successful attempts</p></div><div id="chart" class="chart"></div></section>
<section class="panel"><div class="section-head"><h2>Full attempt log</h2><p>raw records, searchable and paginated</p></div><div class="toolbar"><input id="search" type="search" placeholder="Filter model, status, error or round…"><select id="model"><option value="">All models</option></select><select id="status"><option value="">All statuses</option><option value="ok">ok</option><option value="error">error</option></select></div><div class="table-wrap"><table><thead><tr><th>Time (SGT)</th><th>Round</th><th>Model</th><th>Status</th><th>Duration</th><th>Input</th><th>Cached</th><th>Output</th><th>Reasoning</th><th>Total</th><th>Error</th><th>SVG</th></tr></thead><tbody id="tbody"></tbody></table></div><div class="pager"><span id="count"></span><span><button id="prev">Previous</button> <button id="next">Next</button></span></div></section>
<section class="panel muted"><b>为什么做这件事？</b> 重要任务不会交给一个疑似降智的 Codex 去做；这里的 SVG 只是低风险探针。额度没怎么用却反复收到 “Selected model is at capacity”，同时怀疑模型质量悄悄下降。官方没有可查记录，所以这个账号每 5 分钟公开留下一份体检档案：错误率暴露容量问题，耗时、token 用量和任务失败是降智的早期信号。<br><span>In October 2026 this account began seeing unexplained capacity refusals and suspected silent degradation. This page makes the evidence reproducible: the Raspberry Pi runs <code>run_round.py</code>, appends to <code>stats.json</code>, rebuilds this page, and publishes both branches. A separate subjective quality series is planned: Claude Code will score fixed benchmark answers with a versioned rubric. No subjective score is shown until those reviews exist.</span></section>
</main><script>
const records = {payload}; const pageSize = 25; let page = 0;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const models = [...new Set(records.map(r => r.model))]; const modelSelect = document.querySelector('#model'); models.forEach(m => modelSelect.insertAdjacentHTML('beforeend', `<option>${{esc(m)}}</option>`));
const rounds = [...new Set(records.map(r => r.round))].sort(); const chart = document.querySelector('#chart'); rounds.slice(-24).forEach(round => {{ const rs=records.filter(r=>r.round===round), ok=rs.filter(r=>r.status==='ok').length, bar=document.createElement('div'); bar.className='bar-wrap'; bar.title=`${{round}} · ${{ok}}/${{rs.length}} ok`; bar.innerHTML=`<div class="bar ${{ok?'':'zero'}}" style="height:${{Math.max(3,ok/Math.max(rs.length,1)*100)}}%"></div><div class="bar-label">${{round.slice(4)}}</div>`; chart.append(bar); }});
function render() {{ const q=document.querySelector('#search').value.toLowerCase(), m=modelSelect.value, s=document.querySelector('#status').value; const filtered=records.filter(r=>(!q||JSON.stringify(r).toLowerCase().includes(q))&&(!m||r.model===m)&&(!s||r.status===s)); const pages=Math.max(1,Math.ceil(filtered.length/pageSize)); page=Math.min(page,pages-1); document.querySelector('#tbody').innerHTML=filtered.slice(page*pageSize,(page+1)*pageSize).map(r=>`<tr><td>${{esc(r.time_sgt)}}</td><td>${{esc(r.round)}}</td><td><b>${{esc(r.model)}}</b></td><td class="${{r.status==='ok'?'pass':'fail'}}">${{esc(r.status)}}</td><td class="n">${{r.duration_s??'—'}}s</td><td class="n">${{r.input_tokens??'—'}}</td><td class="n">${{r.cached_input_tokens??'—'}}</td><td class="n">${{r.output_tokens??'—'}}</td><td class="n">${{r.reasoning_tokens??'—'}}</td><td class="n">${{r.total_tokens??'—'}}</td><td class="errtxt">${{esc(r.error)}}</td><td>${{r.svg?`<a href="${{esc(r.svg)}}">view</a>`:'—'}}</td></tr>`).join(''); document.querySelector('#count').textContent=`${{filtered.length}} records · page ${{page+1}}/${{pages}}`; document.querySelector('#prev').disabled=page===0; document.querySelector('#next').disabled=page>=pages-1; }}
['search','model','status'].forEach(id=>document.querySelector('#'+id).addEventListener('input',()=>{{page=0;render()}})); document.querySelector('#prev').onclick=()=>{{page--;render()}}; document.querySelector('#next').onclick=()=>{{page++;render()}}; render();
</script></body></html>"""


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
    round_id = datetime.now(SGT).strftime("%Y%m%d-%H%M%S") + "-" + PROMPT_VARIANT
    print(f"round {round_id}: {len(MODELS)} models, one attempt each", flush=True)
    # All models run concurrently: each codex exec mostly waits on the API,
    # so the Pi handles 8 in parallel fine, and a round takes ~max(duration)
    # instead of the sum. Each model's duration is still its own wall-clock.
    with ThreadPoolExecutor(max_workers=len(MODELS)) as pool:
        results = list(pool.map(lambda m: run_model(m, round_id), MODELS))
    for rec in results:
        print(f"  {rec['model']}: {rec['status']} {rec['duration_s']}s "
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
    # Publish both refs independently. A transient failure on main must not
    # prevent the Pages branch from receiving the generated index.html.
    push = git("push", "origin", "main")
    if push.returncode != 0:
        print("PUSH MAIN FAILED (will retry next round):",
              (push.stderr or push.stdout).strip()[:300], flush=True)
    else:
        print("pushed main", flush=True)
    # GitHub Pages is served from gh-pages, which mirrors the committed tree.
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
