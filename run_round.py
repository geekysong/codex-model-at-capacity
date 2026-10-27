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
from daily_prompt import load_daily_prompt
from claude_daily import matching_artifacts
from challenge_validation import validate_daily_artifact

REPO = Path(__file__).resolve().parent
GA_MEASUREMENT_ID = "G-846Y37CFNX"
SGT = ZoneInfo("Asia/Singapore")
MODELS = [
    "gpt-6-astra",
    "gpt-6.1-sol",
    "gpt-6-luna",
    "gpt-6.1-terra",
]
PER_MODEL_TIMEOUT = 600  # seconds; hard cap, no retry after this
from probe_prompts import ACTIVE_VARIANTS, load_prompt, timestamped_prompt
PROMPT_VARIANT = os.environ.get("PROBE_VARIANT", "daily")
PROMPT, PROMPT_DATE, PROMPT_SHA = load_prompt(PROMPT_VARIANT)
PROMPTS = {variant: load_prompt(variant)[0] for variant in ACTIVE_VARIANTS}

# The small cross-provider panel on the site compares only these four pairs.
# Claude outputs are produced separately by compare_claude.py via Anthropic's API.
PAIRINGS = [
    ("gpt-6-astra", "claude-fable-5-1", "Fable 5.1"),
    ("gpt-6.1-sol", "claude-opus-5-5", "Opus 5.5"),
    ("gpt-6-luna", "claude-haiku-5-5", "Haiku 5.5"),
    ("gpt-6.1-terra", "claude-sonnet-5-5", "Sonnet 5.5"),
]


def apply_artifact_validation(rec: dict, svg_path: Path, prompt: str, prompt_date: str, prompt_sha: str) -> dict:
    """Mark recognized Daily answer failures without retrying or discarding SVGs."""
    error = validate_daily_artifact(svg_path, rec, prompt_date, prompt_sha, prompt)
    if error:
        rec["status"] = "error" if error.startswith("invalid SVG:") else "semantic_error"
        rec["error"] = error[:400]
    else:
        rec["status"] = "ok"
    return rec


def run_model(model: str, round_id: str) -> dict:
    env = dict(os.environ)
    env["PATH"] = str(Path.home() / ".local" / "bin") + ":" + env.get("PATH", "")
    started = datetime.now(SGT)
    request_timestamp, request_prompt = timestamped_prompt(PROMPT, started)
    t0 = time.monotonic()
    rec = {
        "round": round_id,
        "variant": PROMPT_VARIANT,
        "prompt_date": PROMPT_DATE,
        "prompt_sha": PROMPT_SHA,
        "request_timestamp": request_timestamp,
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
                request_prompt,
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
        return apply_artifact_validation(rec, svg_path, PROMPT, PROMPT_DATE, PROMPT_SHA)
    except subprocess.TimeoutExpired:
        rec["duration_s"] = round(time.monotonic() - t0, 2)
        rec["error"] = f"timeout after {PER_MODEL_TIMEOUT}s (no retry, per spec)"
        return rec
    except Exception as e:  # noqa: BLE001 - record anything, keep the round going
        rec["duration_s"] = round(time.monotonic() - t0, 2)
        rec["error"] = f"runner exception: {e}"[:400]
        return rec


def build_index(records: list[dict]) -> str:
    def public_error(value: object) -> str:
        """Keep operational error context while removing common secrets/PII."""
        text = str(value or "unknown error")
        text = re.sub(r"(?i)(api[_ -]?key|authorization|bearer|token)\s*[:=]\s*[^\s|,;]+", r"\1=[redacted]", text)
        text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email redacted]", text)
        text = re.sub(r"(?:/home|/Users|/tmp|/var)/[^\s|]+", "[path redacted]", text)
        return html.escape(text[:240])

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
            art = f'<div class="noart">✕ no SVG<small>{public_error(r["error"])}</small></div>'
        state = "PASS" if r["status"] == "ok" else "FAIL"
        cards.append(
            f'<figure class="card"><div class="art">{art}</div><figcaption><div><b>{html.escape(r["model"])}</b>'
            f'<span class="state {"pass" if state == "PASS" else "fail"}">{state}</span></div>'
            f'<small>{r["duration_s"] or "—"}s · {r["total_tokens"] or "—"} tokens</small></figcaption></figure>'
        )
    pair_sections = []
    comparison_root = REPO / "comparisons"
    comparison_files = sorted(comparison_root.glob("*/*/claude-*/claude.svg")) if comparison_root.exists() else []
    for variant in ACTIVE_VARIANTS:
        variant_prompt, challenge_day, challenge_sha = load_prompt(variant)
        # Records from the original capacity probe have no variant field and
        # must not be mistaken for the newer pelican round.
        variant_records = [r for r in records if r.get("variant", "legacy") == variant
                           and r.get("prompt_date") == challenge_day and r.get("prompt_sha") == challenge_sha]
        pair_cards = []
        for codex_model, claude_id, claude_label in PAIRINGS:
            latest_model = max(
                (r for r in variant_records if r["model"] == codex_model),
                key=lambda r: (r["round"], r["time_sgt"]), default=None,
            )
            codex = latest_model if latest_model and latest_model.get("svg") else None
            claude_paths = matching_artifacts(REPO, variant, claude_id, challenge_day, challenge_sha)
            claude = claude_paths[-1] if claude_paths else None
            left = (f'<img src="{html.escape(codex["svg"])}" alt="{html.escape(codex_model)}" loading="lazy">'
                    if codex else f'<div class="noart">No Codex image<small>{public_error(latest_model.get("error") if latest_model else "no record")}</small></div>')
            if latest_model:
                left += f'<small>{html.escape(latest_model["time_sgt"])} SGT</small>'
            if claude:
                rel = claude.relative_to(REPO).as_posix()
                cost = ""
                meta = {}
                try:
                    meta = json.loads(claude.with_name("meta.json").read_text(encoding="utf-8"))
                    cost = f' · ${meta["estimated_cost_usd"]:.6f} est.' if meta.get("estimated_cost_usd") is not None else ""
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                right = f'<img src="{html.escape(rel)}" alt="{html.escape(claude_label)}" loading="lazy">'
                right += f'<small>{html.escape(meta.get("time_sgt", challenge_day))} SGT · {html.escape(challenge_sha)}{cost}</small>'
            else:
                error = f"No successful Claude control for {challenge_day} / {challenge_sha}; awaiting daily run"
                meta_path = claude_paths[-1].with_name("meta.json") if claude_paths else None
                if meta_path and meta_path.exists():
                    try:
                        error = json.loads(meta_path.read_text(encoding="utf-8")).get("error") or "Claude returned no image"
                    except (OSError, ValueError):
                        error = "Claude metadata unavailable"
                right = f'<div class="noart">No Claude image<small>{public_error(error)}</small></div>'
            pair_cards.append(f'<article class="pair"><div><small>CODEX · {html.escape(codex_model)}</small>{left}</div>'
                              f'<div><small>CLAUDE API · {html.escape(claude_label)}</small>{right}</div></article>')
        if pair_cards:
            round_prompt = html.escape(variant_prompt)
            pair_sections.append(
                f'<h3>{html.escape("Pelican" if variant == "pelican" else "Daily Challenge")}</h3>'
                f'<details class="round-prompt"><summary>Prompt for this round</summary><pre class="prompt">{round_prompt}</pre></details>'
                f'<div class="pairs">{"".join(pair_cards)}</div>'
            )
    payload = html.escape(json.dumps(sorted(records, key=lambda x: (x["round"], x["time_sgt"]), reverse=True), ensure_ascii=False), quote=False)
    # The JSON is inserted into a script tag; escaping '<' prevents a data value from closing it.
    payload = payload.replace("&lt;", "\\u003c").replace("&gt;", "\\u003e").replace("&amp;", "&")
    updated = datetime.now(SGT).strftime("%Y-%m-%d %H:%M:%S SGT")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){{dataLayer.push(arguments);}}
gtag('js', new Date());
gtag('config', '{GA_MEASUREMENT_ID}');
</script>
<title>At capacity census · Codex account monitor</title>
<style>
*{{box-sizing:border-box}} :root{{color-scheme:dark;--bg:#0b0f14;--panel:#121923;--line:#263241;--muted:#8b99a8;--ink:#edf3f8;--cyan:#6ee7f9;--green:#73e2a3;--red:#ff7b86;--amber:#f7c66a}}
body{{background:radial-gradient(circle at 80% -20%,#163346 0,#0b0f14 38rem);color:var(--ink);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}}
main{{max-width:1440px;margin:auto;padding:34px 24px 64px}} header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-end;margin-bottom:28px}}
h1{{font-size:clamp(28px,4vw,52px);letter-spacing:-.045em;line-height:1.02;margin:0 0 9px}} h1 span{{color:var(--cyan)}}
.eyebrow{{color:var(--cyan);font:700 11px/1.2 ui-monospace,monospace;letter-spacing:.16em;text-transform:uppercase}} .lede{{color:var(--muted);max-width:760px;margin:0}}
a{{color:var(--cyan)}} .links{{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:6px}} .links a{{border:1px solid var(--line);border-radius:999px;padding:8px 12px;text-decoration:none}} .language-switch{{display:inline-flex;gap:2px;padding:2px;background:#0e151e;border:1px solid var(--line);border-radius:999px}} .language-switch button{{border:0;border-radius:999px;padding:6px 10px;background:transparent;color:var(--muted);font-size:12px}} .language-switch button:hover,.language-switch button:focus-visible{{color:var(--ink);background:#223244}} body:not(.zh) .language-switch [data-language="en"],body.zh .language-switch [data-language="zh"]{{background:var(--cyan);color:#071018}}
.panel{{background:rgba(18,25,35,.86);border:1px solid var(--line);border-radius:16px;padding:18px;margin:18px 0;box-shadow:0 14px 40px #0002}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}} .metric{{padding:14px 16px;border-left:2px solid var(--cyan);background:#0e151e;border-radius:10px}} .metric b{{display:block;font-size:25px;letter-spacing:-.04em}} .metric small,.muted{{color:var(--muted)}}
.section-head{{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:32px 0 12px}} h2{{font-size:20px;margin:0}} .section-head p{{color:var(--muted);margin:0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}} .card{{background:#0e151e;border:1px solid var(--line);border-radius:12px;margin:0;overflow:hidden}} .art{{aspect-ratio:4/3;background:#fff;display:grid;place-items:center}} .card img{{width:100%;height:100%;object-fit:contain;display:block}} .card figcaption{{padding:11px 13px}} .card figcaption div{{display:flex;justify-content:space-between;gap:8px}} .card small{{color:var(--muted)}} .state{{font:700 10px ui-monospace,monospace;letter-spacing:.08em}} .pass{{color:var(--green)}} .fail{{color:var(--red)}} .noart{{padding:20px;text-align:center;color:var(--red)}} .noart small{{display:block;color:var(--muted);margin-top:8px}}
.pairs{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}} .pair{{display:grid;grid-template-columns:1fr 1fr;gap:8px;background:#0e151e;border:1px solid var(--line);border-radius:12px;padding:9px}} .pair small{{display:block;color:var(--muted);font:10px ui-monospace,monospace;margin:2px 3px 7px}} .pair img{{width:100%;aspect-ratio:4/3;object-fit:contain;background:#fff;border-radius:7px;display:block}} details summary{{cursor:pointer;color:var(--cyan);font-weight:700}} .round-disclosure summary{{display:flex;justify-content:space-between;gap:12px;align-items:center}} .round-disclosure summary span{{color:var(--muted);font-size:12px;font-weight:400}} .round-disclosure .grid{{margin-top:14px}} .prompt{{white-space:pre-wrap;color:#c8d5e0;background:#0b1118;border:1px solid var(--line);padding:14px;border-radius:8px;font:12px/1.55 ui-monospace,monospace;margin:14px 0 0}} .lang-zh{{display:none}} body.zh .lang-en{{display:none}} body.zh .lang-zh{{display:block}}
.chart{{display:grid;grid-template-columns:34px minmax(0,1fr);gap:8px;height:190px;padding:14px 4px 0;overflow:auto}} .y-axis{{display:flex;flex-direction:column;justify-content:space-between;padding:0 7px 24px 0;border-right:1px solid var(--line);color:var(--muted);font:10px ui-monospace,monospace;text-align:right}} .plot{{display:flex;align-items:stretch;gap:8px;min-width:max-content;height:100%;border-bottom:1px solid var(--line);background:repeating-linear-gradient(to bottom,transparent 0,transparent calc(50% - 1px),#26324155 50%,transparent calc(50% + 1px))}} .bar-wrap{{min-width:42px;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:6px}} .bar{{width:26px;min-height:3px;background:linear-gradient(#6ee7f9,#347d9a);border-radius:5px 5px 0 0}} .bar.zero{{background:var(--red)}} .bar-label{{color:var(--muted);font:10px ui-monospace,monospace;white-space:nowrap;transform:rotate(-45deg);transform-origin:top center;margin-top:4px}}
.toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}} input,select{{background:#0b1118;border:1px solid var(--line);border-radius:8px;color:var(--ink);padding:9px 11px;font:inherit}} input{{min-width:240px;flex:1}} .table-wrap{{overflow:auto}} table{{border-collapse:collapse;width:100%;font-size:12px;min-width:1000px}} th,td{{border-bottom:1px solid #202b38;padding:9px 8px;text-align:left;vertical-align:top}} th{{color:var(--muted);font-size:11px;letter-spacing:.04em;text-transform:uppercase;position:sticky;top:0;background:#121923}} td.n{{text-align:right;font-variant-numeric:tabular-nums}} td.errtxt{{color:var(--red);max-width:300px;word-break:break-word}} .pager{{display:flex;justify-content:space-between;align-items:center;margin-top:12px;color:var(--muted)}} button{{background:#172331;border:1px solid var(--line);border-radius:7px;color:var(--ink);padding:7px 11px;cursor:pointer}} button:disabled{{opacity:.4;cursor:not-allowed}}
@media(max-width:760px){{main{{padding:24px 14px 48px}}header{{display:block}}.links{{margin-top:18px}}.metrics{{grid-template-columns:repeat(2,1fr)}}.panel{{padding:14px}}.pairs{{grid-template-columns:1fr}}}}
</style></head><body><main>
<header><div><div class="eyebrow">PUBLIC ACCOUNT MONITOR · 30 MINUTE CENSUS</div><h1>When the door says <span>at capacity</span>.</h1><p class="lede">One Codex account, four models in sequence, two challenges, one attempt each. The SVGs are the probe; timestamps, latency, token drift and failures are the evidence.</p></div><div class="links"><a href="stats.json">raw stats.json</a><a href="history.html">history / 历史轮次</a><a href="https://github.com/geekysong/codex-model-at-capacity">source ↗</a><div class="language-switch" role="group" aria-label="Language"><button type="button" data-language="en">English</button><button type="button" data-language="zh">中文</button></div></div></header>
<section class="panel intro"><div class="lang-en"><b>Why this exists</b><p>Important work should not depend on a possibly degraded Codex. These SVGs are low-risk probes: capacity errors, latency, token use and failures make availability changes reproducible. In October 2026 this account began seeing unexplained capacity refusals and suspected silent degradation. The Raspberry Pi records each attempt, rebuilds this page and publishes both branches. Independent visual reviews compare pelican drawings with a fixed Astra reference. These subjective scores describe visible output quality, not general model intelligence.</p></div><div class="lang-zh"><b>为什么做这件事</b><p>重要任务不应该依赖一个可能降智的 Codex。这些 SVG 是低风险探针：容量错误、耗时、token 用量和失败记录让可用性变化可以复现。2026 年 10 月，这个账号开始出现无法解释的容量拒绝和疑似能力下降。树莓派记录每次尝试、重建页面并发布两个分支。独立视觉评审以固定的 Astra 图片为基准，检查鹈鹕绘图。这些主观评分描述可见的画面问题，不代表模型整体能力。</p></div></section>
<section class="metrics"><div class="metric"><small>Latest round</small><b>{ok_n}/{len(latest_recs)}</b><small>models returned an SVG</small></div><div class="metric"><small>All attempts</small><b>{attempts}</b><small>{len(rounds)} rounds · {all_ok / attempts * 100 if attempts else 0:.1f}% success</small></div><div class="metric"><small>Median latency</small><b>{median if median is not None else "—"}<small> s</small></b><small>across recorded attempts</small></div><div class="metric"><small>Last seen</small><b style="font-size:16px">{latest or "—"}</b><small>{updated}</small></div></section>
<details class="panel round-disclosure"><summary><b>Latest round · {latest or "—"}</b><span>{ok_n}/{len(latest_recs)} passed · once per model · no retries</span></summary><div class="grid">{''.join(cards)}</div></details>
<section class="panel"><div class="section-head"><h2>Cross-provider pairs</h2><p>Codex subscription vs Claude API · four models · benchmark rounds</p></div>{''.join(pair_sections) or '<p class="muted">Claude comparison images are not available yet.</p>'}</section>
<section class="panel" id="quality-monitor" aria-label="Pelican quality / 鹈鹕绘图质量"><h2><span class="lang-en">Pelican quality over time</span><span class="lang-zh">鹈鹕绘图质量趋势</span></h2><p class="muted"><span class="lang-en">Loading visual reviews…</span><span class="lang-zh">正在加载视觉评审…</span></p></section>
<section class="panel"><div class="section-head"><h2>Capacity signal by round</h2><p>Y = successful attempts · X = round</p></div><div id="chart" class="chart"><div id="y-axis" class="y-axis"></div><div id="plot" class="plot"></div></div></section>
<section class="panel"><div class="section-head"><h2>Full attempt log</h2><p>raw records, searchable and paginated</p></div><div class="toolbar"><input id="search" type="search" placeholder="Filter model, status, error or round…"><select id="model"><option value="">All models</option></select><select id="status"><option value="">All statuses</option><option value="ok">ok</option><option value="error">error</option></select></div><div class="table-wrap"><table><thead><tr><th>Time (SGT)</th><th>Round</th><th>Model</th><th>Status</th><th>Duration</th><th>Input</th><th>Cached</th><th>Output</th><th>Reasoning</th><th>Total</th><th>Error</th><th>SVG</th></tr></thead><tbody id="tbody"></tbody></table></div><div class="pager"><span id="count"></span><span><button id="prev">Previous</button> <button id="next">Next</button></span></div></section>
</main><script>
const records = {payload}; const pageSize = 25; let page = 0;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const models = [...new Set(records.map(r => r.model))]; const modelSelect = document.querySelector('#model'); models.forEach(m => modelSelect.insertAdjacentHTML('beforeend', `<option>${{esc(m)}}</option>`));
const rounds = [...new Set(records.map(r => r.round))].sort(); const plot = document.querySelector('#plot'); const chartRounds = rounds.slice(-24); const maxOk = Math.max(1, ...chartRounds.map(round => records.filter(r=>r.round===round && r.status==='ok').length)); document.querySelector('#y-axis').innerHTML=`<span>${{maxOk}}</span><span>${{Math.ceil(maxOk/2)}}</span><span>0</span>`; chartRounds.forEach(round => {{ const rs=records.filter(r=>r.round===round), ok=rs.filter(r=>r.status==='ok').length, bar=document.createElement('div'); bar.className='bar-wrap'; bar.title=`${{round}} · ${{ok}}/${{rs.length}} ok`; bar.innerHTML=`<div class="bar ${{ok?'':'zero'}}" style="height:${{Math.max(3,ok/maxOk*100)}}%"></div><div class="bar-label">${{round.slice(4)}}</div>`; plot.append(bar); }});
function render() {{ const q=document.querySelector('#search').value.toLowerCase(), m=modelSelect.value, s=document.querySelector('#status').value; const filtered=records.filter(r=>(!q||JSON.stringify(r).toLowerCase().includes(q))&&(!m||r.model===m)&&(!s||r.status===s)); const pages=Math.max(1,Math.ceil(filtered.length/pageSize)); page=Math.min(page,pages-1); document.querySelector('#tbody').innerHTML=filtered.slice(page*pageSize,(page+1)*pageSize).map(r=>`<tr><td>${{esc(r.time_sgt)}}</td><td>${{esc(r.round)}}</td><td><b>${{esc(r.model)}}</b></td><td class="${{r.status==='ok'?'pass':'fail'}}">${{esc(r.status)}}</td><td class="n">${{r.duration_s??'—'}}s</td><td class="n">${{r.input_tokens??'—'}}</td><td class="n">${{r.cached_input_tokens??'—'}}</td><td class="n">${{r.output_tokens??'—'}}</td><td class="n">${{r.reasoning_tokens??'—'}}</td><td class="n">${{r.total_tokens??'—'}}</td><td class="errtxt">${{esc(r.error)}}</td><td>${{r.svg?`<a href="${{esc(r.svg)}}">view</a>`:'—'}}</td></tr>`).join(''); document.querySelector('#count').textContent=`${{filtered.length}} records · page ${{page+1}}/${{pages}}`; document.querySelector('#prev').disabled=page===0; document.querySelector('#next').disabled=page>=pages-1; }}
const textZh = {{'raw stats.json':'原始 stats.json','source ↗':'源代码 ↗','Latest round':'最新一轮','models returned an SVG':'模型返回了 SVG','All attempts':'全部尝试','Median latency':'延迟中位数','across recorded attempts':'所有记录尝试','Last seen':'最近记录','Cross-provider pairs':'跨提供商对比','Codex subscription vs Claude API · four models · benchmark rounds':'Codex 订阅 vs Claude API · 四个模型 · 基准轮次','Capacity signal by round':'每轮容量信号','Y = successful attempts · X = round':'Y = 成功次数 · X = 轮次','Full attempt log':'完整尝试记录','raw records, searchable and paginated':'原始记录，可搜索并分页','All models':'全部模型','All statuses':'全部状态','Previous':'上一页','Next':'下一页','Time (SGT)':'时间（SGT）','Round':'轮次','Model':'模型','Status':'状态','Duration':'耗时','Input':'输入','Cached':'缓存','Output':'输出','Reasoning':'推理','Total':'总计','Error':'错误','SVG':'SVG','view':'查看','ok':'成功','error':'错误'}};
const originalText = new WeakMap();
function setLanguage(lang) {{ document.body.classList.toggle('zh', lang==='zh'); const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT); let node; while(node=walker.nextNode()) {{ if(!originalText.has(node)) originalText.set(node,node.nodeValue); const original=originalText.get(node).trim(); let translated=textZh[original]; if(original.startsWith('Latest round · ')) translated='最新一轮 · '+original.slice(16); else if(/^\\d+\\/\\d+ passed · once per model · no retries$/.test(original)) translated=original.replace(' passed · once per model · no retries',' 通过 · 每个模型一次 · 不重试'); if(translated) node.nodeValue=lang==='zh'?node.nodeValue.replace(original,translated):node.nodeValue.replace(translated,original); }} document.querySelector('#search').placeholder=lang==='zh'?'筛选模型、状态、错误或轮次…':'Filter model, status, error or round…'; }}
['search','model','status'].forEach(id=>document.querySelector('#'+id).addEventListener('input',()=>{{page=0;render()}})); document.querySelector('#prev').onclick=()=>{{page--;render()}}; document.querySelector('#next').onclick=()=>{{page++;render()}}; document.querySelectorAll('[data-language]').forEach(button=>button.addEventListener('click',()=>setLanguage(button.dataset.language))); setLanguage('en'); render();
</script><link rel="stylesheet" href="quality.css"><script src="quality.js"></script><link rel="stylesheet" href="zoom.css"><script src="zoom.js"></script></body></html>"""


def build_history(records: list[dict]) -> str:
    rounds = sorted({r["round"] for r in records}, reverse=True)
    sections = []
    for round_id in rounds:
        round_records = [r for r in records if r["round"] == round_id]
        ok = sum(r["status"] == "ok" for r in round_records)
        cards = []
        for r in round_records:
            if r.get("svg"):
                art = f'<img src="{html.escape(r["svg"])}" alt="SVG by {html.escape(r["model"])}" loading="lazy">'
            else:
                art = f'<div class="noart">✕ no SVG<small>{html.escape(str(r.get("error") or "unknown error")[:240])}</small></div>'
            state = "PASS" if r["status"] == "ok" else "FAIL"
            cards.append(
                f'<figure class="card"><div class="art">{art}</div><figcaption><div><b>{html.escape(r["model"])}</b>'
                f'<span class="state {"pass" if state == "PASS" else "fail"}">{state}</span></div>'
                f'<small>{r.get("time_sgt", "—")} · {r.get("duration_s") or "—"}s</small></figcaption></figure>'
            )
        sections.append(
            f'<details class="round"><summary>{html.escape(round_id)} · {ok}/{len(round_records)} passed</summary>'
            f'<div class="grid">{"".join(cards)}</div></details>'
        )
    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){{dataLayer.push(arguments);}}
gtag('js', new Date());
gtag('config', '{GA_MEASUREMENT_ID}');
</script>
<title>History · At capacity census</title><style>
*{{box-sizing:border-box}}:root{{--bg:#0b0f14;--panel:#121923;--line:#263241;--muted:#8b99a8;--ink:#edf3f8;--cyan:#6ee7f9;--green:#73e2a3;--red:#ff7b86}}body{{margin:0;background:radial-gradient(circle at 80% -20%,#163346 0,#0b0f14 38rem);color:var(--ink);font:14px/1.5 Inter,system-ui,sans-serif}}main{{max-width:1440px;margin:auto;padding:34px 24px 64px}}a{{color:var(--cyan)}}h1{{margin:0 0 8px;letter-spacing:-.04em}}.muted{{color:var(--muted)}}.links{{margin:16px 0 24px}}.links a{{margin-right:12px}}.round{{background:rgba(18,25,35,.9);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:12px 0}}summary{{cursor:pointer;color:var(--cyan);font:700 14px ui-monospace,monospace}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:14px}}.card{{background:#0e151e;border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:0}}.art{{aspect-ratio:4/3;background:#fff;display:grid;place-items:center}}.art img{{width:100%;height:100%;object-fit:contain;display:block}}figcaption{{padding:10px 12px}}figcaption div{{display:flex;justify-content:space-between}}small{{color:var(--muted)}}.pass{{color:var(--green)}}.fail{{color:var(--red)}}.noart{{padding:18px;text-align:center;color:var(--red)}}.noart small{{display:block;margin-top:8px}}@media(max-width:760px){{main{{padding:24px 14px 48px}}.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
</style></head><body><main><h1>History rounds</h1><p class="muted">Expand a round to inspect the SVGs, model status and latency recorded at that time.</p><div class="links"><a href="index.html">← dashboard</a><a href="stats.json">raw stats.json</a></div>{"".join(sections)}</main><link rel="stylesheet" href="zoom.css"><script src="zoom.js"></script></body></html>'''


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, timeout=120)


def sync_publication() -> bool:
    """Merge remote changes before publishing; never force-push research history."""
    fetched = git("fetch", "origin")
    if fetched.returncode:
        print("Publication fetch failed:", fetched.stderr, flush=True)
        return False
    for ref in ("origin/main", "origin/gh-pages"):
        merged = git("merge", "--no-edit", ref)
        if merged.returncode:
            conflicts = git("diff", "--name-only", "--diff-filter=U").stdout.splitlines()
            if not conflicts or not set(conflicts) <= {"index.html", "history.html"}:
                git("merge", "--abort")
                print("Publication needs manual merge:", ref, merged.stderr, flush=True)
                return False
        # Reload the merged generator so remote template updates are preserved.
        import importlib.util
        spec = importlib.util.spec_from_file_location("publication_builder", REPO / "run_round.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        records = json.loads((REPO / "stats.json").read_text(encoding="utf-8"))
        (REPO / "index.html").write_text(builder.build_index(records), encoding="utf-8")
        (REPO / "history.html").write_text(builder.build_history(records), encoding="utf-8")
        git("add", "index.html", "history.html")
        if merged.returncode:
            if git("commit", "--no-edit").returncode:
                return False
        elif git("diff", "--cached", "--quiet").returncode:
            if git("commit", "-m", "Rebuild pages after publication sync").returncode:
                return False
    return True


def main() -> int:
    global PROMPT, PROMPT_VARIANT, PROMPT_DATE, PROMPT_SHA
    lock_path = REPO / ".round.lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another round is still running; skipping", flush=True)
        return 0
    round_id = datetime.now(SGT).strftime("%Y%m%d-%H%M%S")
    print(f"round {round_id}: {len(MODELS)} models, one attempt each", flush=True)
    # Run models one at a time so a round resembles ordinary account use and
    # does not create a burst of simultaneous requests.
    results = []
    for variant in ACTIVE_VARIANTS:
        PROMPT_VARIANT = variant
        PROMPT, PROMPT_DATE, PROMPT_SHA = load_prompt(variant)
        variant_round = f"{round_id}-{variant}"
        batch = [run_model(model, variant_round) for model in MODELS]
        directory = REPO / "runs" / variant_round
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "meta.json").write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
        results.extend(batch)
    for rec in results:
        print(f"  {rec['model']}: {rec['status']} {rec['duration_s']}s "
              f"tok={rec['total_tokens']} err={(rec['error'] or '')[:80]}", flush=True)
    stats_path = REPO / "stats.json"
    records = []
    if stats_path.exists():
        records = json.loads(stats_path.read_text(encoding="utf-8"))
    records.extend(results)
    stats_path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    reviewer = REPO / ".venv-quality" / "bin" / "python"
    try:
        review = subprocess.run(
            [str(reviewer), "-B", str(REPO / "review_quality.py"), "--limit", "8"],
            cwd=REPO, capture_output=True, text=True, timeout=600,
        )
        print(review.stdout[-3000:], flush=True)
        if review.returncode:
            print("Visual review unavailable; raw run results will still publish.", flush=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Visual review pending: {type(exc).__name__}; raw results preserved.", flush=True)
    (REPO / "index.html").write_text(build_index(records), encoding="utf-8")
    (REPO / "history.html").write_text(build_history(records), encoding="utf-8")
    ok_n = sum(1 for r in results if r["status"] == "ok")
    git("add", "-A")
    commit = git("commit", "-m",
                 f"round {round_id}: {ok_n}/{len(results)} SVG ok\n\n"
                 f"Built-By: Codex (per-model, see stats.json) via run_round.py on songyy-pi\n"
                 f"Verified-By: Alberto (Muse Wonder)")
    if commit.returncode != 0:
        print("commit failed:", commit.stdout, commit.stderr, flush=True)
    if not sync_publication():
        return 1
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
