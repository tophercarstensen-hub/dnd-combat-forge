"""
Parse healing-related monster features and add enriched fields for the sim.

Adds:
  regenPerTurn         — HP regained at start of each turn (0 if none)
  regenNegatedBy       — list of damage types that stop regen (e.g. ["fire","acid"])
  bonusActionHeal      — self-heal from bonus actions (0 if none)
  isHealer             — monster knows at least one healing spell (bool)
  healerHealPerRound   — avg HP healed per cast (int)
  healerSpellName      — name of the best healing spell available

Usage:
  ./../roll20-export/venv/Scripts/python.exe enrich_healing.py
"""

import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).parent
IN_PATH = HERE / "monsters_final.json"
BACKUP = HERE / "monsters_final.pre-healing-enrich.json"
SPELLS_PATH = HERE / "spells_final.json"


# ---- Regex patterns ----

REGEN_RE = re.compile(
    r"regains?\s+(\d+)\s+Hit Points?|\bregeneration\b.*?(\d+)\s*Hit Points?",
    re.I | re.S,
)
# e.g. "If the troll takes acid or fire damage, this trait doesn't function..."
NEGATE_RE = re.compile(
    r"(?:takes?|deal(?:s|t))\s+([a-z ,\-or]+)\s+damage[^.]*"
    r"(?:trait doesn't function|this feature doesn't work|regeneration (?:is )?suppressed|"
    r"regeneration (?:is )?disabled|can't regenerate|prevents? this trait)",
    re.I,
)
DAMAGE_TYPES = ["fire", "acid", "cold", "lightning", "thunder", "poison",
                "necrotic", "radiant", "psychic", "force"]

BA_HEAL_RE = re.compile(
    r"regains?\s+(\d+)\s+Hit Points?",
    re.I,
)

HEAL_SPELL_NAMES = {
    "cure wounds", "healing word", "mass cure wounds", "mass healing word",
    "heal", "prayer of healing", "aura of vitality", "vampiric touch",
    "life transference", "power word heal", "regenerate",
}


def find_start_of_turn_regen(trait_desc: str) -> int:
    """Return the regen amount if trait is a 'start of turn' regeneration."""
    # must mention 'start of' turn AND 'regains X Hit Points'
    if not re.search(r"start of (?:its|the) (?:next )?turn", trait_desc, re.I):
        return 0
    m = REGEN_RE.search(trait_desc)
    if m:
        amt = m.group(1) or m.group(2)
        try:
            return int(amt)
        except (TypeError, ValueError):
            return 0
    return 0


def find_regen_negations(trait_desc: str) -> list:
    """Return list of damage types that negate regen (e.g. ['fire','acid'])."""
    m = NEGATE_RE.search(trait_desc)
    if not m:
        return []
    text = m.group(1).lower()
    out = [t for t in DAMAGE_TYPES if t in text]
    return out


def parse_regen(m: dict) -> tuple[int, list]:
    """Look through traits for regeneration. Return (regen_per_turn, negated_by)."""
    for trait in m.get("traits") or []:
        if not isinstance(trait, dict):
            continue
        name = (trait.get("name") or "").lower()
        desc = trait.get("desc") or ""
        # Fast check: trait name contains "regen" or desc matches
        if "regen" not in name and not re.search(r"regains?\s+\d+\s+Hit Points?", desc, re.I):
            continue
        amt = find_start_of_turn_regen(desc)
        if amt:
            return amt, find_regen_negations(desc)
    return 0, []


def parse_ba_heal(m: dict) -> int:
    """Look through bonus actions for self-heal. Return amount or 0."""
    for a in m.get("bonusActions") or []:
        if not isinstance(a, dict):
            continue
        desc = a.get("desc") or ""
        # Must be a SELF heal; skip abilities that heal allies
        if not re.search(r"\b(?:it|the (?:creature|monster|\w+))\s+regains?\s+\d+", desc, re.I):
            # more lenient: any "regains N Hit Points" on the action
            m2 = BA_HEAL_RE.search(desc)
            if m2:
                return int(m2.group(1))
            continue
        m2 = BA_HEAL_RE.search(desc)
        if m2:
            return int(m2.group(1))
    return 0


def build_spell_heal_index():
    """Load SPELL_DB and return {slug_or_name_lower: spell} for quick lookup."""
    if not SPELLS_PATH.exists():
        return {}
    spells = json.loads(SPELLS_PATH.read_text(encoding="utf-8"))
    out = {}
    for s in spells:
        nm = (s.get("name") or "").lower().strip()
        if nm:
            out[nm] = s
    return out


def parse_healer(m: dict, spell_idx: dict) -> tuple[bool, int, str]:
    """If the monster knows a healing spell, return (True, avg_heal, name)."""
    best = (0, "")
    for sc in m.get("spellcasting") or []:
        if not isinstance(sc, dict):
            continue
        desc = sc.get("desc") or ""
        # Match any spell name from HEAL_SPELL_NAMES present in the desc
        for nm in HEAL_SPELL_NAMES:
            if re.search(rf"\b{re.escape(nm)}\b", desc, re.I):
                spell = spell_idx.get(nm)
                if spell:
                    # Use avgDamage as proxy for heal amount (healing spells put
                    # their average in avgDamage with isHealing=True)
                    heal = int(spell.get("avgDamage") or 0)
                    # Some healing spells have avgDamage=0 in data; fall back to
                    # a reasonable baseline by spell level
                    if heal == 0:
                        level = spell.get("level") or 1
                        heal = {0: 0, 1: 9, 2: 14, 3: 18, 4: 23, 5: 27, 6: 32,
                                7: 36, 8: 41, 9: 45}.get(level, 15)
                    if heal > best[0]:
                        best = (heal, nm.title())
    if best[0] > 0:
        return True, best[0], best[1]
    return False, 0, ""


def main():
    if not BACKUP.exists():
        shutil.copy2(IN_PATH, BACKUP)
        print(f"Backup: {BACKUP.name}")

    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    spell_idx = build_spell_heal_index()
    print(f"Loaded {len(data)} monsters, {len(spell_idx)} spells in index")

    regen_count = ba_heal_count = healer_count = 0
    for m in data:
        regen, negated = parse_regen(m)
        m["regenPerTurn"] = regen
        m["regenNegatedBy"] = negated
        if regen > 0: regen_count += 1

        ba_heal = parse_ba_heal(m)
        m["bonusActionHeal"] = ba_heal
        if ba_heal > 0: ba_heal_count += 1

        is_healer, heal_amt, heal_name = parse_healer(m, spell_idx)
        m["isHealer"] = is_healer
        m["healerHealPerRound"] = heal_amt
        m["healerSpellName"] = heal_name
        if is_healer: healer_count += 1

    IN_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {IN_PATH.name}")

    print(f"\n=== Healing enrichment summary ===")
    print(f"  Natural regen:          {regen_count} monsters")
    print(f"  Bonus action self-heal: {ba_heal_count} monsters")
    print(f"  Healer spell casters:   {healer_count} monsters")

    # Show top regen samples
    regens = sorted(
        (m for m in data if m.get("regenPerTurn", 0) > 0),
        key=lambda x: -x["regenPerTurn"],
    )
    print(f"\n  Top regen monsters:")
    for m in regens[:10]:
        neg = ", ".join(m["regenNegatedBy"]) if m["regenNegatedBy"] else "(none)"
        print(f"    +{m['regenPerTurn']:3}/rd  {m['name']!r} (CR {m['cr']})  "
              f"negated by: {neg}")

    healers = sorted(
        (m for m in data if m.get("isHealer")),
        key=lambda x: -x["healerHealPerRound"],
    )
    print(f"\n  Top healers:")
    for m in healers[:10]:
        print(f"    +{m['healerHealPerRound']:3}/cast  {m['name']!r} (CR {m['cr']})  "
              f"spell: {m['healerSpellName']}")


if __name__ == "__main__":
    main()
