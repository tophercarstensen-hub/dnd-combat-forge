# Combat Forge Changelog

## v15.1 (2026-04-16)
### Spell Library
- New **Spell Library tab** with 936 spells from 5etools data
- Chip-based multi-select filters: Class, Level, Casting Time, Category, Damage Type, School, Targeting, AoE Shape
- Fixed 4-per-row grid layout with dynamic counts on every chip
- Per-section clear buttons and "Clear All" reset
- Spells grouped by level with collapsible gold-accent section headers
- "Newest Only" toggle deduplicates reprinted spells (XPHB > PHB)
- Full spell details: casting time, range, components, duration, classes, damage formula, description
- Source shown as acronym in list, full name when expanded
- Collapse-all button in Level section

### Spell-Aware Sim
- Baked spell database replaces hardcoded 40-spell SPELL_DPR with 352 damaging spells
- `parseSpellsForDamage` now scans against the full spell DB
- Monsters with spellcasting get their best damage spell factored into per-round DPR
- Spell-based AoE promoted when it beats extracted breath weapon damage

### Encounter Generator
- **Iterative refinement engine** replaces full-redraw retry loop
  - 2 seed candidates × 12 refinement steps per seed
  - Type-specific mutations: boss=CR-only, horde=count-first, duo/trio=CR+family-match
  - Family-aware swaps (goblin fight adds hobgoblin, not random fiend)
  - One-line refinement trail shown in status bar
- **Tier-gap-scaled mutations** — removes 2-3 grunts at once and CR-swaps 2-3 steps per mutation when 2+ tiers off target
- **Relaxed CR pool** for mutations — slider bounds don't cap the algorithm when chasing a tier
- **Weighted XP distribution** — boss/lt/main/grunt groups always use full budget (no silent unused XP)
- **Action economy adjustment** — solo bosses get 1.5× budget boost, hordes get 0.6×
- **Boss+minions loop** allows CR-down on the boss before dropping groups
- **"Dangerous" difficulty** now has an XP budget (midpoint of High and Deadly)
- Warning in status when refinement couldn't find exact tier match

### Solo Boss Model (CR 20+)
- **Multi-attack composition analyzer** — parses multiattack text ("one bite + two claws") and sums true per-round damage instead of repeating the best single attack
- **Multi-AoE detection** — monsters with 3+ breath weapons/AoE actions get elevated fire rate (up to 85%/round for 5+ AoEs like Tiamat)
- **Legendary action damage** uses best single-attack damage × 0.85 (not averaged-down multiattack rate)
- **2024 MM format support** — detects abbreviated `m +14` hit format, flat damage (`Hit: 60 force`), and `automatic hit`
- **Rider-aware damage extraction** — "36 force plus 22 lightning" correctly sums to 58
- **Bonus actions scanned** for AoE and attacks (294 new structured bonusActions extracted from prose traits)
- **Dual-typed legendaryActions canonicalized** — array-stored legendary actions (Tiamat) no longer break the sim

## v15.0 (2026-04-16)
### Spell Library Tab (initial)
- New tab in topbar alongside Builder+Sim and Monster Library
- Search, filter by level/school/class, sort by name/level
- Click-to-expand spell details with full stat block

## v14.8 (2026-04-16)
### Spell Data Pipeline
- New `scripts/build_spells.py` — extracts 936 spells from 5etools source
- Output: `spells_final.json` with 26 fields per spell
- `bake_monsters.py` updated to bake both monsters AND spells into HTML
- `SPELL_DATA` const added to HTML, decoded via `_decodeB64Utf8`

## v14.7 (2026-04-16)
### Boss+Minions Iteration Fix
- Mutation strategies split into 5 granular operations: count_adj, bosscr, cr, count_add, count_drop
- Boss+minions/elite "too hard" flow: trim grunts → CR-down boss → drop group (preserves encounter identity)

## v14.6 (2026-04-16)
### Solo Legendary Boss Model
- `analyzeMonsterCombat()` — walks actions + legendary_actions + bonusActions for multi-attack and multi-AoE
- `multiattackDPR` / `bestAttackDmg` / `aoeActionCount` written back to monster fields
- `resolveMonsterStats` overrides weapon DPR when composition is 10%+ better
- `aoeFreq` proportional to AoE count (33% base, +15% per additional AoE)
- Legendary action handler uses bestAttackDmg instead of averaged dmgPerAtk

## v14.5 (2026-04-16)
### Bug Fixes & UI Polish
- **Monster Library stat panel restored** — stat block preview above editor form
- **Alpha chip jump fixed** — `MACTIVE_LETTER` tracks clicked letter, `getBoundingClientRect` scroll
- **"Clear Filters (keep CR)" button** added alongside "Clear All"
- **Pin default flipped** — encounter stays open by default; lock opts into auto-collapse
- **First-run hint toast** — explains pin on first Simulate, persisted in localStorage
- Collapsible section bars: gold gradient + left-border accent
- Encounter diff-bar merged into summary header (XP + budget in tooltip)
- Bottom enc-divider removed; summary header is sole collapse control
- Monster card clickability: name hover underline, HP/AC bar gold tint + "click to edit" hint
- Sim control bar compacted to one line; sizes bumped
- Tooltips added across entire UI (filter controls, encounter chips, sim controls, etc.)

## v14.0 (2026-04-15)
### Major UI Restructure
- **Encounter generator moved** from left sidebar into encounter zone (collapsible Generate section)
- **Double-collapse system** — Generate and Monsters sections collapse independently
- **Encounter summary header** with count + names + tier tag + XP + pin
- **Alpha chip row** (A-Z jump navigation) in monster sidebar
- **Pagination** (75 per page) replaces the old 500-cap
- **De-abbreviated labels**: Community, 3rd Party, Homebrew, Any Environment
- **CR↓ sort button** added; sort row separated from source chips
- **Clear Filters button** added
- Generator decoupled from search box
- Version naming convention: major.minor.patch (semver-ish)

## v13.0 (2026-04-15)
### Core Fixes
- **UTF-8 mojibake fixed** — `_decodeB64Utf8()` helper for proper non-ASCII monster names
- **HP [object Object] fixed** — `normalizeAll` flattens compound HP `{average, formula}` to scalar
- **NaN in sim fixed** — `dmgPerAtk` dice-formula strings parsed to numeric averages
- **Rider damage extraction** — "1d8+3 piercing plus 1d6 fire" correctly summed in Python pipeline
- **Schema alias** — `resistances` → `damageResistances` normalized
- **Generator XP weighting** rewritten — weighted distribution uses full budget
- **Generator pool** removes forced bossMinCR/ltMinCR gates; pickClosest drives via XP distance
- **CR auto-set** drops avgLvl/4 floor — sub-1 CRs (0, 1/8, 1/4, 1/2) now accessible
- **Dangerous difficulty** budget = midpoint(high, deadly)
- Spellcasting prose rendered with per-tier line breaks
- Bake script updated to new `_decodeB64Utf8` pattern
- Version bumped from v12 → v13; filename unversioned (`combat_forge_baked.html`)
