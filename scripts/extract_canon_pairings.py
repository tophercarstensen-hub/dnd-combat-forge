#!/usr/bin/env python3
"""
Mine monsters_final.json's existing `lore` text for mentions of OTHER
monster names, to find candidate "canonical lore pairings" (githyanki <->
red dragon, etc.) that no type/family/environment/source tag captures.

Does NOT touch the roll20-export crawl -- that crawl is per-monster
character-sheet pages, already fully absorbed into `lore`; there's no
separate narrative/encounter-table text to go back and mine.

Filtering (tuned against a first-pass human review -- see canon_pairings_001
in review/completed/ for the labeled examples that drove each rule):
  - Word-boundary name matching only (not substring).
  - Generic NPC-role names (Guard, Cultist, ...) excluded outright.
  - A large stoplist of common English words that also happen to be some
    monster's literal name (Fire, Coral, Gleam, Solar, ...) -- these matched
    constantly inside unrelated prose ("smooth like a salamander's hide").
  - "The X" / "A X" names excluded when X alone is in that stoplist (The
    Flesh, etc.) -- these read as descriptive phrases, not proper nouns.
  - Simile/comparison context ("resembles a", "like a", "reminiscent of",
    "stuff of") and predation/food context ("feeds on", "favorite food",
    "prey on") immediately before a match are excluded from evidence --
    a dragon's hide being compared to a salamander's, or an aboleth's meal,
    isn't a faction pairing.
  - Adventure-hook / roll-table sections are stripped from lore text before
    scanning (detected via an "Adventure Hook" heading or pipe-delimited
    numbered table rows) -- these enumerate random creatures as DM prompts,
    not real relationships.
  - Age/tier modifier words (Adult/Young/Ancient/Wyrmling/Greater/... plus
    Transcendent/Primordial/Exalted) are stripped from both ends of a name
    to get a "family root" for aggregation and self-mention exclusion, so
    e.g. "Transcendent Lunarchidna" doesn't get flagged as a partner of
    plain "Lunarchidna".
  - Requires support from >=2 distinct source monsters before a pairing is
    proposed for review.
  - Already-reviewed pairs (APPROVE or REJECT, from any prior
    canon_pairings_NNN.json in pending/ or completed/) are excluded from
    future batches so you never have to re-decide the same pair.

Writes review/pending/canon_pairings_<NNN>.json (binary_classify, next
sequence number) for human review -- this script only proposes candidates,
it never edits CANON_PAIRINGS in combat_forge.html itself. See
review/schema.md.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MONSTERS_PATH = HERE / "monsters_final.json"
REVIEW_DIR = HERE.parent / "review"

# ── Generic NPC/role names -- exact-name exclusion, either side of a pair ──
ROLE_STOPLIST = {
    "guard", "guards", "thug", "thugs", "bandit", "bandits", "cultist",
    "cultists", "acolyte", "acolytes", "commoner", "commoners", "noble",
    "nobles", "veteran", "veterans", "knight", "knights", "spy", "spies",
    "scout", "scouts", "priest", "priests", "mage", "mages", "wizard",
    "wizards", "warrior", "warriors", "soldier", "soldiers", "apprentice",
    "apprentices", "gladiator", "gladiators", "assassin", "assassins",
    "berserker", "berserkers", "tough", "toughs", "brute", "brutes",
    "peasant", "peasants", "merchant", "merchants", "archer", "archers",
    "swashbuckler", "swashbucklers", "captain", "captains", "champion",
    "champions", "guardian", "guardians", "warlord", "warlords",
}

# ── Common English words that are ALSO some monster's literal name.
# Confirmed false-positive pattern from human review: Fire, Coral, Gleam,
# Solar, Flesh, Nightmare all matched inside ordinary prose having nothing
# to do with the actual creature of that name. Genuine fantasy proper nouns
# (Derro, Demilich, Acererak) are NOT in this list and pass through fine --
# this targets ordinary-dictionary-word collisions specifically.
COMMON_WORD_STOPLIST = {
    "fire", "coral", "gleam", "solar", "flesh", "nightmare", "stone", "ash",
    "ember", "embers", "blood", "bone", "bones", "iron", "steel", "silver",
    "gold", "crystal", "night", "star", "stars", "sea", "wood", "root",
    "roots", "thorn", "thorns", "web", "webs", "wing", "wings", "horn",
    "horns", "shell", "scale", "scales", "mist", "fog", "rain", "snow",
    "thunder", "lightning", "spark", "sparks", "flame", "flames", "smoke",
    "dust", "sand", "salt", "moss", "vine", "vines", "briar", "briars",
    "shadow", "shadows", "storm", "storms", "wind", "winds", "ice", "frost",
    "moon", "sun", "sky", "cloud", "clouds", "river", "lake", "stream",
    "leaf", "leaves", "branch", "branches", "petal", "petals", "thistle",
    "spore", "spores", "spike", "spikes", "claw", "claws", "fang", "fangs",
    "tooth", "teeth", "tail", "eye", "eyes", "heart", "hearts", "soul",
    "souls", "spirit", "spirits", "ghost", "ghosts", "grave", "graves",
    "tomb", "tombs", "crypt", "crypts", "ruin", "ruins", "swamp", "marsh",
    "bog", "cave", "cavern", "pit", "pits", "abyss", "void", "chaos",
    "order", "light", "dark", "darkness", "brightness", "glow", "glimmer",
    "shine", "shard", "shards", "gem", "gems", "jewel", "jewels", "coin",
    "coins", "gold", "treasure", "trap", "traps", "wall", "walls", "door",
    "doors", "tower", "towers", "castle", "bridge", "gate", "gates",
}

_ARTICLE_RE = re.compile(r"^(the|a|an)\s+(.+)$", re.I)

# Phrases that mean "the following name is a comparison, not a partnership" --
# checked in a short window immediately before a match.
NEGATIVE_CONTEXT_RE = re.compile(
    r"(resembl\w*|reminiscent of|similar to|like an?\b|stuff of|"
    r"compared to|as if it were an?\b|akin to)\s*$",
    re.I,
)
FOOD_CONTEXT_RE = re.compile(
    r"(feeds? on|favou?rite food (?:is|was)|prey(?:s)? (?:on|upon)|"
    r"diet (?:of|consists)|hunts? .{0,20}for food|eats?|devours?)\s*$",
    re.I,
)

# Roll-table / adventure-hook sections enumerate random creatures as DM
# prompts, not real relationships -- strip from lore before scanning.
ADVENTURE_HOOK_RE = re.compile(r"adventure hooks?\s*:?", re.I)
TABLE_ROW_RE = re.compile(r"\n?\s*\d{1,2}\s*\|[^\n]*", re.M)

# ── Age/tier modifier words stripped from either end of a name to get a
# "family root" for aggregation and self-mention exclusion.
_AGE_WORDS = (r"ancient|adult|young|wyrmling|greater|lesser|elder|juvenile|"
              r"old|great|giant|huge|large|small|tiny|transcendent|"
              r"primordial|exalted|corrupted|awakened|true")
AGE_PREFIX_RE = re.compile(rf"^(?:{_AGE_WORDS})\s+", re.I)
AGE_SUFFIX_RE = re.compile(rf"\s+(?:{_AGE_WORDS})$", re.I)


def family_root(name: str) -> str:
    n = name.lower().strip()
    prev = None
    while prev != n:
        prev = n
        n = AGE_PREFIX_RE.sub("", n)
        n = AGE_SUFFIX_RE.sub("", n)
    return n.strip()


def is_common_word_name(name: str) -> bool:
    """True if this candidate name is (or is 'The'/'A' + ) a common English
    word rather than a distinctive proper noun."""
    n = name.lower().strip()
    if n in COMMON_WORD_STOPLIST:
        return True
    m = _ARTICLE_RE.match(n)
    if m and m.group(2) in COMMON_WORD_STOPLIST:
        return True
    return False


def clean_lore(lore: str) -> str:
    """Strip adventure-hook / roll-table sections before scanning."""
    m = ADVENTURE_HOOK_RE.search(lore)
    if m:
        lore = lore[:m.start()]
    lore = TABLE_ROW_RE.sub(" ", lore)
    return lore


def load_prior_decisions() -> set:
    """(root_a, root_b) pairs already decided (any decision) in any prior
    canon_pairings_NNN.json, pending or completed -- skip these forever."""
    decided = set()
    for subdir in ("pending", "completed"):
        d = REVIEW_DIR / subdir
        if not d.exists():
            continue
        for f in sorted(d.glob("canon_pairings_*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for item in data.get("items", []):
                if item.get("user_decision") is None:
                    continue  # not actually decided, still open for review
                name = item.get("name", "")
                if "↔" in name:
                    a, b = name.split("↔")
                    decided.add(tuple(sorted([a.strip().lower(), b.strip().lower()])))
    return decided


def next_sequence_number() -> int:
    existing = list((REVIEW_DIR / "pending").glob("canon_pairings_*.json")) + \
               list((REVIEW_DIR / "completed").glob("canon_pairings_*.json"))
    nums = []
    for f in existing:
        m = re.search(r"canon_pairings_(\d+)\.json$", f.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def main():
    monsters = json.loads(MONSTERS_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(monsters)} monsters")

    prior_decisions = load_prior_decisions()
    print(f"Already-decided pairs to skip: {len(prior_decisions)}")

    candidate_names = set()
    junk_skipped = 0
    common_word_skipped = 0
    for m in monsters:
        name = (m.get("name") or "").strip()
        if len(name) < 5:
            continue
        if name.lower() in ROLE_STOPLIST:
            continue
        if is_common_word_name(name):
            common_word_skipped += 1
            continue
        type_str = m.get("type") if isinstance(m.get("type"), str) else (m.get("type") and "x")
        if not (type_str or "").strip() and not str(m.get("cr") or "").strip():
            junk_skipped += 1
            continue
        candidate_names.add(name)
    print(f"Skipped {junk_skipped} stat-less junk entries, {common_word_skipped} common-word names from candidacy")
    print(f"Candidate names: {len(candidate_names)}")

    sorted_names = sorted(candidate_names, key=len, reverse=True)
    compiled = [(n, re.compile(r"\b" + re.escape(n) + r"\b", re.I)) for n in sorted_names]

    pair_support = defaultdict(set)
    pair_evidence = {}

    checked = 0
    for m in monsters:
        lore = m.get("lore")
        if not isinstance(lore, str) or len(lore) < 150:
            continue
        src_name = m.get("name") or ""
        src_root = family_root(src_name)
        checked += 1
        lore_clean = clean_lore(lore)
        lore_lower = lore_clean.lower()
        for cand_name, rx in compiled:
            cand_root = family_root(cand_name)
            if cand_root == src_root:
                continue
            if cand_name.lower() not in lore_lower:
                continue
            match = rx.search(lore_clean)
            if not match:
                continue
            window_start = max(0, match.start() - 40)
            before = lore_clean[window_start:match.start()]
            if NEGATIVE_CONTEXT_RE.search(before) or FOOD_CONTEXT_RE.search(before):
                continue
            key = tuple(sorted([src_root, cand_root]))
            if key in prior_decisions:
                continue
            pair_support[key].add(src_name)
            if key not in pair_evidence:
                start = max(0, match.start() - 80)
                excerpt = lore_clean[start:match.end() + 80].strip()
                pair_evidence[key] = (src_name, excerpt)

    print(f"Scanned lore text on {checked} monsters")
    print(f"Raw candidate pairs found: {len(pair_support)}")

    MIN_SUPPORT = 2
    qualifying = [(k, v) for k, v in pair_support.items() if len(v) >= MIN_SUPPORT]
    qualifying.sort(key=lambda kv: -len(kv[1]))
    print(f"Pairs with support >= {MIN_SUPPORT}: {len(qualifying)}")

    seq = next_sequence_number()
    out_path = REVIEW_DIR / "pending" / f"canon_pairings_{seq:03d}.json"

    CAP = 150
    items = []
    for i, (key, supporters) in enumerate(qualifying[:CAP]):
        a, b = key
        src_name, excerpt = pair_evidence[key]
        items.append({
            "id": f"pair_{i:03d}",
            "name": f"{a.title()} ↔ {b.title()}",
            "source": f"{len(supporters)} monster(s), e.g. {src_name}",
            "text": excerpt,
            "algorithm_proposed": "APPROVE",
            "algorithm_reasoning": (
                f"{len(supporters)} distinct monster lore entries mention "
                f"\"{b}\" (or vice versa) by name -- e.g. {src_name}'s lore: "
                f"…{excerpt}…"
            ),
            "user_decision": None,
            "user_note": None,
            "reviewed_at": None,
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    task = {
        "task_id": f"canon_pairings_{seq:03d}",
        "task_type": "binary_classify",
        "question": "Is this a real canonical D&D lore pairing worth adding to Combat Forge's theme-matching (CANON_PAIRINGS in combat_forge.html)?",
        "context": (
            "Combat Forge's Seed Monster / Themed Boss generator scores candidate "
            "monsters by shared type/family/environment/source book. Some real D&D "
            "pairings (githyanki riding red dragons, etc.) share none of those tags "
            "-- the connection is pure lore. This batch was auto-extracted by scanning "
            "every monster's existing lore text for mentions of another monster's name "
            "(word-boundary matched; generic NPC-role names and common-English-word "
            "monster names excluded; simile/food context excluded; adventure-hook roll "
            "tables stripped before scanning; self-mentions of a monster's own "
            "age/tier variants excluded; requires >=2 independent monster entries "
            "mentioning the same partner). Already-decided pairs from prior batches "
            "are never re-shown. APPROVE means: add this pair to CANON_PAIRINGS so the "
            "two families score a theme match even with no shared type/environment tag. "
            "REJECT means: noise (coincidental overlap, description not partnership, "
            "too generic, etc)."
        ),
        "created_at": "2026-08-24T00:00:00Z",
        "options": ["APPROVE", "REJECT"],
        "items": items,
        "completed_at": None,
    }
    out_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path} ({len(items)} candidate pairings for review)")

    if len(qualifying) > CAP:
        print(f"Note: {len(qualifying) - CAP} additional lower-support pairs not included in this batch.")


if __name__ == "__main__":
    main()
