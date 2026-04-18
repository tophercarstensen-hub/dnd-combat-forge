"""
Add derived `prof` field to every monster and audit attack-stat assumptions.

Step 1: Compute prof from CR using the PHB 2024 table (Up to 4=+2, 5-8=+3,
        9-12=+4, 13-16=+5, 17-20=+6, 21-24=+7, 25-28=+8, 29-30=+9).

Step 2: For each monster, derive expected attack-stat modifier:
            expected_mod = atkBonus - prof
        Then compare against all 6 ability mods, allowing for +1/+2/+3 magic
        bonuses, to infer which stat the monster is actually attacking with.

Step 3: Flag outliers — monsters whose atkBonus doesn't fit any ability mod
        plausibly, and monsters whose best-fit ability is NOT max(str,dex).

Writes:
  monsters_final.prof_audit.json   (data + added prof field)
  monsters_audit_report.json        (report of outliers for review)
"""

import json
from pathlib import Path
from collections import Counter, defaultdict

HERE = Path(__file__).parent
IN_PATH = HERE / "monsters_final.json"
OUT_PATH = HERE / "monsters_final.prof_audit.json"
REPORT_PATH = HERE / "monsters_audit_report.json"


def ability_mod(score: int) -> int:
    return (score - 10) // 2


def cr_to_prof(cr_str: str) -> int:
    """PHB 2024 Proficiency table. CR as string (handles '1/8', '1/4', '1/2')."""
    fraction_map = {"0": 0, "1/8": 0.125, "1/4": 0.25, "1/2": 0.5}
    if cr_str in fraction_map:
        cr = fraction_map[cr_str]
    else:
        try:
            cr = int(cr_str)
        except (ValueError, TypeError):
            return 2
    if cr <= 4:  return 2
    if cr <= 8:  return 3
    if cr <= 12: return 4
    if cr <= 16: return 5
    if cr <= 20: return 6
    if cr <= 24: return 7
    if cr <= 28: return 8
    return 9


ABILITIES = ["str", "dex", "con", "int", "wis", "cha"]


def best_fitting_ability(atk_bonus: int, prof: int, abils: dict):
    """Return (best_ability, magic_bonus, exact_match).

    Searches for an ability whose modifier + prof (+ 0..3 magic) == atk_bonus.
    Prefers max(str,dex), then any match, smallest magic bonus wins.
    """
    if atk_bonus is None:
        return None, None, False
    target = atk_bonus - prof  # ability_mod + magic_bonus
    mods = {a: ability_mod(abils.get(a, 10)) for a in ABILITIES}

    # Candidate scoring: (magic_bonus, -priority)
    candidates = []
    priority = {"str": 3, "dex": 3, "wis": 2, "cha": 2, "int": 1, "con": 0}
    for abil, mod in mods.items():
        for magic in (0, 1, 2, 3):
            if mod + magic == target:
                candidates.append((magic, -priority[abil], abil, mod, magic))
                break
    if not candidates:
        return None, None, False
    candidates.sort()
    _, _, abil, mod, magic = candidates[0]
    return abil, magic, True


def main():
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(data)} monsters from {IN_PATH.name}")

    # Counters for reporting
    by_attack_stat = Counter()
    by_magic_bonus = Counter()
    no_fit = []           # atkBonus doesn't match any stat+magic combo
    non_str_dex = []      # attacks using INT/WIS/CHA/CON
    missing_atk = []      # monsters with no atkBonus to audit

    for m in data:
        cr = str(m.get("cr", "0"))
        prof = cr_to_prof(cr)
        m["prof"] = prof

        atk = m.get("atkBonus")
        abils = m.get("abilities") or {}
        if atk is None or not abils:
            missing_atk.append({"name": m.get("name"), "cr": cr, "atkBonus": atk})
            m["inferredAttackStat"] = None
            m["inferredMagicBonus"] = None
            continue

        abil, magic, ok = best_fitting_ability(atk, prof, abils)
        m["inferredAttackStat"] = abil
        m["inferredMagicBonus"] = magic
        if not ok:
            no_fit.append({
                "name": m.get("name"),
                "source": m.get("source"),
                "cr": cr,
                "prof": prof,
                "atkBonus": atk,
                "expected_mod": atk - prof,
                "abilities": abils,
                "mods": {a: ability_mod(abils.get(a, 10)) for a in ABILITIES},
            })
        else:
            by_attack_stat[abil] += 1
            by_magic_bonus[magic] += 1
            if abil not in ("str", "dex"):
                non_str_dex.append({
                    "name": m.get("name"),
                    "source": m.get("source"),
                    "cr": cr,
                    "prof": prof,
                    "atkBonus": atk,
                    "inferredStat": abil,
                    "magicBonus": magic,
                    "stat_score": abils.get(abil),
                })

    # Write augmented data
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH.name} with added 'prof', 'inferredAttackStat', "
          f"'inferredMagicBonus' fields")

    # Build report
    total = len(data)
    report = {
        "total_monsters": total,
        "summary": {
            "missing_atkBonus": len(missing_atk),
            "no_ability_fits": len(no_fit),
            "non_str_dex_attackers": len(non_str_dex),
            "attack_stat_distribution": dict(by_attack_stat.most_common()),
            "magic_bonus_distribution": dict(sorted(by_magic_bonus.items())),
        },
        "outliers_no_fit": no_fit[:50],
        "non_str_dex_samples": non_str_dex[:100],
        "missing_atkBonus_samples": missing_atk[:30],
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Console summary
    print(f"\n=== Audit summary ({total} monsters) ===")
    print(f"  missing atkBonus:      {len(missing_atk):5} ({100*len(missing_atk)/total:.1f}%)")
    print(f"  no ability fits:       {len(no_fit):5} ({100*len(no_fit)/total:.1f}%)")
    print(f"  non-str/dex attackers: {len(non_str_dex):5} ({100*len(non_str_dex)/total:.1f}%)")
    print(f"\n  Attack stat distribution:")
    for abil, count in by_attack_stat.most_common():
        print(f"    {abil}: {count} ({100*count/total:.1f}%)")
    print(f"\n  Magic bonus distribution (0 = matches prof+mod exactly):")
    for bonus, count in sorted(by_magic_bonus.items()):
        label = f"+{bonus}" if bonus > 0 else "exact"
        print(f"    {label}: {count} ({100*count/total:.1f}%)")
    print(f"\nReport saved: {REPORT_PATH.name}")
    if no_fit:
        print(f"\nFirst 5 outliers (no ability fits):")
        for o in no_fit[:5]:
            print(f"  {o['name']!r} (CR {o['cr']}, {o['source']}): atk=+{o['atkBonus']}, "
                  f"expected mod=+{o['expected_mod']}, mods={o['mods']}")


if __name__ == "__main__":
    main()
