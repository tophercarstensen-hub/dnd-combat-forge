#!/usr/bin/env python3
"""
Monster Environment Enricher
=============================
Run this on your local machine:

  1. Make sure Python 3.7+ is installed (no extra packages needed)
  2. Set your API key at the top of this file (API_KEY = "sk-ant-...")
  3. Set INPUT_FILE to the path of your monsters_all.json
  4. Run:  python enrich_environments_local.py

Takes about 3-5 minutes. Progress is saved as it runs — safe to stop and restart.
Output:  monsters_all_enriched.json  (same folder as this script)
"""

import json, urllib.request, urllib.error, time, os
from collections import defaultdict

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIGURE THESE TWO LINES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_KEY    = "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"
INPUT_FILE = r"C:\Users\tophe\OneDrive\Documents\DND Applications\Combat Calc\monsters_all.json"        # path to your file
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OUTPUT_FILE   = "monsters_all_enriched.json"
PROGRESS_FILE = "enrich_progress.json"
API_URL       = "https://api.anthropic.com/v1/messages"
MODEL         = "claude-haiku-4-5-20251001"  # fast + cheap, plenty smart for this task
BATCH_SIZE    = 20
DELAY         = 0.4   # seconds between API calls

VALID_ENVS = frozenset([
    "arctic","cave","coastal","desert","dungeon","forest",
    "grassland","hill","mountain","swamp","underdark","urban","underwater","any"
])

# ── Name keyword heuristics ──────────────────────────────────────────────────
NAME_KEYWORDS = [
    (["shark","dolphin","whale","kraken","merfolk","sea serpent","sea hag","sahuagin",
      "triton","mariner","aboleth spawn","deep scion"],                                ["underwater","coastal"]),
    (["deep dragon","deep gnome","mind flayer","illithid","aboleth","duergar","myconid",
      "beholder","drider","drow","svirfneblin","hook horror","kuo-toa","grell",
      "roper","cloaker","underdark"],                                                  ["underdark"]),
    (["frost giant","ice ","frost ","winter ","yeti","mammoth","polar bear",
      "remorhaz","wendigo"],                                                           ["arctic"]),
    (["sand ","desert","mummy","gnoll","sphinx","jackal","blue dragon",
      "brass dragon","scorpion","lamia"],                                              ["desert"]),
    (["swamp","bog","lizardfolk","bullywug","black dragon","will-o'-wisp",
      "crocodile","hydra"],                                                            ["swamp"]),
    (["forest","dryad","treant","centaur","green dragon","satyr","pixie",
      "sprite","owlbear","displacer beast","blink dog"],                               ["forest"]),
    (["aarakocra","mountain","griffon","giant eagle","stone giant","cloud giant",
      "roc","azer","galeb duhr","wyvern","peryton","manticore"],                       ["mountain","hill"]),
    (["cave","troglodyte","minotaur","gelatinous","purple worm","darkmantle",
      "piercer","goblin","hobgoblin","bugbear","kobold"],                              ["dungeon","cave"]),
    (["vampire","lich","wraith","wight","ghoul","zombie","skeleton","specter",
      "ghost","banshee","revenant"],                                                   ["dungeon","urban"]),
    (["balor","marilith","nalfeshnee","glabrezu","hezrou","vrock","erinyes",
      "pit fiend","bone devil","chain devil","githyanki","githzerai","modron","slaad"],["any"]),
    (["noble","merchant","acolyte","archmage","spy","veteran","commoner",
      "assassin","bandit captain","gladiator"],                                        ["urban"]),
]

TYPE_FALLBACKS = {
    "undead":           ["dungeon","urban"],
    "construct":        ["dungeon","urban"],
    "celestial":        ["any"],
    "fiend":            ["any"],
    "aberration":       ["underdark","dungeon"],
    "ooze":             ["dungeon","cave"],
    "plant":            ["forest","swamp","grassland"],
    "elemental":        ["any"],
    "fey":              ["forest"],
    "giant":            ["mountain","hill","grassland"],
    "dragon":           ["mountain","any"],
    "humanoid":         ["urban"],
    "monstrosity":      ["dungeon","forest","any"],
    "beast":            ["forest","grassland"],
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_type(m):
    t = m.get("type","")
    return (t.get("type","") if isinstance(t,dict) else str(t)).lower()

def heuristic(m):
    nl = m.get("name","").lower()
    for keywords, envs in NAME_KEYWORDS:
        if any(k in nl for k in keywords):
            return envs
    mt = get_type(m)
    for type_key, envs in TYPE_FALLBACKS.items():
        if type_key in mt:
            return envs
    return ["any"]

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"done_keys": {}, "pass2_done": False}

def save_progress(p):
    with open(PROGRESS_FILE,"w") as f:
        json.dump(p,f)

def call_api(prompt):
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 1500,
        "messages": [{"role":"user","content":prompt}]
    }).encode()
    req = urllib.request.Request(API_URL, data=payload, headers={
        "Content-Type":       "application/json",
        "x-api-key":          API_KEY,
        "anthropic-version":  "2023-06-01",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["content"][0]["text"]

def parse_response(text):
    s,e = text.find("{"), text.rfind("}")+1
    if s<0 or e<=0: return {}
    try:
        raw = json.loads(text[s:e])
        out = {}
        for k,v in raw.items():
            envs = [x.lower().strip() for x in (v if isinstance(v,list) else [v])]
            envs = [x for x in envs if x in VALID_ENVS]
            if envs: out[k] = envs
        return out
    except: return {}

def make_prompt(items):
    body = "{" + ",\n".join(
        f'"{gid}": {{"name":{json.dumps(name)}, "type":{json.dumps(mtype)}, "lore":{json.dumps(lore[:400])}}}'
        for gid,name,mtype,lore in items
    ) + "}"
    return f"""You are a D&D expert. Assign environment tags to each monster based on its lore.

Valid tags ONLY: arctic, cave, coastal, desert, dungeon, forest, grassland, hill, mountain, swamp, underdark, urban, underwater, any

Rules:
- "any" = widespread/planar/summoned creatures
- "dungeon" = ruins, tombs, ancient structures
- "cave" = natural underground spaces
- "underdark" = deep underground (drow cities, mind flayer colonies, etc.)
- Assign 1-4 tags. Be specific when lore clearly indicates habitat.

Monsters:
{body}

Reply with ONLY a JSON object: {{"0":["forest","hill"],"1":["underdark"],"2":["any"]}}"""

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Validate config
    if API_KEY == "PASTE_YOUR_API_KEY_HERE":
        print("ERROR: You need to set your API_KEY at the top of this script.")
        return
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: Input file not found: {INPUT_FILE}")
        return

    print(f"Loading {INPUT_FILE}...")
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    print(f"Loaded {len(data):,} monsters.")

    slug_map = {m["slug"]: m for m in data}
    progress = load_progress()
    done_keys = progress["done_keys"]

    # ── Pass 1: API inference from lore ──────────────────────────────────────
    needs_env = [m for m in data if not m.get("environment")]
    has_lore  = [m for m in needs_env if m.get("lore",{}).get("paragraphs")]
    no_lore   = [m for m in needs_env if not m.get("lore",{}).get("paragraphs")]

    # Group by shared lore
    groups = defaultdict(list)
    for m in has_lore:
        key = " ".join(m["lore"]["paragraphs"])[:150]
        groups[key].append(m)

    pending = [(k,ms) for k,ms in groups.items() if k not in done_keys]
    total_batches = (len(pending)+BATCH_SIZE-1)//BATCH_SIZE

    print(f"\nPass 1: {len(has_lore):,} monsters with lore → {len(groups):,} groups → {total_batches} API batches")
    print(f"  Already done: {len(done_keys):,} groups   Pending: {len(pending):,} groups")
    print(f"Pass 2: {len(no_lore):,} monsters → heuristics\n")

    api_ok = api_fb = batch_num = 0

    for i in range(0, len(pending), BATCH_SIZE):
        batch_groups = pending[i:i+BATCH_SIZE]
        batch_num += 1
        items = [
            (str(i+j), ms[0]["name"], get_type(ms[0]), " ".join(ms[0]["lore"]["paragraphs"]))
            for j,(_,ms) in enumerate(batch_groups)
        ]
        pct = int(batch_num/total_batches*100)
        print(f"  [{pct:3d}%] Batch {batch_num}/{total_batches}...", end=" ", flush=True)

        try:
            result_text = call_api(make_prompt(items))
            env_map = parse_response(result_text)
            for j,(lore_key,ms) in enumerate(batch_groups):
                envs = env_map.get(str(i+j))
                if envs:
                    for m in ms: slug_map[m["slug"]]["environment"] = envs
                    done_keys[lore_key] = envs
                    api_ok += len(ms)
                else:
                    for m in ms: slug_map[m["slug"]]["environment"] = heuristic(m)
                    done_keys[lore_key] = None
                    api_fb += len(ms)
            assigned = sum(1 for gid in [str(i+j) for j in range(len(batch_groups))] if gid in env_map)
            print(f"✓  {assigned}/{len(batch_groups)} from API")
        except Exception as e:
            print(f"✗  ERROR: {e}  →  heuristics")
            for _,ms in batch_groups:
                for m in ms: slug_map[m["slug"]]["environment"] = heuristic(m)
                api_fb += len(ms)

        progress["done_keys"] = done_keys
        save_progress(progress)
        time.sleep(DELAY)

    # ── Pass 2: heuristics for no-lore monsters ───────────────────────────────
    if not progress.get("pass2_done"):
        print(f"\nPass 2: heuristics for {len(no_lore):,} monsters with no lore...")
        for m in no_lore:
            slug_map[m["slug"]]["environment"] = heuristic(m)
        progress["pass2_done"] = True
        save_progress(progress)
        print("  Done.\n")

    # ── Summary & save ────────────────────────────────────────────────────────
    final = list(slug_map.values())
    enriched = sum(1 for m in final if m.get("environment"))
    print(f"Summary")
    print(f"  Before: 813 had environments")
    print(f"  After:  {enriched:,} have environments")
    print(f"  API-assigned: {api_ok:,}   Heuristic: {api_fb+len(no_lore):,}")
    print(f"\nSaving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE,"w") as f:
        json.dump(final, f, separators=(",",":"))
    mb = os.path.getsize(OUTPUT_FILE)/1024/1024
    print(f"Saved. {mb:.1f} MB")
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
    print("\nAll done! Upload monsters_all_enriched.json to your Drive.")

if __name__ == "__main__":
    main()
