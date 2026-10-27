"""Deterministic, no-model validation for the active Daily Challenge SVG."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

PRIME_SQUARE_MARKERS = re.compile(
    r"4x4.*prime.*perfect\s+square|prime.*perfect\s+square.*4x4",
    re.IGNORECASE | re.DOTALL,
)
EXPECTED_CELLS = {
    1: "orange", 2: "blue", 3: "blue", 4: "orange",
    5: "blue", 6: "white", 7: "blue", 8: "white",
    9: "orange", 10: "white", 11: "blue", 12: "white",
    13: "blue", 14: "white", 15: "white", 16: "orange",
}


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _color(value: str | None) -> str:
    value = (value or "").strip().lower()
    named = {"blue": "blue", "orange": "orange", "white": "white"}
    if value in named:
        return named[value]
    if value == "none":
        return "none"
    if value.startswith("rgb"):
        nums = [int(x) for x in re.findall(r"\d+", value)[:3]]
        if len(nums) == 3:
            r, g, b = nums
            return _rgb_color(r, g, b)
    if value.startswith("#"):
        raw = value[1:]
        if len(raw) == 3:
            raw = "".join(ch * 2 for ch in raw)
        if len(raw) == 6 and all(ch in "0123456789abcdef" for ch in raw):
            return _rgb_color(int(raw[:2], 16), int(raw[2:4], 16), int(raw[4:], 16))
    return value or "unknown"


def _rgb_color(r: int, g: int, b: int) -> str:
    if min(r, g, b) >= 220:
        return "white"
    if b > r * 1.15 and b > g * 1.05:
        return "blue"
    if r >= 150 and g >= 80 and g < r and b < g * 0.8:
        return "orange"
    return "unknown"


def _svg_cells(root: ET.Element) -> dict[int, str]:
    cells: dict[int, str] = {}

    def walk(node: ET.Element, inherited_fill: str | None = None) -> None:
        fill = node.attrib.get("fill", inherited_fill)
        if node.tag.endswith("rect") and node.attrib.get("x") and node.attrib.get("y"):
            try:
                x = int(float(node.attrib["x"]))
                y = int(float(node.attrib["y"]))
                width = int(float(node.attrib.get("width", "0")))
                height = int(float(node.attrib.get("height", "0")))
            except ValueError:
                x = y = width = height = -1
            if (120 <= x <= 300 and 60 <= y <= 240 and
                    (x - 120) % 60 == 0 and (y - 60) % 60 == 0 and
                    width == 60 and height == 60):
                number = ((y - 60) // 60) * 4 + ((x - 120) // 60) + 1
                cells[number] = _color(fill)
        for child in node:
            walk(child, fill)

    walk(root)
    return cells


def validate_daily_artifact(
    path: Path,
    record: dict,
    expected_date: str,
    expected_sha: str,
    prompt: str,
) -> str | None:
    """Return a bounded error string, or None when the artifact is acceptable.

    Pelican and other non-daily variants are intentionally ignored. For future
    Daily prompts whose semantics are not recognized here, identity/date checks
    still apply while the model-specific semantic check is skipped.
    """
    if record.get("variant") != "daily":
        return None
    errors: list[str] = []
    if record.get("prompt_date") != expected_date:
        errors.append(f"prompt_date={record.get('prompt_date')!r}, expected {expected_date!r}")
    if record.get("prompt_sha") != expected_sha:
        errors.append(f"prompt_sha={record.get('prompt_sha')!r}, expected {expected_sha!r}")
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return f"invalid SVG: {type(exc).__name__}"
    texts = [_normalize_text("".join(node.itertext())) for node in root.iter() if node.tag.endswith("text")]
    joined = " ".join(texts)
    if expected_date not in joined:
        errors.append(f"visible date label missing {expected_date}")
    if not PRIME_SQUARE_MARKERS.search(prompt):
        return "; ".join(errors) or None

    cells = _svg_cells(root)
    if set(cells) != set(EXPECTED_CELLS):
        missing = sorted(set(EXPECTED_CELLS) - set(cells))
        extra = sorted(set(cells) - set(EXPECTED_CELLS))
        errors.append(f"grid cells missing={missing} extra={extra}")
    else:
        mismatches = [f"{n}: expected {want}, got {cells[n]}"
                      for n, want in EXPECTED_CELLS.items() if cells[n] != want]
        if mismatches:
            errors.append("cell colors " + ", ".join(mismatches))

    labels = [text for text in texts if re.fullmatch(r"(?:1[0-6]|[1-9])", text)]
    expected_labels = [str(n) for n in range(1, 17)]
    if sorted(labels, key=int) != expected_labels:
        errors.append(f"cell labels expected 1-16 exactly once, got {labels}")

    blue = re.search(r"blue.*?prime.*?:\s*(\d+)", joined, re.IGNORECASE)
    orange = re.search(r"orange.*?square.*?:\s*(\d+)", joined, re.IGNORECASE)
    if not blue or int(blue.group(1)) != 6:
        errors.append("declared blue-prime count is not 6")
    if not orange or int(orange.group(1)) != 4:
        errors.append("declared orange-square count is not 4")
    return "; ".join(errors) or None
