#!/usr/bin/env python3
"""
Replace the Kobold-Fight-Club-sourced Tome of Beasts 1/2/3 monsters in
monsters_final.json with clean records built from the real 5etools
homebrew data (TheGiddyLimit/homebrew on GitHub — the same corpus
Plutonium/5etools serve).

Why: the existing KFC-derived ToB/ToB2/ToB3 monsters have their `source`
field polluted with a literal page number (e.g. "Tome of Beasts 2: 188"
instead of "ToB2"), which breaks the app's source-filter grouping/badges
for ~1,261 of ~1,447 Kobold Press monsters. The homebrew files use the
exact same schema as official 5etools bestiary JSON, so this script
reuses build_monsters_enriched.py's parsing (build_monster/resolve_copy)
unchanged and just points it at a different input.

Usage:
    python build_kobold_press_from_homebrew.py           # writes monsters_final.json (backs up first)
    python build_kobold_press_from_homebrew.py --dry-run # stats only, no write
"""

import argparse
import json
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_monsters_enriched as bme  # reuse build_monster / resolve_copy / strip_entries

ROOT = Path(__file__).resolve().parent.parent
HOMEBREW_DIR = ROOT / "data" / "kobold-press-homebrew"
MONSTERS_FILE = ROOT / "monsters_final.json"

# (input file, canonical source code) — original ToB1 printing kept (not
# the 2023 revision) to match the source code the DB's few pre-existing
# clean KP-ToB entries already used.
SOURCE_FILES = [
    (HOMEBREW_DIR / "tome-of-beasts-1.json", "ToB"),
    (HOMEBREW_DIR / "tome-of-beasts-2.json", "ToB2"),
    (HOMEBREW_DIR / "tome-of-beasts-3.json", "ToB3"),
]

# Anything with a source matching these is an old KFC-derived Kobold
# Press monster to be replaced. The polluted form is "Tome of Beasts[ N]: <page>".
import re
POLLUTED_SOURCE_RE = re.compile(r'^Tome of Beasts.*:\s*\d+$')
OLD_CLEAN_SOURCES = {"KP-ToB", "KP-ToB2", "KP-ToB3"}


def is_old_kfc_kp_source(source):
    if not source:
        return False
    if source in OLD_CLEAN_SOURCES:
        return True
    return bool(POLLUTED_SOURCE_RE.match(source))


def load_fluff_map(data, source_code):
    """Build {(name_lower, SOURCE): lore_text} from a homebrew file.

    Two patterns seen in the wild:
      - top-level `monsterFluff` array (name/source/entries) — same shape
        official 5etools fluff-bestiary-*.json files use.
      - per-monster inline `fluff.entries` (no top-level monsterFluff, or
        monsterFluff entries that don't cover every monster).
    """
    fluff_map = {}
    for entry in data.get("monsterFluff", []):
        name = entry.get("name", "")
        src = entry.get("source", source_code)
        text = bme.strip_entries(entry.get("entries", [])).strip()
        if text:
            fluff_map[(name.lower(), src.upper())] = text

    for m in data.get("monster", []):
        key = (m.get("name", "").lower(), m.get("source", source_code).upper())
        if key in fluff_map:
            continue
        inline = m.get("fluff")
        if isinstance(inline, dict) and inline.get("entries"):
            text = bme.strip_entries(inline["entries"]).strip()
            if text:
                fluff_map[key] = text
    return fluff_map


def build_kp_monsters():
    """Load all SOURCE_FILES, resolve _copy chains, and build combat-calc
    schema records for every monster, tagged with the canonical source."""
    all_raw = []
    all_by_key = {}
    fluff_map = {}

    for fpath, source_code in SOURCE_FILES:
        if not fpath.exists():
            print(f"  WARNING: missing {fpath}, skipping")
            continue
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        monsters = data.get("monster", [])
        print(f"  {fpath.name}: {len(monsters)} monsters (source={source_code})")
        for m in monsters:
            # Force the canonical clean source code — some files' raw
            # `source` already matches (ToB2/ToB3), ToB1's raw source is
            # also "ToB" already, but set explicitly so this is robust
            # even if a future homebrew update changes it.
            m["source"] = source_code
            key = (m.get("name", "").lower(), source_code.upper())
            all_by_key[key] = m
            all_raw.append(m)
        fluff_map.update(load_fluff_map(data, source_code))

    print(f"\n  Total raw KP monsters: {len(all_raw)}")
    print(f"  Fluff entries loaded: {len(fluff_map)}")

    output = []
    errors = 0
    for m_raw in all_raw:
        try:
            resolved = bme.resolve_copy(m_raw, all_by_key)
            built = bme.build_monster(resolved, fluff_map, old_env_map={})
            if built["name"]:
                output.append(built)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error on {m_raw.get('name','?')}: {e}")

    print(f"  Built: {len(output)}  (errors: {errors})")
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=" * 60)
    print("Kobold Press (Tome of Beasts 1/2/3) ingestion from 5etools homebrew")
    print("=" * 60)

    print("\nBuilding replacement monster records...")
    new_kp = build_kp_monsters()

    by_source = {}
    for m in new_kp:
        by_source[m["source"]] = by_source.get(m["source"], 0) + 1
    print("\nNew records by source:")
    for src, n in sorted(by_source.items()):
        print(f"  {src}: {n}")

    print(f"\nLoading {MONSTERS_FILE}...")
    with open(MONSTERS_FILE, encoding="utf-8") as f:
        current = json.load(f)
    print(f"  Current monster count: {len(current)}")

    old_kp = [m for m in current if is_old_kfc_kp_source(m.get("source"))]
    kept = [m for m in current if not is_old_kfc_kp_source(m.get("source"))]
    print(f"  Old KFC-derived Kobold Press monsters to remove: {len(old_kp)}")
    print(f"  Remaining after removal: {len(kept)}")

    merged = kept + new_kp
    print(f"\nFinal monster count: {len(merged)}  (was {len(current)}, net {len(merged)-len(current):+d})")

    if args.dry_run:
        print("\n[Dry run — no file written]")
        return 0

    backup = MONSTERS_FILE.with_suffix(".json.bak-kp-homebrew")
    if not backup.exists():
        shutil.copy2(MONSTERS_FILE, backup)
        print(f"\nBacked up original to: {backup}")

    with open(MONSTERS_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"Wrote: {MONSTERS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
