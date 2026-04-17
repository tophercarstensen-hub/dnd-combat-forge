"""
extract_prose_bonus_actions.py

Scans monsters_final.json for monsters whose traits or actions contain
prose descriptions of bonus actions but have no structured bonusActions
array.  Extracts structured entries and writes them back to the JSON.

Usage:
    python scripts/extract_prose_bonus_actions.py
    python scripts/extract_prose_bonus_actions.py --dry-run
    python scripts/extract_prose_bonus_actions.py --in path/to/monsters.json --out path/to/out.json

Strategy (conservative):
    TRAITS  — The trait exists specifically to describe a bonus-action ability.
              Strong signals: "As a bonus action, ...", "can use a bonus action to ...",
              "can take the X action as a bonus action", "can take a bonus action to ...".
              Filtered by a broad incidental-reference list.

    ACTIONS — Much stricter.  Only extract when the action entry ITSELF IS the
              bonus action (i.e. the action is labelled/described as being used as
              a bonus action by the creature), NOT when the action merely *grants* or
              *mentions* a bonus action as a side-effect or exit condition.
              Required pattern: the desc starts with "As a bonus action" or the
              action is explicitly described as a bonus-action use in the first clause.
"""

import argparse
import json
import re
from pathlib import Path
from collections import Counter

# ---------------------------------------------------------------------------
# Shared: WHOLE-ABILITY signal for TRAITS
# The trait entry IS the bonus action ability.
# ---------------------------------------------------------------------------
TRAIT_WHOLE_RE = re.compile(
    r"""
    (?:
        \bAs\s+a\s+bonus\s+action\b                                     # "As a bonus action, ..."
      | \bcan\s+(?:use|take)\s+a\s+bonus\s+action\s+to\b               # "can use/take a bonus action to ..."
      | \bcan\s+take\s+the\s+(?:\w+\s+)*action\s+as\s+a\s+bonus\s+action\b  # "can take the Hide action as a bonus action"
      | \bcan\s+take\s+a\s+bonus\s+action\s+to\b                       # "can take a bonus action to ..."
      | \bbonus\s+action\s+to\s+(?:make|attack|cast|use|take|move|teleport|hide|dash|disengage|draw)\b
      | \busing\s+a\s+bonus\s+action\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Shared: INCIDENTAL references in TRAITS — these are NOT whole-ability signals.
# The bonus action is mentioned as a side-effect or exit condition.
# ---------------------------------------------------------------------------
TRAIT_INCIDENTAL_RE = re.compile(
    r"""
    (?:
        (?:revert|return|end|dismiss|cancel|drop|emerge)\s+
            (?:(?:to|from)\s+\w+\s+)?(?:form|shape|effect|it)?\s+as\s+a\s+bonus\s+action
      | (?:revert|return)\s+to\s+(?:its?|her|his|their)\s+(?:true\s+)?form.*bonus\s+action
      | can\s+revert.*as\s+a\s+bonus\s+action
      | bonus\s+action\s+to\s+(?:become|remain|stay)\s+(?:visible|invisible|incorporeal)
      | bonus\s+action\s+to\s+end\s+it
      | (?:casting\s+time|it\s+becomes)\s+(?:\w+\s+)?bonus\s+action     # Echo Spell style
      | until\s+\w+\s+(?:uses?|takes?)\s+a\s+bonus\s+action\s+to\s+end
      | while\s+the\s+spell\s+is\s+ongoing.*bonus\s+action              # Illusory Reality style
      | (?:he|she|it|they)\s+can\s+do\s+this.*as\s+a\s+bonus\s+action
      | takes?\s+a\s+bonus\s+action\s+to\s+end\s+it
      | bonus\s+action\s+on\s+(?:its?|her|his|their)\s+turn\s*\.?$     # trailing fragment
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ---------------------------------------------------------------------------
# ACTION source: strict pattern — desc must open with "As a bonus action"
# (or equivalent lead phrase) meaning the WHOLE ACTION IS the bonus action.
# Any bonus-action mention that is a rider/side-effect is rejected.
# ---------------------------------------------------------------------------
ACTION_LEAD_RE = re.compile(
    r"""
    (?:
        ^As\s+a\s+bonus\s+action\b      # desc literally opens with it
    )
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

# Actions where the bonus action is a rider/exit/side-effect — always skip
ACTION_INCIDENTAL_RE = re.compile(
    r"""
    (?:
        (?:revert|return|end|dismiss|cancel|drop|emerge|leaves?)\s+
            (?:(?:to|from|as)\s+\w+\s+)?(?:form|shape|effect|it)?\s+as\s+a\s+bonus\s+action
      | can\s+revert.*as\s+a\s+bonus\s+action
      | the\s+ghost\s+ends?\s+it\s+as\s+a\s+bonus\s+action
      | (?:the\s+\w+\s+)?ends?\s+(?:the\s+possession|it)\s+as\s+a\s+bonus\s+action
      | can\s+use\s+(?:its?|her|his|the)\s+(?:\w+\s+)?(?:attack|slam|strike)\s+as\s+a\s+bonus\s+action
      | use\s+its?\s+\w+\s+attack\s+as\s+a\s+bonus\s+action
      | make\s+one\s+(?:\w+\s+)*attack\s+as\s+a\s+bonus\s+action     # Battle Cry rider
      | can\s+use\s+a\s+bonus\s+action\s+to\s+swim                   # Moonshark
      | can\s+detach\s+itself\s+as\s+a\s+bonus\s+action              # Space Eel
      | can\s+mentally\s+command\s+it\s+as\s+a\s+bonus\s+action      # Solar Flying Sword
      | use\s+the\s+(?:Dash|Hide|Disengage)\s+action\s+as\s+a\s+bonus\s+action  # Ink Cloud rider
      | until\s+(?:it|he|she|they)\s+emerges?\s+as\s+a\s+bonus\s+action  # Shell Defense
      | as\s+a\s+bonus\s+action\s+on\s+(?:its?|her|his|their)\s+turn
      | (?:using\s+a\s+bonus\s+action\s+on\s+(?:its?|her|his|their)\s+turn)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Damage formula extraction
# ---------------------------------------------------------------------------
DMG_FORMULA_RE = re.compile(
    r"\d+\s*\(\s*\d+d\d+(?:\s*[+\-]\s*\d+)?\s*\)"  # 7 (2d6) or 7 (2d6 + 3)
    r"|\d+d\d+(?:\s*[+\-]\s*\d+)?"                   # bare: 2d6+3
)

# ---------------------------------------------------------------------------
# Category classifiers
# ---------------------------------------------------------------------------
ATTACK_RE = re.compile(
    r"\bto\s+hit\b|\bweapon\s+attack\b|\bmelee\s+attack\b|\branged\s+attack\b"
    r"|\bmake\s+(?:one|an?)\s+(?:\w+\s+)*attack\b",
    re.IGNORECASE,
)
AOE_RE = re.compile(
    r"\bsaving\s+throw\b|\bDC\s+\d+\b|\beach\s+creature\b"
    r"|\barea\s+of\s+effect\b|\bcone\b|\bline\b|\bradius\b|\bemanation\b",
    re.IGNORECASE,
)
CONTROL_RE = re.compile(
    r"\bcharmed\b|\bfrightened\b|\bstunned\b|\bparalyzed\b|\brestrained\b"
    r"|\bincapacitated\b|\bblinded\b|\bpoisoned\b|\bprone\b"
    r"|\bcan't\s+(?:move|speak|attack)\b",
    re.IGNORECASE,
)
HEAL_RE = re.compile(
    r"\bregain[s]?\s+\d+.*hit\s+point\b|\bheal\b|\brestores?\s+\d+\b",
    re.IGNORECASE,
)
UTILITY_RE = re.compile(
    r"\bteleport\b|\bhide\b|\bdisengage\b|\bdash\b|\binvisib\b"
    r"|\bwild\s+shape\b|\bshape[\-\s]?shift\b",
    re.IGNORECASE,
)


def classify(desc: str) -> str:
    if ATTACK_RE.search(desc) and DMG_FORMULA_RE.search(desc):
        return "attack"
    if AOE_RE.search(desc) and DMG_FORMULA_RE.search(desc):
        return "aoe"
    if CONTROL_RE.search(desc):
        return "control"
    if HEAL_RE.search(desc):
        return "healing"
    if UTILITY_RE.search(desc):
        return "utility"
    return "unknown"


def extract_damage(desc: str) -> str | None:
    m = DMG_FORMULA_RE.search(desc)
    return m.group(0).strip() if m else None


# ---------------------------------------------------------------------------
# Name derivation (strips recharge/frequency annotations)
# ---------------------------------------------------------------------------
def derive_name(entry_name: str) -> str:
    clean = re.sub(r"\s*\(.*?\)\s*$", "", entry_name).strip()
    return clean if clean else "Bonus Action"


# ---------------------------------------------------------------------------
# Is a TRAIT entry a whole bonus-action ability?
# ---------------------------------------------------------------------------
def trait_is_bonus_action(desc: str) -> bool:
    if not TRAIT_WHOLE_RE.search(desc):
        return False
    # If the incidental pattern fires BEFORE (or at) the whole-ability pattern, skip.
    whole_m = TRAIT_WHOLE_RE.search(desc)
    incid_m = TRAIT_INCIDENTAL_RE.search(desc)
    if incid_m and incid_m.start() <= whole_m.start():
        return False
    return True


# ---------------------------------------------------------------------------
# Is an ACTION entry itself a bonus action?
# Strict: the description must open with "As a bonus action" AND must not
# contain the action-incidental patterns.
# ---------------------------------------------------------------------------
def action_is_bonus_action(desc: str) -> bool:
    if not ACTION_LEAD_RE.search(desc):
        return False
    if ACTION_INCIDENTAL_RE.search(desc):
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Extract prose-embedded bonus actions from monsters_final.json"
    )
    parser.add_argument("--in", dest="input", default=None)
    parser.add_argument("--out", dest="output", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    default_json = repo_root / "monsters_final.json"

    in_path = Path(args.input) if args.input else default_json
    out_path = Path(args.output) if args.output else in_path

    print(f"Reading: {in_path}")
    with open(in_path, "r", encoding="utf-8") as f:
        monsters = json.load(f)
    print(f"Loaded {len(monsters)} monsters")

    updated_list = list(monsters)
    stats: Counter = Counter()
    categories: Counter = Counter()
    detail_rows: list[dict] = []

    for idx, m in enumerate(monsters):
        has_bonus = bool(m.get("bonusActions") or m.get("bonus_actions"))
        if has_bonus:
            stats["already_structured"] += 1
            continue

        extracted: list[dict] = []

        # --- Traits (broader ruleset) ---
        for entry in (m.get("traits") or []):
            desc = entry.get("desc", "")
            if desc and trait_is_bonus_action(desc):
                ba_name = derive_name(entry.get("name", ""))
                cat = classify(desc)
                dmg = extract_damage(desc) if cat in ("attack", "aoe") else None
                extracted.append({
                    "name": ba_name,
                    "desc": desc,
                    "_src": "trait",
                    "_cat": cat,
                    "_dmg": dmg,
                })
                stats["extracted_from_trait"] += 1
                categories[cat] += 1

        # --- Actions (strict: desc must open with "As a bonus action") ---
        for entry in (m.get("actions") or []):
            desc = entry.get("desc", "")
            if desc and action_is_bonus_action(desc):
                ba_name = derive_name(entry.get("name", ""))
                cat = classify(desc)
                dmg = extract_damage(desc) if cat in ("attack", "aoe") else None
                extracted.append({
                    "name": ba_name,
                    "desc": desc,
                    "_src": "action",
                    "_cat": cat,
                    "_dmg": dmg,
                })
                stats["extracted_from_action"] += 1
                categories[cat] += 1

        if extracted:
            clean_entries = [{"name": e["name"], "desc": e["desc"]} for e in extracted]
            updated = dict(m)
            updated["bonusActions"] = clean_entries
            updated_list[idx] = updated
            stats["monsters_updated"] += 1
            for e in extracted:
                detail_rows.append({
                    "monster": m["name"],
                    "source": e["_src"],
                    "ba_name": e["name"],
                    "category": e["_cat"],
                    "damage": e["_dmg"],
                })

    # ---- Summary ----
    print()
    print("=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"Monsters already had bonusActions:  {stats['already_structured']}")
    print(f"Monsters updated:                   {stats['monsters_updated']}")
    print(f"  Entries from traits:              {stats['extracted_from_trait']}")
    print(f"  Entries from actions:             {stats['extracted_from_action']}")
    print()
    print("Category breakdown:")
    for cat in ("attack", "aoe", "control", "healing", "utility", "unknown"):
        print(f"  {cat:<12} {categories[cat]}")
    print()
    print("All changed monsters:")
    for row in detail_rows:
        dmg_str = f"  dmg={row['damage']}" if row["damage"] else ""
        print(f"  [{row['category']:8}] {row['monster']} -> \"{row['ba_name']}\"{dmg_str}")

    if args.dry_run:
        print()
        print("DRY RUN — no files written.")
        return

    print()
    print(f"Writing: {out_path}")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(updated_list, f, ensure_ascii=False, separators=(",", ":"))
    print("Done.")


if __name__ == "__main__":
    main()
