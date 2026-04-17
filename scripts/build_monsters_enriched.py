#!/usr/bin/env python3
"""
Build monsters_all_enriched_v2.json from local 5etools source files.

Usage:
    python build_monsters_enriched.py

Reads from:  C:\\Users\\tophe\\Downloads\\5etools-src-main
Reads also:  monsters_all_enriched.json  (must be in same folder as this script,
             OR the script will look for it next to the 5etools folder)
Writes to:   monsters_all_enriched_v2.json  (same folder as this script)
"""

import json
import re
import glob
import os
import sys
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURATION — edit these paths if needed
# ─────────────────────────────────────────────
def _find_etools_root():
    project_root = Path(__file__).resolve().parent.parent
    candidates = [
        project_root / "5etools-src-main" / "5etools-src-main",
        project_root / "5etools-src-main",
        Path(r"C:\Users\tophe\Downloads\5etools-src-main"),
        Path(r"C:\Users\tophe\Downloads\5etools-src-main\5etools-src-main"),
        Path(r"C:\Users\tophe\Downloads\5etools-src-main\src"),
    ]
    for p in candidates:
        if (p / "data" / "bestiary").exists():
            return p
    # Last resort: walk project root, then Downloads, looking for data/bestiary
    for search_root in (project_root, Path(r"C:\Users\tophe\Downloads")):
        if not search_root.exists():
            continue
        for child in search_root.rglob("bestiary"):
            if child.is_dir() and child.parent.name == "data":
                root = child.parent.parent
                print(f"  Auto-detected 5etools root: {root}")
                return root
    return candidates[0]  # will error with helpful message

ETOOLS_ROOT = _find_etools_root()

# The old enriched file — script looks in several places automatically
_ROOT_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _ROOT_DIR / "data"
OLD_ENRICHED_CANDIDATES = [
    _DATA_DIR / "monsters_all_enriched.json",
    _ROOT_DIR / "monsters_all_enriched.json",
    Path(__file__).parent / "monsters_all_enriched.json",
    ETOOLS_ROOT.parent / "monsters_all_enriched.json",
]

OUTPUT_FILE = _DATA_DIR / "monsters_all_enriched_v2.json"
# ─────────────────────────────────────────────


# ── 5etools tag stripping ────────────────────────────────────────────────────

TAG_RE = re.compile(r'\{@(\w+)([^}]*)\}')

ATK_MAP = {
    "mw": "Melee Weapon Attack:", "rw": "Ranged Weapon Attack:",
    "mwatk": "Melee Weapon Attack:", "rwatk": "Ranged Weapon Attack:",
    "atk": "Attack:", "mwrw": "Melee or Ranged Weapon Attack:",
    "mr": "Melee or Ranged Weapon Attack:", "m,r": "Melee or Ranged Weapon Attack:",
    "ms": "Melee Spell Attack:", "rs": "Melee or Ranged Spell Attack:",
}

def strip_tags(text):
    if not isinstance(text, str):
        return text

    def replace(m):
        tag, rest = m.group(1).lower(), m.group(2).strip()
        parts = [p.strip() for p in rest.split("|")] if rest else []

        if tag in ("b", "bold", "i", "italic", "s", "strike", "u", "underline"):
            return parts[0] if parts else ""
        if tag in ("note", "atk"):
            val = parts[0].lower() if parts else ""
            return ATK_MAP.get(val, val)
        if tag == "hit":
            n = parts[0] if parts else "0"
            try:
                v = int(n)
                return f"+{v}" if v >= 0 else str(v)
            except ValueError:
                return n
        if tag == "h":
            return "Hit: "
        if tag in ("damage", "dice"):
            return parts[0] if parts else ""
        if tag == "dc":
            return f"DC {parts[0]}" if parts else "DC"
        if tag in ("spell", "item", "creature", "condition", "status",
                   "skill", "sense", "action", "variantrule", "quickref",
                   "class", "subclass", "feat", "race", "background",
                   "table", "optfeature", "deity", "reward", "psionic",
                   "object", "trap", "hazard", "encounter", "vehicle",
                   "charOption", "card", "quote"):
            return parts[0] if parts else rest
        if tag == "recharge":
            val = parts[0] if parts else "6"
            return f"(Recharge {val}-6)" if val != "6" else "(Recharge 6)"
        if tag in ("atkrecharge", "actsave"):
            return parts[0].capitalize() if parts else ""
        if tag in ("actsavefail", "actsavesuccess", "actsavesuccessorfail",
                   "acttrigger", "actresponse"):
            labels = {"actsavefail": "Failure:", "actsavesuccess": "Success:",
                      "actsavesuccessorfail": "Success or Failure:",
                      "acttrigger": "Trigger:", "actresponse": "Effect:"}
            return labels.get(tag, "")
        if tag == "atkrecharge":
            return ""
        if tag in ("5et", "5etools"):
            return parts[0] if parts else ""
        if tag in ("filter", "link"):
            return parts[0] if parts else ""
        if tag in ("scaledice", "scaledamage"):
            return parts[2] if len(parts) > 2 else (parts[0] if parts else "")
        return parts[0] if parts else rest

    prev = None
    while prev != text:
        prev = text
        text = TAG_RE.sub(replace, text)
    return text


def strip_entries(obj):
    """Recursively collect plain text from a 5etools entries structure."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return strip_tags(obj)
    if isinstance(obj, list):
        return " ".join(strip_entries(x) for x in obj if x is not None)
    if isinstance(obj, dict):
        t = obj.get("type", "")
        if t in ("entries", "section"):
            parts = []
            if "name" in obj:
                parts.append(strip_tags(obj["name"]) + ":")
            parts.append(strip_entries(obj.get("entries", [])))
            return " ".join(p for p in parts if p)
        if t == "list":
            return strip_entries(obj.get("items", []))
        if t in ("item", "itemSub"):
            parts = []
            if "name" in obj:
                parts.append(strip_tags(obj["name"]) + ".")
            parts.append(strip_entries(obj.get("entries", [])))
            return " ".join(p for p in parts if p)
        if t == "table":
            rows = []
            for row in obj.get("rows", []):
                rows.append(" | ".join(strip_entries(c) for c in row))
            return " ".join(rows)
        if t == "abilityDc":
            ability = obj.get("attributes", [""])[0].upper()
            return f"Spell save DC = 8 + proficiency bonus + {ability} modifier"
        if t == "abilityAttackMod":
            ability = obj.get("attributes", [""])[0].upper()
            return f"Spell attack modifier = proficiency bonus + {ability} modifier"
        if t in ("inlineBlock", "inline", "quote"):
            return strip_entries(obj.get("entries", []))
        if "entries" in obj:
            return strip_entries(obj["entries"])
        if "entry" in obj:
            return strip_entries(obj["entry"])
    return ""


# ── Ability blocks ───────────────────────────────────────────────────────────

def extract_ability_block(m):
    abilities = {}
    for ab in ("str", "dex", "con", "int", "wis", "cha"):
        v = m.get(ab)
        if v is not None:
            abilities[ab] = int(v)
    return abilities


def mod(score):
    return (score - 10) // 2


# ── Saves ────────────────────────────────────────────────────────────────────

def extract_saves(m):
    raw = m.get("save", {})
    if not isinstance(raw, dict):
        return {}
    result = {}
    for k, v in raw.items():
        if isinstance(v, str):
            v = v.strip()
            try:
                result[k] = int(v.replace("+", ""))
            except ValueError:
                pass
        elif isinstance(v, (int, float)):
            result[k] = int(v)
    return result


# ── Skills ───────────────────────────────────────────────────────────────────

def extract_skills(m):
    raw = m.get("skill", {})
    if not isinstance(raw, dict):
        return {}
    result = {}
    for k, v in raw.items():
        if isinstance(v, str):
            try:
                result[k] = int(v.replace("+", "").strip())
            except ValueError:
                pass
        elif isinstance(v, (int, float)):
            result[k] = int(v)
    return result


# ── Speed ────────────────────────────────────────────────────────────────────

def extract_speed(m):
    raw = m.get("speed", {})
    if isinstance(raw, int):
        return {"walk": raw}
    if not isinstance(raw, dict):
        return {}
    result = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            result[k] = v.get("number", 0)
        elif isinstance(v, (int, float)):
            result[k] = int(v)
        elif isinstance(v, bool):
            pass  # "canHover" etc.
    return result


# ── AC ───────────────────────────────────────────────────────────────────────

def extract_ac(m):
    raw = m.get("ac", [])
    if not raw:
        return None
    first = raw[0]
    if isinstance(first, int):
        return first
    if isinstance(first, dict):
        return first.get("ac", first.get("number"))
    return None


# ── HP ───────────────────────────────────────────────────────────────────────

def extract_hp(m):
    raw = m.get("hp", {})
    if isinstance(raw, dict):
        return {"average": raw.get("average"), "formula": raw.get("formula", "")}
    if isinstance(raw, int):
        return {"average": raw, "formula": ""}
    return {"average": None, "formula": ""}


# ── CR ───────────────────────────────────────────────────────────────────────

def extract_cr(m):
    raw = m.get("cr")
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get("cr", raw.get("lair", raw.get("coven")))
    return str(raw)


# ── Damage resist/immune/vuln ────────────────────────────────────────────────

def _flat_damages(lst):
    out = []
    for item in (lst or []):
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            out.extend(item.get("immune", item.get("resist", item.get("vulnerable", []))))
    return out


# ── Senses ───────────────────────────────────────────────────────────────────

def extract_senses(m):
    raw = m.get("senses", [])
    if isinstance(raw, str):
        return [raw]
    return [strip_tags(s) if isinstance(s, str) else strip_tags(s.get("special", "")) for s in raw if s]


# ── Languages ────────────────────────────────────────────────────────────────

def extract_languages(m):
    raw = m.get("languages", [])
    if isinstance(raw, str):
        return [raw]
    return [strip_tags(s) if isinstance(s, str) else strip_tags(s.get("special", "")) for s in raw if s]


# ── Trait/Action/etc blocks ───────────────────────────────────────────────────

def extract_block(items):
    if not items:
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = strip_tags(item.get("name", ""))
        raw_entries = item.get("entries", [])
        text = strip_entries(raw_entries).strip()
        if name or text:
            out.append({"name": name, "desc": text})
    return out


# ── Spellcasting ─────────────────────────────────────────────────────────────

def extract_spellcasting(m):
    raw = m.get("spellcasting", [])
    if not raw:
        return []
    out = []
    for sc in raw:
        if not isinstance(sc, dict):
            continue
        name = strip_tags(sc.get("name", "Spellcasting"))
        header = strip_entries(sc.get("headerEntries", []))
        spells_text = []

        for freq in ("will", "rest", "ritual"):
            splist = sc.get(freq, [])
            if splist:
                spells_text.append(f"At will: {', '.join(strip_tags(s) for s in splist)}")

        daily = sc.get("daily", {})
        for freq_key in sorted(daily.keys()):
            splist = daily[freq_key]
            label = freq_key.replace("e", "/day each").replace("r", "/rest")
            if label.isdigit():
                label = f"{label}/day"
            spells_text.append(f"{label}: {', '.join(strip_tags(s) for s in splist)}")

        spells = sc.get("spells", {})
        for level in sorted(spells.keys(), key=lambda x: int(x) if x.isdigit() else 99):
            lvl_data = spells[level]
            if isinstance(lvl_data, dict):
                spell_list = lvl_data.get("spells", [])
                slots = lvl_data.get("slots", "")
                slot_str = f" ({slots} slots)" if slots else ""
                lvl_label = "Cantrips" if level == "0" else f"Level {level}{slot_str}"
                spells_text.append(f"{lvl_label}: {', '.join(strip_tags(s) for s in spell_list)}")

        desc = ". ".join(filter(None, [header] + spells_text))
        out.append({"name": name, "desc": desc})
    return out


# ── Type ─────────────────────────────────────────────────────────────────────

def extract_type(m):
    raw = m.get("type", "")
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        base = raw.get("type", "")
        tags = raw.get("tags", [])
        if tags:
            tag_strs = []
            for t in tags:
                if isinstance(t, str):
                    tag_strs.append(t)
                elif isinstance(t, dict):
                    tag_strs.append(t.get("tag", t.get("prefix", "")))
            return f"{base} ({', '.join(tag_strs)})"
        return base
    return str(raw)


# ── Alignment ────────────────────────────────────────────────────────────────

ALIGNMENT_MAP = {
    "L": "lawful", "N": "neutral", "C": "chaotic",
    "G": "good", "E": "evil", "U": "unaligned",
    "A": "any", "NX": "neutral", "NY": "neutral",
    "CE": "chaotic evil", "CG": "chaotic good",
    "LE": "lawful evil", "LG": "lawful good",
    "NE": "neutral evil", "NG": "neutral good",
    "TN": "true neutral",
}

def extract_alignment(m):
    raw = m.get("alignment", [])
    if not raw:
        return None
    parts = []
    for a in raw:
        if isinstance(a, str):
            parts.append(ALIGNMENT_MAP.get(a, a.lower()))
        elif isinstance(a, dict):
            if "alignment" in a:
                parts.extend(ALIGNMENT_MAP.get(x, x.lower()) for x in a["alignment"])
    return " ".join(dict.fromkeys(parts)) or None


# ── Size ─────────────────────────────────────────────────────────────────────

SIZE_MAP = {"T": "Tiny", "S": "Small", "M": "Medium",
            "L": "Large", "H": "Huge", "G": "Gargantuan"}

def extract_size(m):
    raw = m.get("size", [])
    if isinstance(raw, str):
        return SIZE_MAP.get(raw, raw)
    if isinstance(raw, list) and raw:
        if len(raw) == 1:
            return SIZE_MAP.get(raw[0], raw[0])
        return "/".join(SIZE_MAP.get(s, s) for s in raw)
    return None


# ── Environment ──────────────────────────────────────────────────────────────

def extract_environment(m):
    raw = m.get("environment", [])
    if isinstance(raw, str):
        return [raw]
    return [e for e in raw if isinstance(e, str)]


# ── Legendary actions ────────────────────────────────────────────────────────

def extract_legendary(m):
    raw = m.get("legendary", [])
    lheader = m.get("legendaryHeader", [])
    header_text = strip_entries(lheader)
    actions = extract_block(raw)
    if header_text and actions:
        actions[0]["header"] = header_text
    return actions


# ── Combat-calc compatibility fields ─────────────────────────────────────────

def infer_combat_calc_fields(m, abilities):
    """
    Attempt to infer atkBonus, numAtks, dmgPerAtk, dmgTypes, saveDC,
    aoeType, aoeDmg from the 5etools action data.
    """
    result = {
        "atkBonus": None,
        "numAtks": 1,
        "dmgPerAtk": None,
        "dmgTypes": [],
        "saveDC": None,
        "saveAbility": None,
        "aoeType": None,
        "aoeDmg": None,
        "multiattack": False,
    }

    actions = m.get("action", []) or []
    action_tags = m.get("actionTags", []) or []
    if "Multiattack" in action_tags:
        result["multiattack"] = True

    # Find best attack action
    best_dmg_val = -1

    # Regexes on RAW (un-stripped) entries text to catch {@hit} and {@damage} tags
    dmg_tag_re = re.compile(r'\{@damage ([^}]+)\}')
    hit_re = re.compile(r'\{@hit ([+-]?\d+)\}')
    dc_re = re.compile(r'\{@dc (\d+)\}')
    # Also match already-stripped forms as fallback
    hit_plain_re = re.compile(r'([+-]\d+) to hit')
    dmg_plain_re = re.compile(r'Hit:.*?(\d+d\d+(?:[+-]\d+)?)')
    dc_plain_re = re.compile(r'DC\s*(\d+)')

    num_atk_re = re.compile(r'makes? (\w+) (?:attack|.*?Attack)', re.IGNORECASE)
    num_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

    def get_raw_text(entries):
        """Get raw JSON string of entries to search for tags before stripping."""
        return json.dumps(entries) if entries else ""

    for action in actions:
        if not isinstance(action, dict):
            continue
        name = action.get("name", "").lower()
        entries = action.get("entries", [])
        raw_text = get_raw_text(entries)
        stripped_text = strip_entries(entries)

        if "multiattack" in name:
            m2 = num_atk_re.search(stripped_text)
            if m2:
                word = m2.group(1).lower()
                result["numAtks"] = num_words.get(word, result["numAtks"])
            result["multiattack"] = True
            continue

        # Try raw tag search first
        hit_matches = hit_re.findall(raw_text)
        dmg_matches = dmg_tag_re.findall(raw_text)
        dc_matches = dc_re.findall(raw_text)

        # Fall back to plain text search if tags not found
        if not hit_matches:
            hit_matches = hit_plain_re.findall(stripped_text)
        if not dmg_matches:
            dmg_matches = dmg_plain_re.findall(stripped_text)
        if not dc_matches:
            dc_matches = dc_plain_re.findall(stripped_text)

        if hit_matches and dmg_matches:
            resolved = _resolve_attack_damage(raw_text, dmg_matches)
            try:
                total_dmg = _avg_dice(resolved) if resolved else 0
            except Exception:
                total_dmg = 0
            if total_dmg > best_dmg_val:
                best_dmg_val = total_dmg
                result["atkBonus"] = int(str(hit_matches[0]).replace("+", ""))
                result["dmgPerAtk"] = resolved
        elif dc_matches and dmg_matches:
            resolved = _resolve_attack_damage(raw_text, dmg_matches)
            try:
                total_dmg = _avg_dice(resolved) if resolved else 0
            except Exception:
                total_dmg = 0
            if result["saveDC"] is None:
                result["saveDC"] = int(dc_matches[0])
            if total_dmg > best_dmg_val:
                best_dmg_val = total_dmg
                result["aoeDmg"] = resolved

    # Damage types
    dmg_tags = m.get("damageTags", []) or []
    type_map = {
        "A": "acid", "B": "bludgeoning", "C": "cold", "F": "fire",
        "O": "force", "L": "lightning", "N": "necrotic", "P": "piercing",
        "I": "poison", "Y": "psychic", "R": "radiant", "S": "slashing",
        "T": "thunder",
    }
    result["dmgTypes"] = [type_map.get(t, t.lower()) for t in dmg_tags if t in type_map]

    # AOE type
    misc_tags = m.get("miscTags", []) or []
    if "AOE" in misc_tags:
        result["aoeType"] = "AOE"

    return result


def _classify_damage_connector(text):
    """Given raw 5etools text between two {@damage} tags, decide if the
    second tag is a versatile alternate (skip) or a rider (sum).

    Versatile: "..., or 8 ({@damage 1d10 + 3}) slashing damage if used with two hands."
    Rider:     "... piercing damage plus 3 ({@damage 1d6}) fire damage."
    """
    t = text.lower()
    # Explicit versatile phrasing wins
    if re.search(r'\bor\b[^.]{0,80}(if\s+used|two[- ]?hand|versatile|wielded)', t):
        return "versatile"
    # Bare " or " before another damage tag — treat as alternate
    if re.search(r'\bor\b', t) and not re.search(r'\b(plus|and)\b', t):
        return "versatile"
    # Everything else (plus / and / comma-joined) is a rider
    return "rider"


def _resolve_attack_damage(raw_text, dmg_matches):
    """Collapse a list of damage dice tags from one action into a compound
    formula string, honoring versatile/rider semantics. Returns a string like
    "1d8 + 3" or "1d8 + 3 + 1d6" that `_avg_dice` can sum and the JS side's
    `avgDiceFormula` can parse.
    """
    if not dmg_matches:
        return None
    if len(dmg_matches) == 1:
        return dmg_matches[0]
    tag_positions = list(re.finditer(r'\{@damage ([^}]+)\}', raw_text))
    # If position lookup disagrees with the match list (e.g. plain-text
    # fallback was used), fall back to the first formula only.
    if len(tag_positions) != len(dmg_matches):
        return dmg_matches[0]
    kept = [dmg_matches[0].strip()]
    for i in range(1, len(tag_positions)):
        connector = raw_text[tag_positions[i - 1].end(): tag_positions[i].start()]
        if _classify_damage_connector(connector) == "rider":
            kept.append(dmg_matches[i].strip())
    return " + ".join(kept)


def _avg_dice(expr):
    """Rough average of a dice expression like '2d6+4'."""
    expr = expr.strip()
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


# ── XP table ─────────────────────────────────────────────────────────────────

CR_TO_XP = {
    "0": 10, "1/8": 25, "1/4": 50, "1/2": 100,
    "1": 200, "2": 450, "3": 700, "4": 1100, "5": 1800,
    "6": 2300, "7": 2900, "8": 3900, "9": 5000, "10": 5900,
    "11": 7200, "12": 8400, "13": 10000, "14": 11500, "15": 13000,
    "16": 15000, "17": 18000, "18": 20000, "19": 23000, "20": 25000,
    "21": 33000, "22": 41000, "23": 50000, "24": 62000, "25": 75000,
    "26": 90000, "27": 105000, "28": 120000, "29": 135000, "30": 155000,
}


# ── Main build ────────────────────────────────────────────────────────────────

def find_old_enriched():
    for path in OLD_ENRICHED_CANDIDATES:
        if path.exists():
            print(f"  Found old enriched file: {path}")
            return path
    return None


def load_fluff(etools_root):
    """Load all fluff files into {source: {name: lore_text}}."""
    fluff_dir = etools_root / "data" / "bestiary"
    fluff_map = {}
    patterns = [fluff_dir / "fluff-bestiary-*.json"]
    files = []
    for pat in patterns:
        files.extend(glob.glob(str(pat)))

    for fpath in files:
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("monsterFluff", data.get("monster", []))
            for entry in entries:
                name = entry.get("name", "")
                source = entry.get("source", "")
                entries_raw = entry.get("entries", [])
                lore = strip_entries(entries_raw).strip()
                if lore:
                    fluff_map[(name.lower(), source.upper())] = lore
        except Exception as e:
            print(f"  Warning: could not load fluff {fpath}: {e}")

    print(f"  Loaded fluff for {len(fluff_map)} monsters from {len(files)} files")
    return fluff_map


def resolve_copy(m, all_by_key):
    """Follow _copy chains to get a fully-resolved monster dict."""
    seen = set()
    current = m
    while "_copy" in current:
        cp = current["_copy"]
        key = (cp["name"].lower(), cp.get("source", "MM").upper())
        if key in seen:
            break
        seen.add(key)
        base = all_by_key.get(key)
        if not base:
            break
        # Merge: base fields, then override with current (non-_copy) fields
        merged = dict(base)
        for k, v in current.items():
            if k not in ("_copy",):
                merged[k] = v
        # Apply _mod if present
        mods = current.get("_mod", {})
        if mods:
            merged = apply_mods(merged, mods)
        current = merged
    return current


def apply_mods(m, mods):
    """Very basic _mod support: replace/append entries."""
    for field, operations in mods.items():
        if isinstance(operations, list):
            for op in operations:
                if not isinstance(op, dict):
                    continue
                mode = op.get("mode", "")
                if mode == "replaceName":
                    if field in m:
                        m[field] = op.get("replace", m[field])
                elif mode == "appendArr":
                    if field not in m:
                        m[field] = []
                    if isinstance(m[field], list):
                        items = op.get("items", [])
                        if isinstance(items, list):
                            m[field].extend(items)
                        else:
                            m[field].append(items)
    return m


def build_monster(m_raw, fluff_map, old_env_map):
    """Convert a raw 5etools monster dict to combat-calc schema."""

    m = m_raw  # already resolved

    name = m.get("name", "")
    source = m.get("source", "")

    abilities = extract_ability_block(m)
    ac = extract_ac(m)
    hp = extract_hp(m)
    cr = extract_cr(m)
    saves = extract_saves(m)
    skills = extract_skills(m)
    speed = extract_speed(m)
    senses = extract_senses(m)
    languages = extract_languages(m)
    size = extract_size(m)
    mtype = extract_type(m)
    alignment = extract_alignment(m)

    resist = _flat_damages(m.get("resist", []))
    immune = _flat_damages(m.get("immune", []))
    vuln = _flat_damages(m.get("vulnerable", []))
    cond_immune = m.get("conditionImmune", [])
    if isinstance(cond_immune, list):
        cond_immune = [c if isinstance(c, str) else c.get("conditionImmune", "") for c in cond_immune]

    traits = extract_block(m.get("trait", []))
    actions = extract_block(m.get("action", []))
    bonus_actions = extract_block(m.get("bonus", []))
    reactions = extract_block(m.get("reaction", []))
    legendary = extract_legendary(m)
    mythic = extract_block(m.get("mythic", []))
    spellcasting = extract_spellcasting(m)

    # Lore
    lore_key = (name.lower(), source.upper())
    lore = fluff_map.get(lore_key, "")
    if not lore:
        # fallback: case-insensitive name match any source
        for (n, _s), v in fluff_map.items():
            if n == name.lower() and v:
                lore = v
                break

    # Environment: prefer 5etools; fall back to old enriched
    env_5et = extract_environment(m)
    old_env = old_env_map.get((name.lower(), source.upper()), [])
    if not old_env:
        old_env = old_env_map.get((name.lower(), ""), [])
    environment = list(dict.fromkeys(env_5et + old_env))

    # Source type classification
    OFFICIAL_SOURCES = {
        "MM","PHB","DMG","VGM","MTF","XGE","TCE","MOT","FTD","BMT","BAM",
        "VRGR","SCC","IDRotF","WDH","WDMM","GGR","EGW","AI","OGA","IMR",
        "HftT","DSotDQ","KftGV","PAbtSO","SatO","ToFW","VEoR","XMM","XPHB",
        "XDMG","QftIS","MisMV","SLW","SD","ToA","PotA","SKT","CoS","LMoP",
        "TftYP","Rot","HotDQ","WBtW","RMBre","NF","OoW","OotA",
        "GoS","DC","BGDIA","EET","RMBRE","HAT-LMI","HAT-TG","RTG","SADS",
        "SDW","SCC","NRH-AT","NRH-AWOL","NRH-ASS","NRH-CoI","NRH-TLT",
        "NRH-TCMC","NRH-AVitW","MPP","VEOR","VD","TTP","TOFW","ROT",
        "PS-A","PS-D","PS-I","PS-K","PS-X","PS-Z","SLWCTG"
    }
    COMMUNITY_SOURCES = {
        "UA","UAClassFeatureVariants","PSA","PSI","PSK",
        "PSX","PSZ","PSD","STREAM","TWITTER","UARC"
    }
    source_upper = source.upper()
    if source_upper in OFFICIAL_SOURCES:
        source_type = "official"
    elif source_upper in COMMUNITY_SOURCES:
        source_type = "community"
    else:
        source_type = "third-party"

    # Slug
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    # Make slug unique by appending source if needed
    slug = f"{slug}-{source.lower()}" if source else slug

    # Combat-calc fields
    cc = infer_combat_calc_fields(m, abilities)
    xp = CR_TO_XP.get(str(cr), None)

    passive = m.get("passive")
    initiative_bonus = m.get("initiative", {})
    if isinstance(initiative_bonus, dict):
        initiative_bonus = initiative_bonus.get("proficiency", None)
    else:
        initiative_bonus = None

    return {
        "name": name,
        "slug": slug,
        "source": source,
        "sourceType": source_type,
        "page": m.get("page"),
        "size": size,
        "type": mtype,
        "alignment": alignment,
        "ac": ac,
        "hp": hp,
        "speed": speed,
        "abilities": abilities,
        "saves": saves,
        "skills": skills,
        "senses": senses,
        "passive": passive,
        "languages": languages,
        "cr": cr,
        "xp": xp,
        "resistances": resist,
        "immunities": immune,
        "vulnerabilities": vuln,
        "conditionImmunities": cond_immune,
        "traits": traits,
        "actions": actions,
        "bonusActions": bonus_actions,
        "reactions": reactions,
        "legendaryActions": legendary,
        "mythicActions": mythic,
        "spellcasting": spellcasting,
        "lore": lore,
        "environment": environment,
        # Combat-calc compat
        "atkBonus": cc["atkBonus"],
        "numAtks": cc["numAtks"],
        "dmgPerAtk": cc["dmgPerAtk"],
        "dmgTypes": cc["dmgTypes"],
        "saveDC": cc["saveDC"],
        "saveAbility": cc["saveAbility"],
        "aoeType": cc["aoeType"],
        "aoeDmg": cc["aoeDmg"],
        "multiattack": cc["multiattack"],
    }


def main():
    print("=" * 60)
    print("D&D 5e Monster Data Rebuild")
    print("=" * 60)

    # Verify 5etools root
    bestiary_dir = ETOOLS_ROOT / "data" / "bestiary"
    if not bestiary_dir.exists():
        print(f"\nERROR: Could not find bestiary folder at:\n  {bestiary_dir}")
        print("\nMake sure ETOOLS_ROOT in this script points to the root of")
        print("your 5etools-src-main folder (the one containing 'data/').")
        sys.exit(1)

    print(f"\n5etools root: {ETOOLS_ROOT}")
    print(f"Bestiary dir: {bestiary_dir}")

    # Load old enriched file for environment preservation
    old_env_map = {}
    old_path = find_old_enriched()
    if old_path:
        print(f"\nLoading old enriched file for environment data...")
        try:
            with open(old_path, encoding="utf-8") as f:
                old_data = json.load(f)
            monsters_list = old_data if isinstance(old_data, list) else old_data.get("monsters", old_data.get("monster", []))
            for m in monsters_list:
                name = m.get("name", "").lower()
                source = m.get("source", "").upper()
                env = m.get("environment", [])
                if env:
                    old_env_map[(name, source)] = env
                    old_env_map[(name, "")] = env  # fallback
            print(f"  Loaded environment data for {len(old_env_map)//2} monsters")
        except Exception as e:
            print(f"  Warning: could not load old enriched file: {e}")
    else:
        print("\nNote: old monsters_all_enriched.json not found. Environment data")
        print("      will come from 5etools only (some monsters may have no environment).")
        print("      To fix: put monsters_all_enriched.json next to this script.")

    # Load fluff
    print("\nLoading fluff/lore data...")
    fluff_map = load_fluff(ETOOLS_ROOT)

    # Load all bestiary stat files
    print("\nLoading bestiary stat files...")
    stat_files = sorted(glob.glob(str(bestiary_dir / "bestiary-*.json")))
    # Exclude fluff files (glob above shouldn't catch them but be safe)
    stat_files = [f for f in stat_files if "fluff" not in Path(f).name]
    print(f"  Found {len(stat_files)} stat files")

    # First pass: load all monsters into a lookup for _copy resolution
    all_monsters_raw = []
    all_by_key = {}  # (name.lower(), source.upper()) -> raw dict

    for fpath in stat_files:
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            for m in data.get("monster", []):
                name = m.get("name", "")
                source = m.get("source", "")
                key = (name.lower(), source.upper())
                all_by_key[key] = m
                all_monsters_raw.append(m)
        except Exception as e:
            print(f"  Warning: could not load {fpath}: {e}")

    print(f"  Loaded {len(all_monsters_raw)} raw monster entries")

    # Second pass: resolve _copy and build output
    print("\nBuilding enriched monster list...")
    output = []
    skipped = 0
    errors = 0

    for i, m_raw in enumerate(all_monsters_raw):
        if i % 500 == 0 and i > 0:
            print(f"  Processed {i}/{len(all_monsters_raw)}...")
        try:
            resolved = resolve_copy(m_raw, all_by_key)
            built = build_monster(resolved, fluff_map, old_env_map)
            # Skip monsters with no name or clearly placeholder entries
            if not built["name"]:
                skipped += 1
                continue
            output.append(built)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error on {m_raw.get('name','?')}: {e}")

    print(f"\nTotal monsters built: {len(output)}")
    print(f"Skipped: {skipped}, Errors: {errors}")

    # Stats
    has_traits = sum(1 for m in output if m.get("traits"))
    has_actions = sum(1 for m in output if m.get("actions"))
    has_lore = sum(1 for m in output if m.get("lore"))
    has_saves = sum(1 for m in output if m.get("saves"))
    has_env = sum(1 for m in output if m.get("environment"))
    has_atk = sum(1 for m in output if m.get("atkBonus") is not None)
    official = sum(1 for m in output if m.get("sourceType") == "official")
    third_party = sum(1 for m in output if m.get("sourceType") == "third-party")
    community = sum(1 for m in output if m.get("sourceType") == "community")

    print(f"\nData quality:")
    print(f"  Has traits:      {has_traits}/{len(output)} ({has_traits*100//len(output)}%)")
    print(f"  Has actions:     {has_actions}/{len(output)} ({has_actions*100//len(output)}%)")
    print(f"  Has lore:        {has_lore}/{len(output)} ({has_lore*100//len(output)}%)")
    print(f"  Has saves:       {has_saves}/{len(output)} ({has_saves*100//len(output)}%)")
    print(f"  Has environment: {has_env}/{len(output)} ({has_env*100//len(output)}%)")
    print(f"  Has atkBonus:    {has_atk}/{len(output)} ({has_atk*100//len(output)}%)")
    print(f"\nSource breakdown:")
    print(f"  Official:        {official}")
    print(f"  Third-party:     {third_party}")
    print(f"  Community:       {community}")

    # Write output
    print(f"\nWriting {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    size_mb = OUTPUT_FILE.stat().st_size / 1024 / 1024
    print(f"Done! Output: {OUTPUT_FILE} ({size_mb:.1f} MB)")
    print("\nSample monster check (first MM monster with actions):")
    for m in output:
        if m.get("source") == "MM" and m.get("actions"):
            print(f"  {m['name']} (CR {m['cr']}, AC {m['ac']}, HP {m['hp']['average']})")
            print(f"  Actions: {[a['name'] for a in m['actions'][:3]]}")
            print(f"  Traits:  {[t['name'] for t in m['traits'][:3]]}")
            break


if __name__ == "__main__":
    main()
