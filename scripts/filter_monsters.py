"""
Clean up monsters_final.json:
  1. Drop community/indie sources that aren't available on Roll20
  2. Re-classify `sourceType` using 5etools' books.json + adventures.json as
     ground truth (fixes ~1,400 WotC books currently mislabeled as third-party)

Writes a backup to monsters_final.pre-filter.json before overwriting.

    python scripts/filter_monsters.py

Flags:
    --etools PATH   5etools-src-main root (default: C:/Users/tophe/Downloads/5etools-src-main/5etools-src-main)
    --dry-run       print stats without writing
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ETOOLS = Path(r"C:\Users\tophe\Downloads\5etools-src-main\5etools-src-main")

# Sources to remove (small indie / Reddit / DMsGuild community).
# Compared against a normalized source string (see norm_source below).
PURGE_SOURCES = {
    "Monster-A-Day",
    "Critter Compendium",
    "Monsters of the Guild",
    "Nerzugal's Dungeon Master Toolkit 2",
    "Nerzugal's Extended Bestiary",
    "Primeval Thule Campaign Setting",
    "Primeval Thule Gamemaster's Companion",
    "Monster Module",
}

# Malformed source strings that should be dropped individually (not normalizable).
PURGE_EXACT = {
    "Tome of Beasts: 320, Tome of Beasts: 424",
}

# WotC supplements that aren't in 5etools' books.json/adventures.json index
# (small digital/promotional releases). Supplements the 5etools index — all
# matched case-insensitively.
KNOWN_OFFICIAL = {
    "SADS",   # Sapphire Anniversary Dice & Miscellany Starter Set
    "VD",     # Vecna Dossier
    "SLW",    # Storm Lord's Wrath
    "SDW",    # Sleeping Dragon's Wake
    "DC",     # Divine Contention
    "HftT",   # Hunt for the Thessalhydra
    "TTP",    # The Tortle Package
    "OGA",    # One Grung Above
    "PS-A", "PS-D", "PS-I", "PS-K", "PS-X", "PS-Z",  # Plane Shift series
    "RMBRE",  # The Lost Dungeon of Rickedness: Big Rick Energy
    "NRH-AT", "NRH-AWoL", "NRH-ASS", "NRH-CoI", "NRH-TLT",
    "NRH-TCMC", "NRH-AVitW",  # NERDs Restoring Harmony one-shots
    "HAT-LMI", "HAT-TG",  # Heroes of Adventure Team
    "MCV1SC", "MCV2DC", "MCV3MC", "MCV4EC",  # Monstrous Compendium Volume
    "MisMV1",  # Mistrys of Morrasskis...
    "AATM",    # Adventure Atlas: The Mortuary
    "GotSF",   # Giants of the Star Forge (or similar)
}


def norm_source(s: str) -> str:
    """Strip trailing `: <page>` or `: https://...` suffixes from source strings."""
    s = (s or "").strip()
    if ":" in s:
        after = s.split(":", 1)[1].strip()
        if after.isdigit() or after.startswith("http"):
            return s.split(":", 1)[0].strip()
    return s


def load_official_sources(etools_root: Path) -> dict:
    """Build {source_code_lowercase: canonical_code} from 5etools books + adventures."""
    official = {}
    for fname in ("books.json", "adventures.json"):
        p = etools_root / "data" / fname
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for key in d:
            for entry in d[key]:
                code = entry.get("id") or entry.get("source")
                if code:
                    official[code.lower()] = code
    return official


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--etools", type=Path, default=DEFAULT_ETOOLS,
                    help="path to 5etools-src-main root")
    ap.add_argument("--dry-run", action="store_true",
                    help="print stats without writing")
    args = ap.parse_args()

    final_path = ROOT_DIR / "monsters_final.json"
    backup_path = ROOT_DIR / "monsters_final.pre-filter.json"

    print(f"loading {final_path.name}...")
    monsters = json.loads(final_path.read_text(encoding="utf-8"))
    print(f"  {len(monsters):,} monsters before filter")

    official_map = load_official_sources(args.etools)
    if not official_map:
        sys.exit(
            f"error: could not load 5etools data from {args.etools}. "
            "Pass --etools PATH or verify the folder exists."
        )
    # Merge in small supplements not present in the 5etools index.
    for code in KNOWN_OFFICIAL:
        official_map.setdefault(code.lower(), code)
    print(f"  {len(official_map):,} official source codes (5etools index + overrides)")

    purged = 0
    reclassified_to_official = 0
    reclassified_to_thirdparty = 0
    kept = []

    for m in monsters:
        raw_src = m.get("source", "")
        src = norm_source(raw_src)

        if src in PURGE_SOURCES or raw_src in PURGE_EXACT:
            purged += 1
            continue

        old_type = m.get("sourceType")
        new_type = "official" if src.lower() in official_map else "third-party"
        if new_type != old_type:
            if new_type == "official":
                reclassified_to_official += 1
            else:
                reclassified_to_thirdparty += 1
            m["sourceType"] = new_type

        kept.append(m)

    print(f"\nresult:")
    print(f"  purged:                       {purged:>6}")
    print(f"  reclassified -> official:     {reclassified_to_official:>6}")
    print(f"  reclassified -> third-party:  {reclassified_to_thirdparty:>6}")
    print(f"  kept:                         {len(kept):>6}")

    official_count = sum(1 for m in kept if m.get("sourceType") == "official")
    print(f"\nfinal breakdown:")
    print(f"  official:    {official_count:>6}")
    print(f"  third-party: {len(kept) - official_count:>6}")

    if args.dry_run:
        print("\n(dry run — no files written)")
        return

    if not backup_path.exists():
        shutil.copy2(final_path, backup_path)
        print(f"\nbackup written: {backup_path.name}")
    else:
        print(f"\nbackup already exists: {backup_path.name} (not overwritten)")

    final_path.write_text(
        json.dumps(kept, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"wrote: {final_path.name}  ({len(kept):,} monsters)")


if __name__ == "__main__":
    main()
