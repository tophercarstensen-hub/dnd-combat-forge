"""
Enrich shell monster records (missing actions/traits/legendary actions) using
the Open5e API.

Targets monsters where `legendaryActions` is a positive int but no legendary
action list exists. Open5e has good coverage of Tome of Beasts 1/2/3 and the
2023 revised edition; less for other third-party books.

    python scripts/enrich_from_open5e.py --dry-run
    python scripts/enrich_from_open5e.py

Writes a backup to monsters_final.pre-enrich.json before overwriting.

Flags:
    --dry-run         report what would change without writing
    --limit N         process only first N broken monsters (for testing)
    --delay SECONDS   pause between API calls (default 0.15)
"""

import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
API_BASE = "https://api.open5e.com/v2/creatures/"

# Preference order when multiple Open5e records match a name.
# Lower index = higher preference.
DOC_PRIORITY = ["tob-2023", "tob", "tob2", "tob3", "ccdx", "kp", "toh"]


def has_list_legendary(m: dict) -> bool:
    la = m.get("legendaryActions")
    if isinstance(la, list) and la:
        return True
    if isinstance(m.get("legendary_actions"), list) and m["legendary_actions"]:
        return True
    return False


def open5e_lookup(name: str, timeout: int = 15):
    """Return best-matching Open5e creature record, or None."""
    params = urllib.parse.urlencode({"name__iexact": name})
    url = f"{API_BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "combat-forge-enricher"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return None, f"http error: {e}"
    results = data.get("results") or []
    if not results:
        return None, "no match"
    # Rank by document preference; fall back to first result.
    def rank(rec):
        doc = (rec.get("document") or {}).get("key", "")
        try:
            return DOC_PRIORITY.index(doc)
        except ValueError:
            return len(DOC_PRIORITY) + 1
    results.sort(key=rank)
    return results[0], None


def convert_actions(o5_actions: list) -> dict:
    """Split Open5e's unified actions array into our schema buckets."""
    buckets = {
        "actions": [],
        "bonusActions": [],
        "reactions": [],
        "legendaryActions": [],
        "mythicActions": [],
    }
    for a in o5_actions or []:
        kind = (a.get("action_type") or "ACTION").upper()
        name = a.get("name") or ""
        desc = a.get("desc") or ""
        cost = a.get("legendary_action_cost")
        if kind == "LEGENDARY_ACTION":
            # Prepend cost note to name if > 1 (matches common stat-block style).
            if cost and cost > 1:
                name = f"{name} (Costs {cost} Actions)"
            buckets["legendaryActions"].append({"name": name, "desc": desc})
        elif kind == "BONUS_ACTION":
            buckets["bonusActions"].append({"name": name, "desc": desc})
        elif kind == "REACTION":
            buckets["reactions"].append({"name": name, "desc": desc})
        elif kind == "MYTHIC_ACTION":
            buckets["mythicActions"].append({"name": name, "desc": desc})
        else:
            buckets["actions"].append({"name": name, "desc": desc})
    return buckets


def convert_traits(o5_traits: list) -> list:
    return [{"name": t.get("name", ""), "desc": t.get("desc", "")}
            for t in (o5_traits or []) if t.get("name")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="0 = no limit")
    ap.add_argument("--delay", type=float, default=0.15)
    args = ap.parse_args()

    final_path = ROOT_DIR / "monsters_final.json"
    backup_path = ROOT_DIR / "monsters_final.pre-enrich.json"

    monsters = json.loads(final_path.read_text(encoding="utf-8"))
    print(f"loaded {len(monsters):,} monsters")

    broken_idx = [i for i, m in enumerate(monsters)
                  if isinstance(m.get("legendaryActions"), int)
                  and m["legendaryActions"] > 0
                  and not has_list_legendary(m)]
    if args.limit:
        broken_idx = broken_idx[:args.limit]
    print(f"targeting {len(broken_idx)} broken-legendary records\n")

    hits = 0
    misses = 0
    errors = 0
    skipped_already_populated = 0

    for n, idx in enumerate(broken_idx, 1):
        m = monsters[idx]
        name = m["name"]
        rec, err = open5e_lookup(name)
        time.sleep(args.delay)

        if err and err != "no match":
            errors += 1
            print(f"[{n}/{len(broken_idx)}] {name} -- ERROR: {err}")
            continue
        if rec is None:
            misses += 1
            print(f"[{n}/{len(broken_idx)}] {name} -- no match")
            continue

        doc_key = (rec.get("document") or {}).get("key", "?")
        buckets = convert_actions(rec.get("actions") or [])
        new_traits = convert_traits(rec.get("traits") or [])

        # Only fill empty buckets — don't overwrite existing data.
        filled = []
        for key, new_items in buckets.items():
            if not new_items:
                continue
            existing = m.get(key)
            if isinstance(existing, list) and existing:
                continue  # already has data, leave alone
            if key == "legendaryActions":
                # Dual-typed: int count exists; replace with list form.
                m[key] = new_items
                filled.append(f"leg:{len(new_items)}")
            else:
                m[key] = new_items
                filled.append(f"{key[:3]}:{len(new_items)}")
        if new_traits and not (isinstance(m.get("traits"), list) and m["traits"]):
            m["traits"] = new_traits
            filled.append(f"traits:{len(new_traits)}")

        if not filled:
            skipped_already_populated += 1
            print(f"[{n}/{len(broken_idx)}] {name} -- match [{doc_key}] but nothing to fill")
            continue

        hits += 1
        print(f"[{n}/{len(broken_idx)}] {name} -- [{doc_key}] filled {' '.join(filled)}")

    print(f"\nsummary: {hits} enriched | {misses} no match | {errors} errors | {skipped_already_populated} already populated")

    if args.dry_run:
        print("\n(dry run -- no files written)")
        return

    if hits == 0:
        print("\nnothing to write.")
        return

    if not backup_path.exists():
        shutil.copy2(final_path, backup_path)
        print(f"\nbackup: {backup_path.name}")
    else:
        print(f"\nbackup already exists: {backup_path.name} (not overwritten)")

    final_path.write_text(
        json.dumps(monsters, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"wrote: {final_path.name}")


if __name__ == "__main__":
    main()
