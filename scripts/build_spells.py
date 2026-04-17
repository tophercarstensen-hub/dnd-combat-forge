#!/usr/bin/env python3
"""
Build spells_final.json from local 5etools source files.

Usage:
    python build_spells.py

Reads from:  ../5etools-src-main/5etools-src-main/data/spells/
Writes to:   ../spells_final.json
"""

import json
import re
import glob
import os
import sys
from pathlib import Path
from collections import defaultdict

# ─────────────────────────────────────────────
# CONFIGURATION
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
        if (p / "data" / "spells").exists():
            return p
    # Last resort: walk project root + Downloads looking for data/spells
    for search_root in (project_root, Path(r"C:\Users\tophe\Downloads")):
        if not search_root.exists():
            continue
        for child in search_root.rglob("spells"):
            if child.is_dir() and child.parent.name == "data":
                root = child.parent.parent
                print(f"  Auto-detected 5etools root: {root}")
                return root
    return candidates[0]


ETOOLS_ROOT = _find_etools_root()
SPELLS_DIR  = ETOOLS_ROOT / "data" / "spells"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "spells_final.json"

# ─────────────────────────────────────────────
# OFFICIAL SOURCES
# ─────────────────────────────────────────────

OFFICIAL_SOURCES = {
    "PHB","XPHB","DMG","XDMG","MM","XMM","VGM","MTF","XGE","TCE","MOT","FTD",
    "BMT","BAM","VRGR","SCC","IDRotF","WDH","WDMM","GGR","EGW","AI","OGA","IMR",
    "HftT","DSotDQ","KftGV","PAbtSO","SatO","ToFW","VEoR","QftIS","MisMV","SLW",
    "SD","ToA","PotA","SKT","CoS","LMoP","TftYP","Rot","HotDQ","WBtW","RMBre",
    "NF","OoW","OotA","GoS","DC","BGDIA","EET","RMBRE","HAT-LMI","HAT-TG","RTG",
    "SADS","SDW","NRH-AT","NRH-AWOL","NRH-ASS","NRH-CoI","NRH-TLT","NRH-TCMC",
    "NRH-AVitW","MPP","VEOR","VD","TTP","TOFW","ROT","PS-A","PS-D","PS-I","PS-K",
    "PS-X","PS-Z","SLWCTG","AAG","AI","LLK","AitFR-AVT","EFA","FRHOF","BMT",
    "GGR","SCC","IDRotF",
}

# ─────────────────────────────────────────────
# SCHOOL CODES
# ─────────────────────────────────────────────

SCHOOL_MAP = {
    "A": "Abjuration",
    "C": "Conjuration",
    "D": "Divination",
    "E": "Enchantment",
    "I": "Illusion",
    "N": "Necromancy",
    "T": "Transmutation",
    "V": "Evocation",
}

# ─────────────────────────────────────────────
# TAG STRIPPING  (reused from build_monsters_enriched.py)
# ─────────────────────────────────────────────

TAG_RE = re.compile(r'\{@(\w+)([^}]*)\}')

def strip_tags(text):
    if not isinstance(text, str):
        return text

    def replace(m):
        tag, rest = m.group(1).lower(), m.group(2).strip()
        parts = [p.strip() for p in rest.split("|")] if rest else []

        if tag in ("b", "bold", "i", "italic", "s", "strike", "u", "underline"):
            return parts[0] if parts else ""
        if tag in ("damage", "dice"):
            return parts[0] if parts else ""
        if tag == "dc":
            return f"DC {parts[0]}" if parts else "DC"
        if tag == "hit":
            n = parts[0] if parts else "0"
            try:
                v = int(n)
                return f"+{v}" if v >= 0 else str(v)
            except ValueError:
                return n
        if tag == "h":
            return "Hit: "
        if tag == "note":
            return parts[0] if parts else ""
        if tag in ("scaledice", "scaledamage"):
            # {@scaledamage 8d6|3-9|1d6} -> show the per-level scaling die
            return parts[2] if len(parts) > 2 else (parts[0] if parts else "")
        if tag in ("spell", "item", "creature", "condition", "status",
                   "skill", "sense", "action", "variantrule", "quickref",
                   "class", "subclass", "feat", "race", "background",
                   "table", "optfeature", "deity", "reward", "psionic",
                   "object", "trap", "hazard", "encounter", "vehicle",
                   "charOption", "card", "quote", "filter", "link",
                   "5et", "5etools"):
            return parts[0] if parts else rest
        if tag == "recharge":
            val = parts[0] if parts else "6"
            return f"(Recharge {val}-6)" if val != "6" else "(Recharge 6)"
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
        if t in ("inlineBlock", "inline", "quote"):
            return strip_entries(obj.get("entries", []))
        if "entries" in obj:
            return strip_entries(obj["entries"])
        if "entry" in obj:
            return strip_entries(obj["entry"])
    return ""

# ─────────────────────────────────────────────
# DICE MATH  (reused from build_monsters_enriched.py)
# ─────────────────────────────────────────────

def _avg_dice(expr):
    """Average of a dice expression like '8d6' or '2d6+4' or '1d8 + 1d6'."""
    if not expr:
        return 0
    expr = str(expr).strip()
    total = 0.0
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
        part = part.strip()
        if 'd' in part.lower():
            nd, ds = re.split(r'd', part.lower(), maxsplit=1)
            try:
                nd = int(nd) if nd.strip() else 1
                ds = int(re.sub(r'\D.*', '', ds))
                total += sign * nd * (ds + 1) / 2
            except ValueError:
                pass
        else:
            try:
                total += sign * float(part)
            except ValueError:
                pass
    return int(round(total))

# ─────────────────────────────────────────────
# PARSING HELPERS
# ─────────────────────────────────────────────

DAMAGE_TAG_RE  = re.compile(r'\{@damage ([^}]+)\}')
DICE_TAG_RE    = re.compile(r'\{@dice ([^}]+)\}')

# AOE area tag -> (shape, est_targets)
AREA_TAG_MAP = {
    "S":  ("sphere",    4),
    "C":  ("cone",      4),
    "L":  ("line",      3),
    "Y":  ("cylinder",  3),
    "Q":  ("cube",      4),
    "H":  ("hemisphere",4),
    "R":  ("radius",    4),
    "W":  ("wall",      3),
    "N":  ("single",    1),  # single-target (but still listed here)
    "ST": ("single",    1),
    "MT": ("multi",     3),
}

# AOE shapes that represent true area-of-effect (not single/multi-target)
AOE_SHAPES = {"sphere","cone","line","cylinder","cube","hemisphere","radius","wall"}

def parse_casting_time(time_list):
    """Return human-readable casting time string."""
    if not time_list:
        return "1 action"
    first = time_list[0]
    if not isinstance(first, dict):
        return str(first)
    n    = first.get("number", 1)
    unit = first.get("unit", "action")
    cond = first.get("condition", "")
    base = f"{n} {unit}" if n != 1 else f"1 {unit}"
    if cond:
        base += f", {strip_tags(cond)}"
    return base


def parse_range(range_obj):
    """Return human-readable range string."""
    if not range_obj:
        return "Self"
    rtype = range_obj.get("type", "")
    dist  = range_obj.get("distance", {})
    dtype = dist.get("type", "") if isinstance(dist, dict) else ""
    amt   = dist.get("amount")   if isinstance(dist, dict) else None

    if dtype == "self" or rtype == "point" and dtype == "self":
        return "Self"
    if dtype == "touch":
        return "Touch"
    if dtype == "sight":
        return "Sight"
    if dtype == "unlimited":
        return "Unlimited"
    if dtype == "feet" and amt is not None:
        return f"{amt} feet"
    if dtype == "miles" and amt is not None:
        return f"{amt} {'mile' if amt == 1 else 'miles'}"
    if rtype in ("cone","cube","line","sphere","hemisphere","cylinder","radius"):
        if amt:
            return f"Self ({amt}-foot {rtype})"
        return f"Self ({rtype})"
    if rtype == "special":
        return "Special"
    return rtype.capitalize() if rtype else "Self"


def parse_duration(duration_list):
    """Return (duration_str, is_concentration)."""
    if not duration_list:
        return "Instantaneous", False
    first = duration_list[0]
    if not isinstance(first, dict):
        return str(first), False

    dtype = first.get("type", "")
    conc  = first.get("concentration", False)

    if dtype == "instant":
        return "Instantaneous", False
    if dtype == "permanent":
        ends = first.get("ends", [])
        if ends:
            return f"Until dispelled or triggered", False
        return "Permanent", False
    if dtype == "special":
        return "Special", conc
    if dtype == "timed":
        d = first.get("duration", {})
        if isinstance(d, dict):
            amt   = d.get("amount", 1)
            dunit = d.get("type", "round")
            label = f"{amt} {dunit}" + ("s" if amt != 1 else "")
            if conc:
                return f"Concentration, up to {label}", True
            return label.capitalize(), False
    return dtype.capitalize(), conc


def parse_components(comp_obj):
    """Return human-readable components string."""
    if not comp_obj:
        return ""
    parts = []
    if comp_obj.get("v"):
        parts.append("V")
    if comp_obj.get("s"):
        parts.append("S")
    m = comp_obj.get("m")
    if m:
        if isinstance(m, dict):
            text = m.get("text", m.get("cost", ""))
            parts.append(f"M ({strip_tags(str(text))})" if text else "M")
        else:
            parts.append(f"M ({strip_tags(str(m))})" if str(m).strip() else "M")
    r = comp_obj.get("r")
    if r:
        parts.append("R")
    return ", ".join(parts)


def is_ritual(spell):
    """True if spell can be cast as a ritual."""
    # Check meta.ritual
    meta = spell.get("meta", {})
    if isinstance(meta, dict) and meta.get("ritual"):
        return True
    # Check time units for "ritual"
    for t in spell.get("time", []):
        if isinstance(t, dict) and t.get("unit") == "ritual":
            return True
    return False


# ─────────────────────────────────────────────
# DAMAGE FORMULA EXTRACTION
# ─────────────────────────────────────────────

def extract_damage_formula(spell):
    """
    Return (formula_str, avg_damage, scaling_formula).

    For cantrips with scalingLevelDice, uses the level-5 formula (most
    relevant for monsters CR 5+).

    For cantrips that scale by beam count (e.g. Eldritch Blast), multiplies
    the base die by the level-5 beam count (2 beams at level 5).

    scaling_formula: e.g. "8d6+1d6/level" for upcast damage.
    """
    level = spell.get("level", 0)
    entries_raw = json.dumps(spell.get("entries", []))
    higher_raw  = json.dumps(spell.get("entriesHigherLevel", []))

    # ── Cantrip: prefer scalingLevelDice at level 5 ──
    sld = spell.get("scalingLevelDice")
    if level == 0 and sld:
        scaling = sld.get("scaling", {}) if isinstance(sld, dict) else {}
        # Get the level-5 value (key "5"), fallback to key "1" then first key
        formula = scaling.get("5") or scaling.get("1") or (
            list(scaling.values())[0] if scaling else None
        )
        if formula:
            avg = _avg_dice(formula)
            # Build scaling description
            all_levels = sorted(scaling.items(), key=lambda x: int(x[0]))
            scale_str = "/".join(f"{v}@{k}" for k, v in all_levels)
            return formula, avg, scale_str

    # ── Cantrip: multi-beam scaling (e.g. Eldritch Blast — "two beams at 5th level") ──
    # Only pull {@damage} here, not {@dice}, to avoid picking up buff dice
    dmg_matches_raw = DAMAGE_TAG_RE.findall(entries_raw)
    if level == 0 and dmg_matches_raw and "SCL" in (spell.get("miscTags") or []):
        base_formula = dmg_matches_raw[0].strip()
        # Detect beam-count pattern: "two beams at 5th level" -> 2 beams
        beam_re = re.compile(
            r'(two|three|four|five)\s+beam(?:s)?\s+(?:at|when you reach)\s+(?:5th|level 5)',
            re.I
        )
        beam_match = beam_re.search(entries_raw)
        beam_words = {"two": 2, "three": 3, "four": 4, "five": 5}
        if beam_match:
            count = beam_words.get(beam_match.group(1).lower(), 1)
            # Parse "XdY" and multiply X by count
            m = re.match(r'(\d+)d(\d+)', base_formula)
            if m:
                scaled = f"{int(m.group(1))*count}d{m.group(2)}"
                avg = _avg_dice(scaled)
                # Build all scaling levels: 1 beam @1, 2 @5, 3 @11, 4 @17
                level_map = [("1", 1), ("5", 2), ("11", 3), ("17", 4)]
                scale_str = "/".join(
                    f"{int(m.group(1))*c}d{m.group(2)}@{lv}"
                    for lv, c in level_map
                )
                return scaled, avg, scale_str

    # ── Regular spells: pull only {@damage} tags from entries ──
    # Do NOT fall back to {@dice} — those are often buff/utility dice (d4 for Bless, etc.)
    dmg_matches = dmg_matches_raw  # already computed above

    if not dmg_matches:
        # Only use {@dice} if spell has damageInflict (confirming it's actually a damage spell)
        if spell.get("damageInflict"):
            dmg_matches = DICE_TAG_RE.findall(entries_raw)

    if not dmg_matches:
        return None, 0, None

    # Take the first unique formula
    unique = list(dict.fromkeys(d.strip() for d in dmg_matches))
    formula = unique[0] if unique else None
    avg = _avg_dice(formula) if formula else 0

    # ── Higher-level scaling ──
    scaling_formula = None
    scale_re = re.compile(r'\{@scale(?:damage|dice) ([^}]+)\}')
    scale_matches = scale_re.findall(higher_raw)
    if scale_matches:
        # format: "baseDice|levelRange|perLevelDice"
        parts = scale_matches[0].split("|")
        if len(parts) >= 3:
            scaling_formula = f"{formula}+{parts[2]}/level"

    return formula, avg, scaling_formula


# ─────────────────────────────────────────────
# CLASSIFICATION
# ─────────────────────────────────────────────

CONTROL_WORDS = re.compile(
    r'\b(charm(?:ed)?|frighten(?:ed)?|stun(?:ned)?|paralyze[ds]?|paralyzed|'
    r'restrain(?:ed)?|incapacitate[ds]?|incapacitated|petrif(?:y|ied)|'
    r'blind(?:ed)?|prone|grapple[ds]?|silence[ds]?|deafen(?:ed)?|'
    r'possess(?:ion)?|banish(?:ed)?|sleep|immobilize[ds]?|hold)\b',
    re.IGNORECASE
)
BUFF_WORDS = re.compile(
    r'\b(bonus|advantage|add(?:ing)?|grant|gain(?:ing)?|increase[ds]?|'
    r'resistance to|shield|ward|protect|empower|bless(?:ing)?|inspire[ds]?|'
    r'double|triple|extra|additional|buff|enhance[ds]?|aura|allies)\b',
    re.IGNORECASE
)
UTILITY_WORDS = re.compile(
    r'\b(detect|communicate|travel|invisible|illusion|create[ds]?|summon[ds]?|'
    r'conjure[ds]?|teleport[ds]?|water|food|shelter|lock|unlock|'
    r'comprehend|speak|read|write|ritual|transform[ds]?|shape|alter)\b',
    re.IGNORECASE
)

def classify_spell(spell, desc_text):
    """
    Returns dict with isHealing, isControl, isBuff, isUtility flags.
    Multiple flags can be True simultaneously.
    """
    misc_tags     = spell.get("miscTags", []) or []
    dmg_inflict   = spell.get("damageInflict", []) or []
    heal_tags     = spell.get("healingInflict", []) or []  # rarely present
    cond_inflict  = spell.get("conditionInflict", []) or []

    # Healing: HL miscTag is the most reliable signal
    is_healing = "HL" in misc_tags
    if not is_healing:
        # Fallback: text contains "regain" + "hit point"
        is_healing = bool(
            re.search(r'\bregain\b', desc_text, re.I) and
            re.search(r'\bhit point', desc_text, re.I)
        )

    # Control: use conditionInflict array first, then text scan
    control_conditions = {
        "charmed","frightened","stunned","paralyzed","restrained",
        "incapacitated","petrified","blinded","prone","grappled",
        "unconscious","silenced","deafened","banished","possessed",
        "asleep",
    }
    is_control = bool(set(c.lower() for c in cond_inflict) & control_conditions)
    if not is_control:
        is_control = bool(CONTROL_WORDS.search(desc_text))

    # Buff: no damage, no direct conditions, but grants bonuses/resistance
    is_buff = (
        not dmg_inflict
        and not is_healing
        and bool(BUFF_WORDS.search(desc_text))
    )

    # Utility: detection, transportation, construction, communication
    is_utility = (
        not dmg_inflict
        and not is_healing
        and not is_control
        and bool(UTILITY_WORDS.search(desc_text))
    )
    # Also tag summoning spells
    summon_tags = spell.get("summonCreature") or spell.get("summonSpell")
    if summon_tags:
        is_utility = True

    return {
        "isHealing": is_healing,
        "isControl": is_control,
        "isBuff":    is_buff,
        "isUtility": is_utility,
    }


# ─────────────────────────────────────────────
# AOE PARSING
# ─────────────────────────────────────────────

AOE_SIZE_PATTERNS = [
    re.compile(r'(\d+)[- ]foot[- ]radius', re.I),
    re.compile(r'(\d+)[- ]foot[- ](sphere|cone|cube|line|cylinder|hemisphere|radius|square|circle)', re.I),
    re.compile(r'(sphere|cone|cube|line|cylinder|hemisphere)\s+(?:of\s+)?(\d+)', re.I),
    re.compile(r'(\d+) by (\d+)[- ]foot', re.I),
    re.compile(r'(\d+)[- ]foot[- ]wide', re.I),
    re.compile(r'(\d+)[- ]foot[- ]long', re.I),
]

SHAPE_KEYWORDS = re.compile(
    r'\b(sphere|cone|cube|cylinder|hemisphere|line|radius|wall|square|circle)\b',
    re.I
)


def parse_aoe(spell, desc_text):
    """
    Returns (is_aoe, aoe_shape, aoe_size_str, est_targets).
    """
    area_tags = spell.get("areaTags", []) or []

    # Single-target and multi-target tags alone do NOT make a spell AoE
    non_aoe_only = all(t in ("N", "ST", "MT") for t in area_tags)

    # If we have actual area tags, resolve shape
    shape    = None
    est_tgts = 1
    is_aoe   = False

    for tag in area_tags:
        if tag in AREA_TAG_MAP:
            candidate_shape, candidate_est = AREA_TAG_MAP[tag]
            if candidate_shape in AOE_SHAPES:
                shape    = candidate_shape
                est_tgts = candidate_est
                is_aoe   = True
                break
    # MT without an AOE tag: treat as multi-target (3 est, still is_aoe for our purposes)
    if not is_aoe and "MT" in area_tags and not any(t in ("N","ST") for t in area_tags):
        shape    = None
        est_tgts = 3
        is_aoe   = True

    # Even if no area_tags, detect from range type
    range_obj  = spell.get("range", {})
    range_type = range_obj.get("type", "")
    if not is_aoe and range_type in ("cone","cube","line","sphere","hemisphere","cylinder","radius"):
        shape  = range_type
        is_aoe = True
        est_tgts = AREA_TAG_MAP.get(range_type.upper()[0], (range_type, 3))[1] if range_type[0].upper() in AREA_TAG_MAP else 3

    # AOE size string: scan description text first (most accurate),
    # then fall back to range distance for self-centered AoE spells
    aoe_size = None
    for pat in AOE_SIZE_PATTERNS:
        m = pat.search(desc_text)
        if m:
            aoe_size = m.group(0).strip()
            break

    # Fall back to range distance only for range types that *are* the AoE
    # (e.g. range.type == "cone"), not point-origin spells like Fireball
    if not aoe_size and is_aoe and shape and range_type in ("cone","cube","line","sphere","hemisphere","cylinder","radius"):
        dist = range_obj.get("distance", {}) if isinstance(range_obj.get("distance"), dict) else {}
        amt  = dist.get("amount")
        if amt:
            aoe_size = f"{amt}-foot-{shape}" if shape != "radius" else f"{amt}-foot-radius"

    # Determine shape from text if still None
    if is_aoe and not shape:
        m = SHAPE_KEYWORDS.search(desc_text)
        if m:
            shape = m.group(1).lower()

    return is_aoe, shape, aoe_size, est_tgts


# ─────────────────────────────────────────────
# ATTACK TYPE
# ─────────────────────────────────────────────

def parse_attack_type(spell):
    """Return 'melee', 'ranged', or None."""
    atk = spell.get("spellAttack", []) or []
    if "M" in atk:
        return "melee"
    if "R" in atk:
        return "ranged"
    return None


# ─────────────────────────────────────────────
# TAGS BUILDER
# ─────────────────────────────────────────────

def build_tags(spell, flags, is_aoe, damage_formula, attack_type):
    tags = []
    dmg_inflict = spell.get("damageInflict", []) or []

    if dmg_inflict or damage_formula:
        tags.append("damage")
    if is_aoe:
        tags.append("aoe")
    if flags["isHealing"]:
        tags.append("healing")
    if flags["isControl"]:
        tags.append("control")
    if flags["isBuff"]:
        tags.append("buff")
    if flags["isUtility"]:
        tags.append("utility")
    if attack_type:
        tags.append(f"{attack_type}-attack")
    if spell.get("savingThrow"):
        tags.append("saving-throw")
    if is_ritual(spell):
        tags.append("ritual")
    if spell.get("concentration"):
        # caught below via duration
        pass
    # School tag
    school_code = spell.get("school", "")
    school_name = SCHOOL_MAP.get(school_code, "")
    if school_name:
        tags.append(school_name.lower())

    return sorted(set(tags))


# ─────────────────────────────────────────────
# MAIN SPELL BUILDER
# ─────────────────────────────────────────────

def build_spell(spell, sources_map):
    name   = spell.get("name", "")
    source = spell.get("source", "")
    level  = spell.get("level", 0)

    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    slug = f"{slug}-{source.lower()}" if source else slug

    source_upper = source.upper()
    source_type  = "official" if source_upper in OFFICIAL_SOURCES else "third-party"

    school_code = spell.get("school", "")
    school      = SCHOOL_MAP.get(school_code, school_code)

    casting_time = parse_casting_time(spell.get("time", []))
    range_str    = parse_range(spell.get("range"))
    duration_str, concentration = parse_duration(spell.get("duration", []))
    components_str = parse_components(spell.get("components", {}))
    ritual = is_ritual(spell)

    # Description: combine main entries
    all_entries = list(spell.get("entries", []))
    desc = strip_entries(all_entries).strip()
    # Truncate to reasonable length for app use
    if len(desc) > 2000:
        desc = desc[:2000].rsplit(" ", 1)[0] + "…"

    # Classes from sources_map
    spell_sources = sources_map.get(source_upper, {})
    class_entries = spell_sources.get(name, {}).get("class", [])
    # Deduplicate by class name (prefer PHB/XPHB source, then any)
    seen_classes = {}
    for ce in class_entries:
        cname = ce.get("name", "")
        csrc  = ce.get("source", "")
        if cname and cname not in seen_classes:
            seen_classes[cname] = csrc
        elif cname and csrc in ("PHB", "XPHB"):
            seen_classes[cname] = csrc
    classes = sorted(seen_classes.keys())

    # Damage
    formula, avg_dmg, scaling = extract_damage_formula(spell)

    # Save
    saves = spell.get("savingThrow", []) or []
    save_type = saves[0].lower() if saves else None

    # Attack type
    attack_type = parse_attack_type(spell)

    # AOE
    is_aoe, aoe_shape, aoe_size, est_targets = parse_aoe(spell, desc)

    # Classification
    flags = classify_spell(spell, desc)

    # Tags
    tags = build_tags(spell, flags, is_aoe, formula, attack_type)

    # Damage types
    dmg_types = [d.lower() for d in (spell.get("damageInflict") or [])]

    return {
        "name":          name,
        "slug":          slug,
        "source":        source,
        "sourceType":    source_type,
        "level":         level,
        "school":        school,
        "castingTime":   casting_time,
        "ritual":        ritual,
        "range":         range_str,
        "components":    components_str,
        "duration":      duration_str,
        "concentration": concentration,
        "classes":       classes,
        "description":   desc,
        "damageType":    dmg_types,
        "saveType":      save_type,
        "attackType":    attack_type,
        "damageFormula": formula,
        "avgDamage":     avg_dmg,
        "scalingFormula":scaling,
        "isAoE":         is_aoe,
        "aoeShape":      aoe_shape,
        "aoeSize":       aoe_size,
        "estTargets":    est_targets,
        "isHealing":     flags["isHealing"],
        "isControl":     flags["isControl"],
        "isBuff":        flags["isBuff"],
        "isUtility":     flags["isUtility"],
        "tags":          tags,
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("D&D 5e Spell Data Build")
    print("=" * 60)

    # Verify spells dir
    if not SPELLS_DIR.exists():
        print(f"\nERROR: Could not find spells folder at:\n  {SPELLS_DIR}")
        print("\nMake sure ETOOLS_ROOT points to the root of 5etools-src-main")
        print("(the folder containing 'data/').")
        sys.exit(1)

    print(f"\n5etools root:  {ETOOLS_ROOT}")
    print(f"Spells dir:    {SPELLS_DIR}")
    print(f"Output file:   {OUTPUT_FILE}")

    # ── Load sources.json ──
    sources_path = SPELLS_DIR / "sources.json"
    sources_map  = {}
    if sources_path.exists():
        print("\nLoading sources.json...")
        with open(sources_path, encoding="utf-8") as f:
            sources_map = json.load(f)
        total_class_entries = sum(
            len(v) for src in sources_map.values() for v in (src.values() if isinstance(src, dict) else [])
        )
        print(f"  Loaded class associations for {sum(len(v) for v in sources_map.values())} spells "
              f"across {len(sources_map)} sources")
    else:
        print("  Warning: sources.json not found — classes will be empty")

    # ── Load all spell files ──
    spell_files = sorted(glob.glob(str(SPELLS_DIR / "spells-*.json")))
    print(f"\nLoading {len(spell_files)} spell files...")

    raw_spells = []
    for fpath in spell_files:
        fname = Path(fpath).name
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            spells_in_file = data.get("spell", [])
            print(f"  {fname}: {len(spells_in_file)} spells")
            raw_spells.extend(spells_in_file)
        except Exception as e:
            print(f"  Warning: could not load {fname}: {e}")

    print(f"\nTotal raw spell entries loaded: {len(raw_spells)}")

    # ── Deduplicate by name+source ──
    seen       = {}
    duplicates = 0
    for s in raw_spells:
        key = (s.get("name", "").lower(), s.get("source", "").upper())
        if key in seen:
            duplicates += 1
        else:
            seen[key] = s

    unique_spells = list(seen.values())
    print(f"After dedup: {len(unique_spells)} unique spells ({duplicates} duplicates removed)")

    # ── Build output ──
    print("\nBuilding spell records...")
    output = []
    errors = 0
    for i, spell in enumerate(unique_spells):
        if i % 200 == 0 and i > 0:
            print(f"  Processed {i}/{len(unique_spells)}...")
        try:
            built = build_spell(spell, sources_map)
            if built["name"]:
                output.append(built)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error on {spell.get('name','?')}/{spell.get('source','?')}: {e}")

    # ── Sort by level then name ──
    output.sort(key=lambda s: (s["level"], s["name"].lower()))

    print(f"\nTotal spells built: {len(output)}  (errors: {errors})")

    # ── Summary stats ──
    by_level  = defaultdict(int)
    by_school = defaultdict(int)
    for s in output:
        by_level[s["level"]]   += 1
        by_school[s["school"]] += 1

    has_damage  = sum(1 for s in output if s.get("damageFormula") or s.get("damageType"))
    has_aoe     = sum(1 for s in output if s.get("isAoE"))
    has_healing = sum(1 for s in output if s.get("isHealing"))
    has_control = sum(1 for s in output if s.get("isControl"))
    has_buff    = sum(1 for s in output if s.get("isBuff"))
    has_utility = sum(1 for s in output if s.get("isUtility"))
    has_classes = sum(1 for s in output if s.get("classes"))
    official    = sum(1 for s in output if s.get("sourceType") == "official")
    third_party = sum(1 for s in output if s.get("sourceType") == "third-party")

    print("\nBy level:")
    for lvl in sorted(by_level):
        label = "Cantrips" if lvl == 0 else f"Level {lvl}"
        print(f"  {label:10s}: {by_level[lvl]}")

    print("\nBy school:")
    for school in sorted(by_school, key=lambda x: by_school[x], reverse=True):
        print(f"  {school:15s}: {by_school[school]}")

    print(f"\nClassification:")
    print(f"  Damage spells:  {has_damage}")
    print(f"  AoE spells:     {has_aoe}")
    print(f"  Healing spells: {has_healing}")
    print(f"  Control spells: {has_control}")
    print(f"  Buff spells:    {has_buff}")
    print(f"  Utility spells: {has_utility}")
    print(f"  Has classes:    {has_classes}")

    print(f"\nSource type:")
    print(f"  Official:       {official}")
    print(f"  Third-party:    {third_party}")

    # ── Write output ──
    print(f"\nWriting {OUTPUT_FILE}...")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"Done!  {OUTPUT_FILE.name}  ({size_kb:.0f} KB,  {len(output)} spells)")

    # ── Spot-check a few known spells ──
    print("\nSpot checks:")
    spot_names = {"Fireball", "Cure Wounds", "Hold Person", "Eldritch Blast", "Bless"}
    for s in output:
        if s["name"] in spot_names and s["source"] in ("PHB", "XPHB"):
            spot_names.discard(s["name"])
            dmg_str = str(s['damageFormula']) if s['damageFormula'] else "—"
            print(f"  {s['name']:20s} Lv{s['level']}  {s['school']:15s}  "
                  f"dmg={dmg_str:8s}  avg={s['avgDamage']:3}  "
                  f"aoe={s['isAoE']}  heal={s['isHealing']}  ctrl={s['isControl']}  "
                  f"classes={s['classes'][:4]}")
            if not spot_names:
                break


if __name__ == "__main__":
    main()
