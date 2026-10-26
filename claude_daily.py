"""Shared artifact identity and bounded lock helpers (no provider calls)."""
import fcntl
import json
import time
from contextlib import contextmanager
from pathlib import Path
import xml.etree.ElementTree as ET


def valid_svg(path):
    try:
        return ET.parse(path).getroot().tag in ('svg', '{http://www.w3.org/2000/svg}svg')
    except (OSError, ET.ParseError):
        return False


def matching_artifacts(repo, variant, model, day, sha):
    found = []
    for path in sorted((repo / 'comparisons').glob('*/*/*/meta.json')):
        try:
            meta = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (meta.get('provider') == 'anthropic' and meta.get('variant') == variant
                and meta.get('requested_model', meta.get('model')) == model
                and meta.get('prompt_date') == day and meta.get('prompt_sha') == sha
                and meta.get('status') == 'ok' and valid_svg(path.with_name('claude.svg'))):
            found.append(path.with_name('claude.svg'))
    return found


@contextmanager
def bounded_lock(path, timeout):
    with open(path, 'a') as handle:
        deadline = time.monotonic() + timeout
        announced = False
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not announced:
                    print(f'waiting for {Path(path).name}; deadline {timeout}s', flush=True)
                    announced = True
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'{Path(path).name} busy after {timeout}s; no model calls made')
                time.sleep(min(1, max(0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)
