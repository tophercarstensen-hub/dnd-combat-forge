#!/usr/bin/env python3
"""
Download monster art for the ToB/ToB2/ToB3 monsters ingested by
build_kobold_press_from_homebrew.py, and set their imagePath field.

Source: the same 5etools homebrew JSON files already vendored at
data/kobold-press-homebrew/ (tome-of-beasts-{1,2,3}.json), each of which
carries real GitHub-hosted webp art per monster under either an inline
`fluff.images[0].href.url` or a top-level `monsterFluff[].images` entry.

Downloads, resizes to the same 512px/quality-80 webp policy as
compress_art.py, content-hash-dedupes into monster_art/ alongside the
existing art pool, and writes imagePath onto the matching records in
monsters_final.json.

Usage:
    python link_kobold_press_art.py            # do it
    python link_kobold_press_art.py --dry-run  # just report match counts
"""

import argparse
import hashlib
import io
import json
import sys
import urllib.request
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
HOMEBREW_DIR = ROOT / "data" / "kobold-press-homebrew"
ART_DIR = ROOT / "monster_art"
MONSTERS_FILE = ROOT / "monsters_final.json"

SOURCE_FILES = {
    "ToB": HOMEBREW_DIR / "tome-of-beasts-1.json",
    "ToB2": HOMEBREW_DIR / "tome-of-beasts-2.json",
    "ToB3": HOMEBREW_DIR / "tome-of-beasts-3.json",
}

MAX_DIM = 512
QUALITY = 80
WORKERS = 12


def build_url_map(fpath, source_code):
    """{(name_lower, SOURCE): image_url} for one homebrew file."""
    data = json.loads(fpath.read_text(encoding="utf-8"))
    url_map = {}

    # Top-level monsterFluff entries carrying their own images
    for entry in data.get("monsterFluff", []):
        imgs = entry.get("images")
        if imgs:
            key = (entry.get("name", "").lower(), entry.get("source", source_code).upper())
            url = imgs[0].get("href", {}).get("url")
            if url:
                url_map[key] = url

    # Inline per-monster fluff.images (covers monsters not in monsterFluff)
    for m in data.get("monster", []):
        key = (m.get("name", "").lower(), source_code.upper())
        if key in url_map:
            continue
        fluff = m.get("fluff")
        if isinstance(fluff, dict):
            imgs = fluff.get("images")
            if imgs:
                url = imgs[0].get("href", {}).get("url")
                if url:
                    url_map[key] = url

    return url_map


def fetch_and_process(name, source, url):
    """Download one image, resize/recompress to webp, save content-hash-named.
    Returns (name, source, filename) or (name, source, None) on failure."""
    # Some homebrew entries (esp. ToB3's monsterFluff images) store the path
    # with raw spaces instead of %20 — quote the path before requesting.
    parts = urlsplit(url)
    safe_url = urlunsplit((parts.scheme, parts.netloc, quote(unquote(parts.path)), parts.query, parts.fragment))
    try:
        req = urllib.request.Request(safe_url, headers={"User-Agent": "combat-forge-art-linker"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except Exception as e:
        return (name, source, None, f"download failed: {e}")

    h = hashlib.sha1(raw).hexdigest()[:12]
    dst = ART_DIR / f"{h}.webp"
    if dst.exists() and dst.stat().st_size > 0:
        return (name, source, dst.name, None)

    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.mode in ("P", "LA"):
                im = im.convert("RGBA")
            elif im.mode == "CMYK":
                im = im.convert("RGB")
            im.thumbnail((MAX_DIM, MAX_DIM), Image.Resampling.LANCZOS)
            im.save(dst, "WEBP", quality=QUALITY, method=4)
    except Exception as e:
        return (name, source, None, f"process failed: {e}")

    return (name, source, dst.name, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=" * 60)
    print("Kobold Press art linking (ToB/ToB2/ToB3)")
    print("=" * 60)

    print("\nBuilding image URL index from homebrew source files...")
    url_map = {}
    for source_code, fpath in SOURCE_FILES.items():
        m = build_url_map(fpath, source_code)
        print(f"  {source_code}: {len(m)} monsters with art URLs")
        url_map.update(m)
    print(f"  Total: {len(url_map)}")

    print(f"\nLoading {MONSTERS_FILE}...")
    monsters = json.loads(MONSTERS_FILE.read_text(encoding="utf-8"))

    targets = []
    for m in monsters:
        if m.get("source") not in SOURCE_FILES:
            continue
        if m.get("imagePath"):
            continue
        key = (m.get("name", "").lower(), m.get("source", "").upper())
        url = url_map.get(key)
        if url:
            targets.append((m, url))

    print(f"  {len(targets)} KP monsters matched to an art URL and need imagePath set")

    if args.dry_run:
        print("\n[Dry run — no downloads, no file written]")
        return 0

    ART_DIR.mkdir(exist_ok=True)
    print(f"\nDownloading + compressing {len(targets)} images with {WORKERS} workers...")

    ok = 0
    failed = 0
    fail_samples = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {
            ex.submit(fetch_and_process, m["name"], m["source"], url): m
            for m, url in targets
        }
        for i, fut in enumerate(as_completed(futures), 1):
            m = futures[fut]
            name, source, filename, err = fut.result()
            if filename:
                m["imagePath"] = filename
                ok += 1
            else:
                failed += 1
                if len(fail_samples) < 10:
                    fail_samples.append(f"{name} ({source}): {err}")
            if i % 200 == 0:
                print(f"  [{i}/{len(targets)}] ok={ok} failed={failed}")

    print(f"\nDone. ok={ok} failed={failed}")
    if fail_samples:
        print("Sample failures:")
        for s in fail_samples:
            print(f"  {s}")

    MONSTERS_FILE.write_text(json.dumps(monsters, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {MONSTERS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
