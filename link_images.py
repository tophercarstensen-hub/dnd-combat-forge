"""
Flatten all book images into Combat Calc/monster_art/ (content-hash dedup),
then match MD files to monsters/spells by name and write imagePath fields.

Output:
  Combat Calc/monster_art/<sha1>.<ext>       — flat, deduplicated image pool
  monsters_final.json (in place)             — adds imagePath field
  spells_final.json (in place)               — adds imagePath field
  link_images_report.json                    — matched + unmatched counts
"""

import hashlib
import json
import re
import shutil
from collections import defaultdict
from difflib import SequenceMatcher
from html import unescape
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).parent                                 # Combat Calc/
ROLL20 = HERE.parent / "roll20-export"                       # sibling dir
BOOKS_DIR = ROLL20 / "books"
ART_DIR = HERE / "monster_art"
MONSTERS_PATH = HERE / "monsters_final.json"
SPELLS_PATH = HERE / "spells_final.json"
REPORT_PATH = HERE / "link_images_report.json"

# Prefer official / WotC books when the same monster exists in multiple sources
BOOK_PRIORITY = [
    "Monster Manual (2024)",
    "Monster Manual",
    "Dungeon Master's Guide (2024)",
    "Player's Handbook (2024)",
    "Free Basic Rules (2024)",
    "Mordenkainen Presents - Monsters of the Multiverse",
    "Mordenkainen's Tome of Foes",
    "Volo's Guide to Monsters",
    "Fizban's Treasury of Dragons",
    "Monster Manual Expanded",    # 3rd-party expansion
    "Tome of Beasts",
    "Tome of Beasts 2",
    "Tome of Beasts 3",
    "Creature Codex",
]
# Anything not listed -> lowest priority; alphabetical among those


def priority(book_name: str) -> int:
    try:
        return BOOK_PRIORITY.index(book_name)
    except ValueError:
        return len(BOOK_PRIORITY) + 100  # low priority


def normalize_name(s: str) -> str:
    s = unescape(s or "")
    s = s.replace("'", "'").replace("'", "'")
    s = re.sub(r"\s+", " ", s).strip().lower()
    # drop parenthetical suffixes for matching (but keep the original elsewhere)
    return s


# ---------- Step 1: flatten + dedupe images ----------

def flatten_images() -> dict:
    """Copy every _images/<url-hash>.png into monster_art/<content-hash>.ext.
    Returns {old_relative_path: new_flat_filename} mapping."""
    ART_DIR.mkdir(exist_ok=True)
    mapping = {}  # e.g. "Monster Manual/_images/abc123.png" -> "deadbeef.png"

    total_copied = 0
    total_dedupe = 0
    for book_dir in BOOKS_DIR.iterdir():
        images_dir = book_dir / "_images"
        if not images_dir.exists():
            continue
        for img in images_dir.iterdir():
            if not img.is_file():
                continue
            try:
                content = img.read_bytes()
            except OSError:
                continue
            h = hashlib.sha1(content).hexdigest()[:12]
            ext = img.suffix.lower() or ".png"
            dst = ART_DIR / f"{h}{ext}"
            rel = str(img.relative_to(BOOKS_DIR)).replace("\\", "/")
            mapping[rel] = dst.name
            if not dst.exists():
                dst.write_bytes(content)
                total_copied += 1
            else:
                total_dedupe += 1
    print(f"Flatten complete: {total_copied} new, {total_dedupe} dedupes, "
          f"{len(list(ART_DIR.iterdir()))} total in {ART_DIR.name}/")
    return mapping


# ---------- Step 2: build name -> image index from MD files ----------

MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


def build_name_image_index(flat_map: dict) -> dict:
    """Walk every MD file. For each, extract title + first image. Return
    {normalized_title: [{"book": ..., "flat_name": ..., "priority": int}]}"""
    idx = defaultdict(list)
    for md in BOOKS_DIR.rglob("*.md"):
        if md.name.startswith("_"):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        # title = first "# X" line
        tm = re.match(r"#\s+(.+?)\s*$", text, re.M)
        if not tm:
            continue
        title = unescape(tm.group(1).strip())
        # first image after title
        im = MD_IMG_RE.search(text)
        if not im:
            continue
        img_rel = im.group(1)  # either _images/xyz.png OR https://... (leftover)
        if not img_rel.startswith("_images/"):
            continue
        # derive flat filename via mapping
        book_dir = md.relative_to(BOOKS_DIR).parts[0]
        old_rel = f"{book_dir}/{img_rel}"
        flat = flat_map.get(old_rel)
        if not flat:
            # Windows backslash variant
            flat = flat_map.get(old_rel.replace("/", "\\"))
        if not flat:
            continue
        key = normalize_name(title)
        idx[key].append({
            "book": book_dir,
            "flat_name": flat,
            "priority": priority(book_dir),
            "md_path": str(md.relative_to(BOOKS_DIR)),
        })
    # sort each list by priority (best first)
    for k in idx:
        idx[k].sort(key=lambda e: e["priority"])
    print(f"Built name index: {len(idx)} unique titles")
    return idx


# ---------- Step 3: match data records to images ----------

# Adjective prefixes that commonly describe monster variants which share art
# with their base form. Used as a fallback when strict matching fails.
_VARIANT_PREFIXES = (
    "armored", "ancient", "young", "adult", "greater", "elder", "legendary",
    "mythic", "enraged", "bloodied", "corrupted", "alpha", "champion",
    "spectral", "skeletal", "zombie", "undead", "fiendish", "shadow",
    "giant", "dire", "feral", "tough", "elite", "reinforced", "awakened",
)
_VARIANT_SUFFIXES = (
    "(2024)", "(legacy)", "(deprecated)", "(variant)", "(2014)",
)


def _candidate_keys(name: str) -> list[str]:
    """Generate alternate normalized forms of a name for fuzzy matching."""
    n = normalize_name(name)
    out = [n]
    # strip known suffixes
    for s in _VARIANT_SUFFIXES:
        if n.endswith(s):
            out.append(n[: -len(s)].strip())
    # strip known variant prefixes ("armored ogre" -> "ogre")
    parts = n.split()
    if len(parts) > 1 and parts[0] in _VARIANT_PREFIXES:
        out.append(" ".join(parts[1:]))
    # drop parenthetical "foo (barovian)" -> "foo"
    if "(" in n:
        out.append(re.sub(r"\s*\([^)]*\)\s*", "", n).strip())
    # drop possessive/sub-name after comma ("Strahd, Master of X" -> "Strahd")
    if "," in n:
        out.append(n.split(",", 1)[0].strip())
    return [x for x in out if x]


def match_records(records: list, idx: dict, name_key: str = "name") -> tuple[int, int]:
    matched = unmatched = 0
    for r in records:
        keys = _candidate_keys(r.get(name_key, ""))
        entries = None
        # 1. exact lookup on any candidate key
        for k in keys:
            if k in idx:
                entries = idx[k]
                break
        # 2. fuzzy fallback on primary key
        if not entries and keys:
            primary = keys[0]
            best_ratio = 0.0
            best_entries = None
            for idx_name, lst in idx.items():
                ratio = SequenceMatcher(None, primary, idx_name).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_entries = lst
            if best_ratio >= 0.85:
                entries = best_entries
        if entries:
            r["imagePath"] = entries[0]["flat_name"]
            matched += 1
        else:
            r["imagePath"] = None
            unmatched += 1
    return matched, unmatched


def main():
    print("Step 1: flatten images...")
    flat_map = flatten_images()

    print("\nStep 2: build MD name -> image index...")
    idx = build_name_image_index(flat_map)

    print("\nStep 3: match monsters...")
    monsters = json.loads(MONSTERS_PATH.read_text(encoding="utf-8"))
    m_matched, m_unmatched = match_records(monsters, idx)
    MONSTERS_PATH.write_text(json.dumps(monsters, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Monsters: {m_matched} matched, {m_unmatched} unmatched "
          f"({100*m_matched/max(1,len(monsters)):.1f}% coverage)")

    print("\nStep 4: match spells...")
    spells = json.loads(SPELLS_PATH.read_text(encoding="utf-8"))
    s_matched, s_unmatched = match_records(spells, idx)
    SPELLS_PATH.write_text(json.dumps(spells, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Spells:   {s_matched} matched, {s_unmatched} unmatched "
          f"({100*s_matched/max(1,len(spells)):.1f}% coverage)")

    report = {
        "monsters": {"total": len(monsters), "matched": m_matched, "unmatched": m_unmatched},
        "spells":   {"total": len(spells),   "matched": s_matched, "unmatched": s_unmatched},
        "flat_images": len(list(ART_DIR.iterdir())),
        "sample_unmatched_monsters": [
            m["name"] for m in monsters if m.get("imagePath") is None
        ][:30],
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport saved: {REPORT_PATH.name}")


if __name__ == "__main__":
    main()
