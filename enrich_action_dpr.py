"""
Parse non-main-attack actions and add per-round DPR/effect fields to each monster.

For each of bonusActions, reactions, legendaryActions, mythicActions, extract:
  - damage dice and compute average damage
  - attack type: attack-roll / save-based / auto
  - reaction subtype: damage / defense / counterspell / control

Adds the following fields per monster:
  bonusActionDpr       — avg damage/round from bonus action attacks (float)
  reactionDpr          — avg damage/round from damage reactions (float)
  reactionDefense      — AC bonus from defensive reactions (int, 0 if none)
  reactionNegate       — true if the monster has a counterspell-like reaction
  reactionControl      — true if the monster has a condition-applying reaction
  legendaryDpr         — avg damage/round from legendary actions (assumes 3 uses/rd)
  legendaryDprDetail   — [{name, dmg, cost}] breakdown
  mythicDpr            — avg damage/round from mythic actions
  actionEnrichmentNotes — list of unusual cases for manual review

Writes monsters_final.json in place (with backup).
"""

import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).parent
IN_PATH = HERE / "monsters_final.json"
BACKUP = HERE / "monsters_final.pre-action-enrich.json"

# ---- Damage parsing ----

DICE_RE = re.compile(
    r"(\d+)\s*\(\s*(\d+)\s*d\s*(\d+)\s*(?:([+-])\s*(\d+))?\s*\)"
)
# matches "12 (2d6 + 5)" / "44 (8d10)" / "10 ( 3d6 )"
PLAIN_DICE_RE = re.compile(r"(\d+)\s*d\s*(\d+)\s*(?:([+-])\s*(\d+))?")

# fallback — bare "X damage" with no dice (e.g. "The target takes 5 damage")
BARE_DMG_RE = re.compile(r"\btakes?\s+(\d+)\s+(?:[a-z]+\s+)?damage\b", re.I)


def extract_damage_values(text: str) -> list[float]:
    """Return list of average damage values found in text. Prefers parenthesized
    form `N (XdY+Z)` because WotC stat blocks always include it."""
    values = []
    # Primary: N (XdY + Z) — take the N (the average)
    for m in DICE_RE.finditer(text):
        values.append(float(m.group(1)))
    if values:
        return values
    # Fallback: raw dice without parenthesized average
    for m in PLAIN_DICE_RE.finditer(text):
        n = int(m.group(1)); d = int(m.group(2))
        sign = m.group(3); mod = int(m.group(4) or 0)
        avg = n * (d + 1) / 2
        if sign == "+": avg += mod
        elif sign == "-": avg -= mod
        values.append(avg)
    if values:
        return values
    # Last resort: "takes N damage"
    for m in BARE_DMG_RE.finditer(text):
        values.append(float(m.group(1)))
    return values


def action_damage(action: dict, main_actions: list | None = None) -> float:
    """Avg damage of a single action (sum of damage clauses in its description).

    If the description *references* a main action ("makes a tail attack", "uses
    its Bite") and main_actions is provided, look up that action's damage.

    Multi-component attacks ("deals X damage + Y damage on failed save") are
    summed. Returns 0 if no damage found."""
    desc = action.get("desc") or ""
    if not desc:
        return 0.0
    # skip obviously non-damage effects (heals, summons, movement)
    if re.search(r"\bhealing\b|regains?\s+\d+\s+Hit Point", desc, re.I):
        return 0.0
    values = extract_damage_values(desc)
    if values:
        return sum(values)

    # Fallback: look up referenced main action by name
    if main_actions:
        # patterns: "makes a tail attack", "makes one Bite attack", "uses its Claw"
        refs = []
        for m in re.finditer(
            r"makes? (?:a|one|two|three|four)\s+([A-Za-z][A-Za-z '\-]+?)\s+attack",
            desc,
        ):
            refs.append(m.group(1).strip())
        for m in re.finditer(r"uses? its ([A-Za-z][A-Za-z '\-]+?)(?:\s|\.|,|$)", desc):
            refs.append(m.group(1).strip())
        # resolve by name match
        main_by_name = {a.get("name", "").lower(): a for a in main_actions if isinstance(a, dict)}
        for ref in refs:
            key = ref.lower().rstrip("s")  # tail/tails, bite/bites
            # try exact, then startswith
            target = main_by_name.get(key) or main_by_name.get(ref.lower())
            if not target:
                for nm, a in main_by_name.items():
                    if nm.startswith(key) or key.startswith(nm):
                        target = a
                        break
            if target:
                dmg = sum(extract_damage_values(target.get("desc") or ""))
                if dmg:
                    return dmg
    return 0.0


# ---- Reaction classification ----

NEGATE_HINTS = [
    r"\bcounterspell\b",
    r"\binterrupt[s]? the spell\b",
    r"spell (?:fails?|is interrupted)",
    r"cast(?:er)?\s+loses? the spell",
]
DEFENSE_HINTS = [
    r"\badds? \+?\d+ to its AC\b",
    r"\badds? \+?\d+ to the AC\b",
    r"\bgains? \+?\d+ AC\b",
    r"\breduce(?:s|) the damage\b",
    r"\breduces? this damage by\b",
    r"\bhalf the damage\b",
    r"\bParry\b",
    r"\bShield(?:\s|\b)",
    r"\bDeflect(?: Missiles| Attack)?\b",
]
CONTROL_HINTS = [
    r"\bFrightened\b",
    r"\bCharmed\b",
    r"\bStunned\b",
    r"\bParalyzed\b",
    r"\bIncapacitated\b",
    r"\bProne\b",
    r"\bRestrained\b",
    r"\bGrappled\b",
]


def classify_reaction(action: dict) -> dict:
    desc = (action.get("desc") or "") + " " + (action.get("name") or "")
    out = {"damage": 0.0, "defense_bonus": 0, "negate": False, "control": False}
    # negate
    if any(re.search(p, desc, re.I) for p in NEGATE_HINTS):
        out["negate"] = True
    # defense
    for pat in DEFENSE_HINTS:
        m = re.search(pat, desc, re.I)
        if m:
            num = re.search(r"\+?(\d+)", m.group(0))
            if num:
                out["defense_bonus"] = max(out["defense_bonus"], int(num.group(1)))
            else:
                out["defense_bonus"] = max(out["defense_bonus"], 2)
            break
    # control
    if any(re.search(p, desc, re.I) for p in CONTROL_HINTS):
        out["control"] = True
    # damage
    out["damage"] = action_damage(action)
    return out


# ---- Legendary action economy ----

def legendary_cost(action: dict) -> int:
    """How many charges this leg action costs (default 1)."""
    text = (action.get("name") or "") + " " + (action.get("desc") or "")
    m = re.search(r"Costs\s+(\d+)\s+Action", text, re.I)
    if m:
        return int(m.group(1))
    return 1


def compute_legendary_dpr(leg_actions: list, main_actions: list | None = None,
                          leg_uses_per_round: int = 3) -> tuple[float, list]:
    """Pick the best-damage per-charge action, fill charges greedily.
    Returns (avg_dpr, detail_list)."""
    if not leg_actions:
        return 0.0, []
    analyzed = []
    for a in leg_actions:
        cost = legendary_cost(a)
        dmg = action_damage(a, main_actions=main_actions)
        analyzed.append({
            "name": a.get("name", ""),
            "damage": dmg,
            "cost": cost,
            "dpc": dmg / cost if cost else dmg,
        })
    # Greedy: pick highest damage-per-charge that fits remaining budget
    remaining = leg_uses_per_round
    total = 0.0
    analyzed.sort(key=lambda x: -x["dpc"])
    for a in analyzed:
        if a["cost"] > remaining: continue
        uses = remaining // a["cost"]
        total += uses * a["damage"]
        remaining -= uses * a["cost"]
        if remaining <= 0: break
    return total, analyzed


# ---- Main ----

def _as_list(val) -> list:
    """Normalize a field to a list of action dicts. Accepts list, None, or int."""
    if isinstance(val, list):
        return [a for a in val if isinstance(a, dict)]
    return []  # None or int (legacy count-only) → no action data to parse


def enrich_monster(m: dict) -> dict:
    notes = []

    # Bonus action DPR — every bonus action attack contributes each round
    ba_total = 0.0
    for a in _as_list(m.get("bonusActions")):
        dmg = action_damage(a)
        if dmg > 0:
            ba_total += dmg
        # note if BA has frequency limits
        if re.search(r"\brecharge\b|\(1/day|\(2/day|\bonce per\b", (a.get("desc") or "") + (a.get("name") or ""), re.I):
            notes.append(f"BA '{a.get('name')}' has limited frequency")
    m["bonusActionDpr"] = round(ba_total, 1)

    # Reaction classification — aggregate across all reactions
    rx_damage = 0.0
    rx_defense = 0
    rx_negate = False
    rx_control = False
    for a in _as_list(m.get("reactions")):
        c = classify_reaction(a)
        rx_damage += c["damage"]
        rx_defense = max(rx_defense, c["defense_bonus"])
        rx_negate = rx_negate or c["negate"]
        rx_control = rx_control or c["control"]
    # Reactions happen at most once/round. If multiple damage reactions exist,
    # we conservatively assume the highest-damage one fires.
    m["reactionDpr"] = round(min(rx_damage, max((action_damage(a) for a in _as_list(m.get("reactions"))), default=0)), 1)
    m["reactionDefense"] = rx_defense
    m["reactionNegate"] = rx_negate
    m["reactionControl"] = rx_control

    # Legendary DPR (can reference main actions by name)
    main_actions = _as_list(m.get("actions"))
    leg_dpr, leg_detail = compute_legendary_dpr(
        _as_list(m.get("legendaryActions")), main_actions=main_actions
    )
    m["legendaryDpr"] = round(leg_dpr, 1)
    m["legendaryDprDetail"] = [
        {"name": d["name"], "damage": round(d["damage"], 1), "cost": d["cost"]}
        for d in leg_detail
    ]

    # Mythic actions — treat like bonus/leg hybrid. Add their summed damage once/round.
    myth_total = 0.0
    for a in _as_list(m.get("mythicActions")):
        myth_total += action_damage(a)
    m["mythicDpr"] = round(myth_total, 1)

    m["actionEnrichmentNotes"] = notes
    return m


def main():
    if not BACKUP.exists():
        shutil.copy2(IN_PATH, BACKUP)
        print(f"Backup: {BACKUP.name}")

    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(data)} monsters")

    total_boosted = 0
    for m in data:
        enrich_monster(m)
        boost = (m.get("bonusActionDpr", 0) + m.get("reactionDpr", 0)
                 + m.get("legendaryDpr", 0) + m.get("mythicDpr", 0))
        if boost > 0:
            total_boosted += 1

    IN_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {IN_PATH.name} ({IN_PATH.stat().st_size:,} bytes)")
    print(f"Monsters with non-zero extra DPR: {total_boosted}/{len(data)}")

    # Show distribution of extra DPR
    print("\n=== Added DPR distribution ===")
    for field, label in [
        ("bonusActionDpr", "Bonus action DPR"),
        ("reactionDpr", "Reaction DPR"),
        ("legendaryDpr", "Legendary DPR"),
        ("mythicDpr", "Mythic DPR"),
    ]:
        vals = [m[field] for m in data if m.get(field, 0) > 0]
        if vals:
            vals.sort()
            print(f"  {label}: {len(vals)} monsters, "
                  f"median={vals[len(vals)//2]:.1f}, max={max(vals):.1f}")

    rx_def = sum(1 for m in data if m.get("reactionDefense", 0) > 0)
    rx_neg = sum(1 for m in data if m.get("reactionNegate"))
    rx_ctrl = sum(1 for m in data if m.get("reactionControl"))
    print(f"\n  Defensive reactions:  {rx_def}")
    print(f"  Negate reactions:     {rx_neg}")
    print(f"  Control reactions:    {rx_ctrl}")

    # Show top 10 biggest boosts for sanity check
    boosts = []
    for m in data:
        extra = (m.get("bonusActionDpr", 0) + m.get("reactionDpr", 0)
                 + m.get("legendaryDpr", 0) + m.get("mythicDpr", 0))
        if extra > 0:
            boosts.append((extra, m))
    boosts.sort(reverse=True, key=lambda x: x[0])
    print("\n=== Top 10 DPR boosts (sanity check) ===")
    for extra, m in boosts[:10]:
        print(f"  +{extra:5.1f}  {m['name']!r} (CR {m['cr']}, {m['source']}) "
              f"ba={m['bonusActionDpr']} rx={m['reactionDpr']} "
              f"leg={m['legendaryDpr']} myth={m['mythicDpr']}")


if __name__ == "__main__":
    main()
