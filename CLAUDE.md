# Combat Forge — Project Context

## What This Is
A single-file D&D 5e encounter simulator and combat calculator for Dungeon Masters.
Built as a self-contained HTML app that can be shared and run locally in a browser.
Current version: **Combat Forge v15.1** (displayed in the app's top bar; filename is unversioned).

Versioning follows semver-ish:
- Major bump (v13 → v14): full UI restructures, big feature additions
- Minor bump (v14 → v14.1): smaller features, visible changes, batched bug fixes
- Patch bump (v14.1 → v14.1.1): silent bug fixes, no behavior change
Update both `<title>` and `.tb-sub` text in `combat_forge.html` when bumping.

## Repository
https://github.com/tophercarstensen-hub/dnd-combat-forge

## File Structure
```
Combat Calc/
├── combat_forge.html                   # Stripped source (~213KB) — EDIT THIS
├── combat_forge_baked.html             # Bake output (~17MB) — TEST THIS
├── monsters_final.json                 # Production monster DB (7,304 monsters)
├── bake_monsters.py                    # Bakes monsters_final.json into combat_forge.html
├── CLAUDE.md                           # This file
├── scripts/
│   ├── build_monsters_enriched.py      # Rebuilds data/monsters_all_enriched_v2.json from 5etools
│   └── merge_monsters.py               # Merges v2 + 3rd-party → monsters_final.json
├── data/
│   ├── monsters_all_enriched.json      # Old enriched file (6,847 monsters, merge source)
│   ├── monsters_all_enriched_v2.json   # 5etools-only build (4,439 monsters)
│   └── kobold-plus-fight-club-master/  # Vendored KFC data
└── Old/
    ├── combat_forge_v12.html           # Previous baked version (stale, archived)
    ├── dnd_combat_calc_v11.html        # Older app versions
    └── dnd_combat_calc_v2..v9.html
```

## Architecture — IMPORTANT
The app ships with monsters baked directly into the HTML as a JS const
(`const MONSTER_DATA=JSON.parse(atob('...'));`). For easier editing/QA the
source HTML is kept stripped (`combat_forge.html`, ~213KB) and a Python
script bakes monsters back in on demand.

**Workflow:**
1. Edit `combat_forge.html`
2. Run `python bake_monsters.py` (defaults: reads `combat_forge.html` + `monsters_final.json`, writes `combat_forge_baked.html`)
3. Open `combat_forge_baked.html` in browser to test
4. Bump the version label in `combat_forge.html` (`<title>` and `.tb-sub`) when shipping meaningful changes — filename stays unversioned.

Bake-script flags: `--in`, `--monsters`, `--out`. Re-baking an already-baked
HTML works (regex matches both stripped and baked forms).

## Monster Data Pipeline
Source: `C:\Users\tophe\Downloads\5etools-src-main\5etools-src-main\data\bestiary\`

Pipeline:
1. `build_monsters_enriched.py` → reads all 5etools bestiary JSONs → outputs `monsters_all_enriched_v2.json`
2. `merge_monsters.py` → merges v2 with third-party Kobold monsters from old file → outputs `monsters_final.json`

### monsters_final.json stats
- 7,304 monsters total
- 2,279 official (WotC), 5,025 third-party (Kobold etc.), 0 community/homebrew
- 98% have atkBonus populated
- 100% have environment tags
- 32% have lore (official monsters mostly covered, third-party partial)

### Monster Schema (what the app expects)
```json
{
  "name": "Goblin",
  "slug": "goblin-mm",
  "source": "MM",
  "sourceType": "official",
  "cr": "1/4",
  "xp": 50,
  "ac": 15,
  "hp": { "average": 7, "formula": "2d6" },
  "size": "Small",
  "type": "humanoid (goblinoid)",
  "alignment": "neutral evil",
  "abilities": { "str": 8, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 8 },
  "saves": {},
  "skills": { "stealth": 6 },
  "speed": { "walk": 30 },
  "senses": ["darkvision 60 ft."],
  "passive": 9,
  "languages": ["Common", "Goblin"],
  "resistances": [],
  "immunities": [],
  "vulnerabilities": [],
  "conditionImmunities": [],
  "traits": [{ "name": "Nimble Escape", "desc": "..." }],
  "actions": [{ "name": "Scimitar", "desc": "Melee Weapon Attack: +4 to hit..." }],
  "bonusActions": [],
  "reactions": [],
  "legendaryActions": [],
  "mythicActions": [],
  "spellcasting": [],
  "lore": "...",
  "environment": ["underdark", "grassland", "forest", "hill"],
  "atkBonus": 4,
  "numAtks": 1,
  "dmgPerAtk": "1d6+2",
  "dmgTypes": ["piercing", "slashing"],
  "saveDC": null,
  "saveAbility": null,
  "aoeType": null,
  "aoeDmg": null,
  "multiattack": false
}
```

## App Features
- Left panel: Monster browser with search, CR sliders, type/env/source filters, sort chips
- Center: Encounter builder + Monte Carlo sim (1,000 runs)
- Right panel: Party builder (class, level, gear, support toggle)
- Encounter generator: picks monsters by difficulty + encounter type, runs 100-sim check to validate tier
- Sim outputs: survival %, median rounds, outcome probabilities, representative combat log

## Danger Tiers (8 tiers, sim-based)
Ordered low → high: **Trivial → Low → Moderate → High → Dangerous → Deadly → Severe → Death**

Thresholds (first match wins, checked Death → Trivial):
- **Death**: surv < 10% OR tpkR ≥ 65%
- **Severe**: surv < 35% OR tpkR ≥ 40%
- **Deadly**: surv < 60% OR tpkR ≥ 20%
- **Dangerous**: surv < 80% OR tpkR ≥ 8%
- **High**: tpkR ≥ 5% OR multiDownR ≥ 25% OR downR ≥ 50%
- **Moderate**: downR ≥ 30% OR multiDownR ≥ 10% OR avgPct ≥ 55%
- **Low**: downR ≥ 15% OR avgPct ≥ 35%
- **Trivial**: everything below Low

## Encounter Generator — Smart Tier Matching
When DM clicks Generate Encounter with a chosen difficulty:
- Runs `quickSimDC()` — 100 quick sims on the candidate encounter
- Accepts ONLY exact tier match (e.g. choosing Moderate must sim as Moderate)
- Retries up to 15 times, takes closest result if no exact match found
- Generator difficulty chips: Low / Moderate / High / Dangerous / Deadly (no Severe/Death)

## Known Issues / Next Tasks (priority order)
1. **Monster list pagination** — currently caps display at 500 (A-D range), need pages of 75 + letter chips
2. **CR slider sub-1 fix** — getSuggested() floors at CR 1, needs to allow 0/1/8/1/4/1/2
3. **Horde/swarm generation** — swarm = very low CR many monsters; horde = sim-driven count scaling
4. **Text size** — A+/A- buttons in topbar exist but only scale some elements (need root font-size fix)

## Key JS Variables & Functions (combat_forge.html)
- `MDB` — monster database array (loaded from baked const or file)
- `ENC` — current encounter array `[{monster, count}]`
- `PCS` — party members array
- `GENDIFF` — selected generator difficulty string
- `ETYPE` — encounter type (random/boss/horde/swarm etc.)
- `runMC()` — runs 1,000 sim iterations, returns full results object
- `quickSimDC(encArr)` — runs 100 sims on a given encounter, returns dc string
- `generateEncounter()` — builds encounter with tier validation loop
- `buildCombat()` — constructs combatant objects from ENC + PCS for sim
- `runOne(intel)` — single combat simulation, returns outcome object
- `partyBudget(diff)` — returns total XP budget for party at given difficulty
- `updateKobold()` — updates XP baseline display
- `searchMonsters()` — filters and renders monster list (currently caps at 500)

## Ruleset Support
- 2014 rules: easy/medium/hard/deadly XP thresholds
- 2024 rules: low/moderate/high/deadly XP thresholds
- `dangerous` budget = midpoint between high and deadly (interpolated)

## Class Data
13 classes modeled: barbarian, bard, cleric, druid, fighter, monk, paladin, ranger,
rogue, sorcerer, warlock, wizard, artificer. Each has HP formula, AC estimate,
DPR by level, initiative bonus, support flag.

## Party Features
- Up to ~8 party members
- Gear toggle: Mundane / Magical (bypasses nonmagical resistance)
- Support toggle: marks healers/buffers
- Paladin aura detection: +3 to all saves if paladin in party
- Bless: auto-applied if support caster present
- Initiative override and AC override per PC
- Saved parties (localStorage)

## Sim Intelligence Slider
1 = Mindless (random targeting)
2 = Low (targets lowest HP)
3 = Average (mixed)
4 = Tactical (focuses downed PCs, targets squishiest)
5 = Genius (optimal play)
Monster INT score overrides slider for dumb creatures.

## Color Scheme (CSS vars)
```
--diff-trivial: #6080a0  (blue-gray)
--diff-low: #1D9E75      (teal)
--diff-moderate: #c9a84c (gold)
--diff-high: #c07020     (orange)
--diff-dangerous: #c04040 (red)
--diff-deadly: #8020a0   (purple)
--diff-severe: #3C3489   (deep indigo)
--diff-death: #0a0a0c    (near black)
```
