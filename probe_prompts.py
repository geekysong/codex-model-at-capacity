"""Shared benchmark prompts and visible per-request timestamps."""
import hashlib
from daily_prompt import load_daily_prompt, SGT

PELICAN_PROMPT = 'Draw a satirical cartoon as ONE single self-contained SVG document (viewBox="0 0 800 600"). Theme: a pelican riding a bicycle. Make it funny and visually expressive, with a clear single scene, readable characters, and a bold title plus a short caption about the pelican on the bicycle. Make it an actual looping SVG animation using embedded SMIL or CSS animation: animate the bicycle wheels and a small pedaling or bobbing motion while keeping text readable. Output ONLY the SVG code: no markdown fences, no explanation, no text outside the document.'
ACTIVE_VARIANTS = ("pelican", "daily")

def load_prompt(variant):
    daily, date, digest = load_daily_prompt()
    if variant == "daily":
        return daily, date, digest
    if variant == "pelican":
        return PELICAN_PROMPT, date, hashlib.sha256(PELICAN_PROMPT.encode()).hexdigest()[:12]
    raise ValueError(f"Unknown benchmark: {variant}")

def timestamped_prompt(prompt, started):
    timestamp = started.astimezone(SGT).isoformat(timespec="microseconds")
    label = started.astimezone(SGT).strftime("%Y-%m-%d %H:%M:%S SGT (UTC+08:00)")
    return timestamp, (
        f"Request timestamp: {timestamp}\n"
        f'Include this exact visible date/time label in the SVG: "{label}". '
        "Use readable <text> inside the viewBox, in a footer with enough space; "
        "do not overlap the scene or other labels. It must be visible, not only a comment or metadata.\n\n"
        + prompt
    )
