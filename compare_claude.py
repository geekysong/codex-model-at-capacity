#!/usr/bin/env python3
"""Run the same low-risk SVG probe through Anthropic's official Messages API.

The API key is read from .secrets/anthropic_api_key (or ANTHROPIC_API_KEY).
The key is never printed, persisted in output, or committed. Results are kept
under comparisons/<timestamp>/ so they can be compared with a Codex round.
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from daily_prompt import load_daily_prompt

REPO = Path(__file__).resolve().parent
KEY_FILE = REPO / ".secrets" / "anthropic_api_key"
API_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "1000000"))
SGT = ZoneInfo("Asia/Singapore")
# USD per million standard input/output tokens. Keep this table versioned with
# the run so historical estimates remain explainable when provider prices change.
PRICE_USD_PER_MTOK = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0),
}

PROMPTS = {
"pelican": (
    "Draw a satirical cartoon as ONE single self-contained SVG document "
    '(viewBox="0 0 800 600"). Theme: a pelican riding a bicycle. Make it funny '
    "and visually expressive, with a clear single scene, readable characters, and "
    "a bold title plus a short caption about the pelican on the bicycle. Make it an "
    "actual looping SVG animation using embedded SMIL or CSS animation: animate the "
    "bicycle wheels and a small pedaling or bobbing motion while keeping text readable. "
    "Output ONLY the SVG code: no markdown fences, no explanation, no text outside the document. "
    "Keep the SVG compact (under 2500 tokens)."
),
"substitution": (
    "Draw a satirical cartoon as ONE single self-contained SVG document "
    '(viewBox="0 0 800 600"). Theme: a service promises a premium model but quietly '
    "substitutes a cheap weak model. Show the bait-and-switch clearly and humorously, "
    "with a bold title and short caption. Output ONLY the SVG code: no markdown fences, "
    "no explanation, no text outside the <svg>...</svg> document. Keep the SVG compact."
),
"physics": (
    "Create one self-contained SVG with viewBox=\"0 0 600 400\" showing a level "
    "seesaw in static equilibrium. A 6 kg mass hangs 2 m left of the pivot, and a "
    "4 kg mass hangs x m right. Solve and show x=3 m. Draw the pivot, force arrows, "
    "distance labels, torque equation 6×2 = 4×3, and the word balanced. Make it an "
    "actual looping SVG animation using embedded SMIL or CSS animation: keep the "
    "seesaw level while gently pulsing the force arrows or weights to visualize balance. "
    "Keep labels readable, and output only the SVG."
),
}
PROMPT, PROMPT_DATE, PROMPT_SHA = load_daily_prompt()
PROMPT_VARIANT = "daily"


def read_key() -> str:
    value = os.environ.get("ANTHROPIC_API_KEY")
    if value:
        return value.strip()
    if not KEY_FILE.exists():
        raise RuntimeError(f"secret file not found: {KEY_FILE}")
    value = KEY_FILE.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"secret file is empty: {KEY_FILE}")
    return value


def main() -> int:
    try:
        key = read_key()
    except RuntimeError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    started = datetime.now(SGT)
    t0 = time.monotonic()
    body = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": PROMPT}],
    }).encode("utf-8")
    request = Request(API_URL, data=body, method="POST", headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    try:
        with urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"Anthropic API returned HTTP {exc.code}; response not saved", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Anthropic API request failed: {exc.reason}", file=sys.stderr)
        return 1
    except TimeoutError:
        print("Anthropic API request timed out", file=sys.stderr)
        return 1

    text = "\n".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text")
    match = re.search(r"<svg[\s\S]*?</svg>", text)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    model_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", MODEL)
    out_dir = REPO / "comparisons" / stamp / PROMPT_VARIANT / model_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "provider": "anthropic",
        "variant": PROMPT_VARIANT,
        "prompt_date": PROMPT_DATE,
        "prompt_sha": PROMPT_SHA,
        "model": result.get("model", MODEL),
        "time_sgt": started.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(time.monotonic() - t0, 2),
        "input_tokens": (result.get("usage") or {}).get("input_tokens"),
        "output_tokens": (result.get("usage") or {}).get("output_tokens"),
        "stop_reason": result.get("stop_reason"),
        "status": "ok" if match else "error",
        "error": None if match else "response did not contain an SVG",
    }
    input_price, output_price = PRICE_USD_PER_MTOK.get(MODEL, (None, None))
    if input_price is not None and metadata["input_tokens"] is not None and metadata["output_tokens"] is not None:
        metadata["price_usd_per_million"] = {"input": input_price, "output": output_price}
        metadata["estimated_cost_usd"] = round(
            metadata["input_tokens"] * input_price / 1_000_000
            + metadata["output_tokens"] * output_price / 1_000_000, 6
        )
    else:
        metadata["price_usd_per_million"] = None
        metadata["estimated_cost_usd"] = None
    (out_dir / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not match:
        print("Claude response did not contain an SVG; metadata saved", file=sys.stderr)
        return 1
    svg = match.group(0)
    if "xmlns" not in svg.split(">", 1)[0]:
        svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    (out_dir / "claude.svg").write_text(svg, encoding="utf-8")
    print(f"saved comparisons/{stamp}/claude.svg ({metadata['duration_s']}s, model={metadata['model']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
