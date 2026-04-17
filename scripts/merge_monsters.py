#!/usr/bin/env python3
"""
merge_monsters.py
=================
Merges monsters_all_enriched_v2.json (5etools base) with third-party monsters
from monsters_all_enriched.json (old Kobold Plus file).

Usage:
    python merge_monsters.py

Reads:
    monsters_all_enriched_v2.json   — your clean 5etools build (same folder)
    monsters_all_enriched.json      — old enriched file with Kobold monsters (same folder)

Writes:
    monsters_final.json             — merged output (same folder)
"""

import json
import re
import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).resolve().parent.parent
DATA_DIR     = ROOT_DIR / "data"
V2_FILE      = DATA_DIR / "monsters_all_enriched_v2.json"
OLD_FILE     = DATA_DIR / "monsters_all_enriched.json"
OUTPUT_FILE  = ROOT_DIR / "monsters_final.json"

# ── Source classification (same as build script) ──────────────────────────────
OFFICIAL_SOURCES = {
    "MM","PHB","DMG","VGM","MTF","XGE","TCE","MOT","FTD","BMT","BAM",
    "VRGR","SCC","IDRotF","WDH","WDMM","GGR","EGW","AI","OGA","IMR",
    "HftT","DSotDQ","KftGV","PAbtSO","SatO","ToFW","VEoR","XMM","XPHB",
    "XDMG","QftIS","MisMV","SLW","SD","ToA","PotA","SKT","CoS","LMoP",
    "TftYP","Rot","HotDQ","WBtW","RMBre","NF","OoW","OotA",
    "GoS","DC","BGDIA","EET","RMBRE","HAT-LMI","HAT-TG","RTG","SADS",
    "SDW","NRH-AT","NRH-AWOL","NRH-ASS","NRH-CoI","NRH-TLT",
    "NRH-TCMC","NRH-AVitW","MPP","VEOR","VD","TTP","TOFW","ROT",
    "PS-A","PS-D","PS-I","PS-K","PS-X","PS-Z","SLWCTG"
}
COMMUNITY_SOURCES = {
    "UA","UAClassFeatureVariants","PSA","PSI","PSK",
    "PSX","PSZ","PSD","STREAM","TWITTER","UARC",
    # Planeshift series (Magic the Gathering crossovers)
    "PS-A","PS-D","PS-I","PS-K","PS-X","PS-Z"
}

def get_source_type(source):
    s = source.upper()
    if s in OFFICIAL_SOURCES:
        return "official"
    if s in COMMUNITY_SOURCES:
        return "community"
    return "third-party"


# ── Attack parsing from plain text desc ──────────────────────────────────────
hit_re      = re.compile(r'([+-]\d+) to hit', re.IGNORECASE)
dmg_re      = re.compile(r'Hit:.*?(\d+d\d+(?:\s*[+-]\s*\d+)?)', re.IGNORECASE)
# Iterate every dice expression in a desc (for riders like "plus 1d6 fire")
all_dice_re = re.compile(r'(\d+d\d+(?:\s*[+-]\s*\d+)?)')
dc_re       = re.compile(r'DC\s*(\d+)', re.IGNORECASE)
num_atk_re  = re.compile(r'makes?\s+(\w+)\s+(?:\w+\s+)?(?:attack|Attack)', re.IGNORECASE)
NUM_WORDS   = {"one":1,"two":2,"three":3,"four":4,"five":5,
               "six":6,"seven":7,"eight":8,"nine":9,"ten":10}


def _classify_damage_connector(text):
    """Given text between two dice expressions, decide versatile vs rider."""
    t = text.lower()
    if re.search(r'\bor\b[^.]{0,80}(if\s+used|two[- ]?hand|versatile|wielded)', t):
        return "versatile"
    if re.search(r'\bor\b', t) and not re.search(r'\b(plus|and)\b', t):
        return "versatile"
    return "rider"


def _resolve_hit_damage(desc):
    """Find the "Hit:" clause in a plain-text action desc and return a compound
    dice formula combining riders (but skipping versatile alternates). Returns
    None if no Hit clause with damage is present."""
    # Scope to text from "Hit:" up to the next sentence that starts an unrelated
    # clause (hitting another action header or end of string).
    hit_start = re.search(r'\bHit:\s*', desc, re.IGNORECASE)
    if not hit_start:
        return None
    # Stop the scan at the next "Action", ". " followed by capitalized verb, or EoS
    segment = desc[hit_start.end():]
    # Cut off at obvious sentence break following the last damage clause
    stop = re.search(r'\.\s+(?=[A-Z][a-z]+\s+(?:the|it|target|creature))', segment)
    if stop:
        segment = segment[:stop.start() + 1]
    matches = list(all_dice_re.finditer(segment))
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0].group(1).replace(" ", "")
    kept = [matches[0].group(1).replace(" ", "")]
    for i in range(1, len(matches)):
        connector = segment[matches[i - 1].end(): matches[i].start()]
        if _classify_damage_connector(connector) == "rider":
            kept.append(matches[i].group(1).replace(" ", ""))
    return " + ".join(kept)

def _avg_dice(expr):
    expr = expr.strip().replace(" ", "")
    total = 0
    for part in re.split(r'(?=[+-])', expr):
        part = part.strip()
        if not part:
            continue
        sign = 1
        if part[0] == '-':
            sign = -1
            part = part[1:]
        elif part[0] == '+':
            part = part[1:]
        if 'd' in part.lower():
            nd, ds = re.split(r'd', part.lower(), maxsplit=1)
            try:
                nd = int(nd) if nd else 1
                ds = int(re.sub(r'\D.*', '', ds))
                total += sign * nd * (ds + 1) / 2
            except ValueError:
                pass
        else:
            try:
                total += sign * float(part)
            except ValueError:
                pass
    return total

def parse_attack_from_actions(actions):
    """Parse atkBonus, numAtks, dmgPerAtk from plain text action descs."""
    result = {
        "atkBonus": None,
        "numAtks": 1,
        "dmgPerAtk": None,
        "saveDC": None,
        "multiattack": False,
    }
    best_dmg = -1

    for action in (actions or []):
        if not isinstance(action, dict):
            continue
        name = action.get("name", "").lower()
        desc = action.get("desc", "") or ""

        if "multiattack" in name:
            result["multiattack"] = True
            m2 = num_atk_re.search(desc)
            if m2:
                word = m2.group(1).lower()
                result["numAtks"] = NUM_WORDS.get(word, result["numAtks"])
            continue

        hit_m = hit_re.search(desc)
        resolved_dmg = _resolve_hit_damage(desc)
        dc_m  = dc_re.search(desc)

        if hit_m and resolved_dmg:
            try:
                dmg_val = _avg_dice(resolved_dmg)
            except Exception:
                dmg_val = 0
            if dmg_val > best_dmg:
                best_dmg = dmg_val
                result["atkBonus"] = int(hit_m.group(1))
                result["dmgPerAtk"] = resolved_dmg
        elif dc_m and resolved_dmg and result["saveDC"] is None:
            result["saveDC"] = int(dc_m.group(1))

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Monster File Merge")
    print("=" * 60)

    # Load v2 (5etools base)
    print(f"\nLoading {V2_FILE.name}...")
    with open(V2_FILE, encoding="utf-8") as f:
        v2_monsters = json.load(f)
    print(f"  {len(v2_monsters):,} monsters loaded")

    # Clean v2: drop community, no-CR, no-AC, normalize HP
    v2_clean = []
    v2_dropped = 0
    for m in v2_monsters:
        source_type = get_source_type(m.get("source",""))
        if source_type == "community":
            v2_dropped += 1
            continue
        if m.get("cr") is None:
            v2_dropped += 1
            continue
        if m.get("ac") is None:
            v2_dropped += 1
            continue
        # Normalize HP
        hp = m.get("hp")
        if isinstance(hp, int):
            m["hp"] = {"average": hp, "formula": ""}
        elif isinstance(hp, dict) and hp.get("average") is None:
            v2_dropped += 1
            continue
        v2_clean.append(m)
    print(f"  Dropped {v2_dropped} (community/no-CR/no-AC) from v2")
    v2_monsters = v2_clean

    # Build lookup of what's already in v2 by name+source
    v2_keys = set()
    for m in v2_monsters:
        key = (m["name"].lower(), m.get("source","").upper())
        v2_keys.add(key)
    print(f"  {len(v2_keys):,} unique name+source keys in v2")

    # Load old file
    print(f"\nLoading {OLD_FILE.name}...")
    with open(OLD_FILE, encoding="utf-8") as f:
        old_monsters = json.load(f)
    print(f"  {len(old_monsters):,} monsters loaded")

    # Filter old file: keep only true third-party, skip official and community
    third_party_new = []
    skipped_official = 0
    skipped_community = 0
    skipped_duplicate = 0

    for m in old_monsters:
        source = m.get("source", "")
        source_upper = source.upper()
        source_type = get_source_type(source)

        # Drop community/homebrew
        if source_type == "community":
            skipped_community += 1
            continue

        # Drop official — v2 already has better versions
        if source_type == "official":
            skipped_official += 1
            continue

        # Drop duplicates already in v2
        key = (m["name"].lower(), source_upper)
        if key in v2_keys:
            skipped_duplicate += 1
            continue

        # Drop monsters with no CR or no AC — unusable in sim
        if m.get("cr") is None or m.get("ac") is None:
            skipped_duplicate += 1  # reuse counter, rename below
            continue

        # Normalize HP int → dict
        hp = m.get("hp")
        if isinstance(hp, int):
            m["hp"] = {"average": hp, "formula": ""}
        elif not isinstance(hp, dict) or hp.get("average") is None:
            continue

        third_party_new.append(m)

    print(f"\n  Skipped official (v2 has better): {skipped_official:,}")
    print(f"  Skipped community/homebrew:        {skipped_community:,}")
    print(f"  Skipped duplicates already in v2:  {skipped_duplicate:,}")
    print(f"  Third-party to merge in:           {len(third_party_new):,}")

    # Enrich third-party monsters with missing fields
    print(f"\nEnriching third-party monsters...")
    enriched = 0
    for m in third_party_new:
        source = m.get("source", "")

        # Set sourceType
        m["sourceType"] = "third-party"

        # Generate slug
        if not m.get("slug"):
            slug = re.sub(r'[^a-z0-9]+', '-', m["name"].lower()).strip('-')
            m["slug"] = f"{slug}-{source.lower()}" if source else slug

        # Parse atkBonus/dmgPerAtk from action desc text if missing
        if m.get("atkBonus") is None and m.get("actions"):
            parsed = parse_attack_from_actions(m["actions"])
            if parsed["atkBonus"] is not None:
                m["atkBonus"] = parsed["atkBonus"]
                enriched += 1
            if m.get("dmgPerAtk") is None and parsed["dmgPerAtk"] is not None:
                m["dmgPerAtk"] = parsed["dmgPerAtk"]
            if m.get("numAtks", 1) == 1:
                m["numAtks"] = parsed["numAtks"]
            if m.get("saveDC") is None and parsed["saveDC"] is not None:
                m["saveDC"] = parsed["saveDC"]
            if not m.get("multiattack"):
                m["multiattack"] = parsed["multiattack"]

        # Ensure all expected fields exist
        for field, default in [
            ("dmgTypes", []), ("saveAbility", None), ("aoeType", None),
            ("aoeDmg", None), ("bonusActions", []), ("reactions", []),
            ("mythicActions", []), ("spellcasting", []), ("vulnerabilities", []),
            ("conditionImmunities", []), ("resistances", []), ("immunities", []),
        ]:
            if field not in m:
                m[field] = default

    print(f"  Parsed atkBonus for {enriched:,} third-party monsters")

    # Merge
    final = v2_monsters + third_party_new
    print(f"\nFinal monster count: {len(final):,}")

    # Stats
    has_atk     = sum(1 for m in final if m.get("atkBonus") is not None)
    has_env     = sum(1 for m in final if m.get("environment"))
    has_lore    = sum(1 for m in final if m.get("lore"))
    official    = sum(1 for m in final if m.get("sourceType") == "official")
    third       = sum(1 for m in final if m.get("sourceType") == "third-party")
    community   = sum(1 for m in final if m.get("sourceType") == "community")

    print(f"\nData quality:")
    print(f"  Has atkBonus:    {has_atk}/{len(final)} ({has_atk*100//len(final)}%)")
    print(f"  Has environment: {has_env}/{len(final)} ({has_env*100//len(final)}%)")
    print(f"  Has lore:        {has_lore}/{len(final)} ({has_lore*100//len(final)}%)")
    print(f"\nSource breakdown:")
    print(f"  Official:        {official:,}")
    print(f"  Third-party:     {third:,}")
    print(f"  Community:       {community:,}")

    # Write
    print(f"\nWriting {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final, f, separators=(",", ":"), ensure_ascii=False)
    size_mb = OUTPUT_FILE.stat().st_size / 1024 / 1024
    print(f"Done! {OUTPUT_FILE.name} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    main()
