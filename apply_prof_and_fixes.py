"""
Commit the prof-audit results back to monsters_final.json and fix the 4 outliers.

Outlier fixes (all judged from each monster's abilities + role):
  - Quenthel Baenre (OotA, CR 22): WIS-based cleric of Lolth. atk = prof+wis = 7+5 = +12
  - Regenerating Black Pudding (OotA, CR 5): STR slam attack. atk = prof+str = 3+3 = +6
  - Wiggan Nettlebee (PotA, CR 2): Druid NPC, WIS-based. atk = prof+wis = 2+2 = +4
  - Kobold Commoner (TftYP, CR 0): Stats all 10s, just prof. atk = prof+0 = +2
"""

import json
import shutil
from pathlib import Path

HERE = Path(__file__).parent
AUDIT_FILE = HERE / "monsters_final.prof_audit.json"
FINAL_FILE = HERE / "monsters_final.json"

FIXES = {
    # (name, source) -> {"atkBonus": int, "inferredAttackStat": str}
    ("Quenthel Baenre", "OotA"):         {"atkBonus": 12, "inferredAttackStat": "wis"},
    ("Regenerating Black Pudding", "OotA"): {"atkBonus": 6, "inferredAttackStat": "str"},
    ("Wiggan Nettlebee", "PotA"):         {"atkBonus": 4, "inferredAttackStat": "wis"},
    ("Kobold Commoner", "TftYP"):         {"atkBonus": 2, "inferredAttackStat": "str"},
}


def main():
    data = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(data)} monsters from audit file")

    applied = 0
    for m in data:
        key = (m.get("name"), m.get("source"))
        if key in FIXES:
            fix = FIXES[key]
            print(f"  Fixing {key[0]!r} ({key[1]}):")
            for k, v in fix.items():
                old = m.get(k)
                m[k] = v
                print(f"    {k}: {old} -> {v}")
            # Also set inferredMagicBonus to 0 since these are now clean computations
            m["inferredMagicBonus"] = 0
            applied += 1

    print(f"\nApplied {applied}/{len(FIXES)} outlier fixes")

    # Overwrite monsters_final.json with audit data + fixes
    FINAL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {FINAL_FILE.name} ({FINAL_FILE.stat().st_size:,} bytes)")
    print(f"Backup preserved at: monsters_final.pre-prof.json")


if __name__ == "__main__":
    main()
