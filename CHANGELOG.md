# Combat Forge Changelog

## v16.9 (2026-04-17)
### Legendary Acts chip + per-section filter controls
- **Legendary Acts chip showed 0 — fixed.** The earlier `legendaryActions=3` bug fix canonicalized the field to a number, which broke the library chip predicate that was still calling `_arr(m.legendaryActions)`. Predicate now checks `+m.legendaryActions > 0 || _arr(m.legendary_actions).length > 0`. Same fix for the "Hide Legendary" exclusion chip.
- **Per-section All / None buttons** in the Source Filter modal (next to each group header: WotC Core Books, Adventure Modules, Kobold Press, etc.) via `selectSection()`.
- **Per-section ✕ Clear chips** in the Monster Library filter panel — dashed-border inline chip at the end of each active category's grid. Section labels now show `(N active)` count. Matches spell-library pattern via new `libClearSection()`.

## v16.8 (2026-04-17)
### Encounter stat panel polish
- **Source badge next to monster name** in the encounter stat panel header — small monospace chip (e.g. `[MM]`, `[BGDIA]`) with a tooltip showing the full source name from `SOURCE_NAMES`. Hidden entirely when the monster has no source field.

## v16.7 (2026-04-17)
### TDZ init fix
- **Console error on page load fixed.** `initLibUI` was called inside the IIFE before `LIB_F` (a later `const`) was initialized → Temporal Dead Zone error. Deferred library init with `setTimeout(0)` so the whole script finishes parsing first. Cleaner console output, no behavior change.

## v16.6 (2026-04-17)
### Picker variety + grunt pool alignment + named-NPC stopgap
- **Adaptive tolerance band in `pickClosest`.** Starts at ±35% of target XP; widens ×1.5 per step (up to 4× target) until at least 8 candidates fit. Prevents the deterministic top-8-by-array-order fallback that caused the "same ~8 monsters across 12 Generates" bug.
- **No upper cap on picker pool.** Previously capped at 50 "for budget discipline" — removed. When a pool has 400+ CR 3 monsters, all 400 are eligible for random pick.
- **Grunt-pool minCR aligned with horde mutation floor.** `gruntMinCR` for horde encounters now reads from the same `HORDE_FLOOR_BY_LVL` table the mutator uses. Initial picks land on-budget instead of forcing multi-step CR-down refinement.
- **`isGrunTierNPC` heuristic** (stopgap, grunt-pool only): flags specific-race humanoid monsters whose names lack role words (Warrior, Captain, Commoner…) and don't contain " of " (faction roles). Catches Thavius Kreeg, Volo, Donavich, Arabelle, etc. before they enter the grunt pool. Accepts some false positives — pool is still 1,000+ monsters. Does NOT affect the Library's "Hide Named NPCs" chip, which stays accurate-only.

## v16.5 (2026-04-17)
### Attack cap + tier CR floor + debug log
- **Per-target attack cap in sim.** Added `MAX_ATTACKERS_PER_PC=4` with a `Map` reset each round. Monsters redirect to an unsaturated PC if their target already has 4 attackers committed; if all PCs are capped they idle. Applies only to single-target attacks — AoE still hits multiple PCs normally. Prevents 30-grunt hordes from rating as "Moderate" against L10 parties when they'd be Trivial at the table.
- **Tier-based CR floor for horde/swarm mutation.** Replaced `Math.max(0.125, avgLvl/8)` formula with a lookup table that scales predictably: L1-2:CR 0, L3-4:1/8, L5-6:1/4, L7-8:1/2, L9-10:CR 1, L11-13:CR 2, L14-16:CR 3, L17-20:CR 5. Old formula plateaued on integer CRs (L10-15 all bottomed at CR 2 then jumped to CR 3 at L17+).
- **Named-NPC heuristic demoted to flag-only.** Removed the lore-length + specific-humanoid + specific-alignment fallback — it was flagging missing data, not named-ness. Now trusts only `m.unique`, `m.isNpc`, `m.isNamedCreature`. Will re-expand when parseable adventure-module book data lands (TODO in code).
- **Debug log (`DEBUG_GEN` flag).** Console-toggleable via `DEBUG_GEN = true`. Each `pickClosest` call logs pool role, target XP, eligible count, after-RECENT exclusions, after-ENC exclusions, tolerance band size, and the picked monster. End-of-Generate summary shows tier match, full encounter, refinement steps trail, and rolling RECENT_PICKS tail.

## v16.4 (2026-04-17)
### Named-NPC filter v1, stat panel height, CR floor, legendary bug
- **Critical bug: `legendaryActions=3` on every CR-0 monster.** `normalizeAll` was setting `m.legendaryActions=3` whenever `Array.isArray(m.legendaryActions)` — including empty arrays. So Arabelle (CR 0 commoner kid) and hundreds of other monsters showed 3 legendary actions in the editor. Fixed: empty-array check sets to 0; non-empty retains the array → count.
- **Initial CR floor for horde mutation** (`Math.max(0.125, avgLvl/8)`) — prevents L10+ hordes from CR-downing into CR 0 chaff. (Revised in v16.5 with proper tier table.)
- **Named NPCs excluded from grunt + mutation pools** via `isLikelyNamedNPC` heuristic (lore-length based initially; revised in v16.5).
- **Library filter chips — "Hide" section.** New exclusion row with "Named NPCs" and "Legendary" toggles. Active chips HIDE matching monsters from the list.
- **Stat panel now fills available height.** Removed `max-height: 540px` hard cap from `.enc-list-col`; replaced with `calc(100vh - 260px)` + 400px minimum. Stat panel sibling no longer truncated by the list column's old cap.

## v16.3 (2026-04-17)
### Source modal URL cleanup
- **Reddit URL-suffixed sources collapse to their label.** "Monster-A-Day: https://reddit.com/r/monsteraday/comments/abc123/..." was creating hundreds of unique modal entries — one per URL. `normaliseSource` now strips anything after `https?://` back to the prefix colon, so all Monster-A-Day monsters merge into a single entry.

## v16.2 (2026-04-17)
### Generator variety + visual fixes
- **RECENT_PICKS rolling exclusion.** New 30-slot LRU of recently generated monster slugs. Picker prefers monsters outside RECENT_PICKS first, falls back to excluding only current ENC, then the full pool. Prevents same-monster repeats across consecutive Generates even when the XP band holds hundreds of candidates.
- **Horde mutation order flipped for easier-tier.** Was `[count_adj, count_drop, cr]` — stripped grunts before trying to weaken them. Now `[cr, count_adj, count_drop]` — CR-down first so a horde stays hordey as long as possible before losing members.
- **Books button styling fixed.** Root cause: `searchMonsters()` was clearing inline `color`/`border-color` styles every run. Moved styling to `.btn-books` CSS class with a `.filtered` modifier the JS toggles. Now stays readable; works across every Books button instance.

## v16.1 (2026-04-17)
### Picker fixes + CR dropdown bulletproofing
- **Picker pool cap raised then removed.** Brief 50-cap ceiling replaced with no cap — random pick from all monsters in the adaptive tolerance band.
- **CR dropdown options inlined in HTML.** Moved all 34 `<option>` entries into the static HTML for both encounter-builder and library CR min/max dropdowns. No more JS-init timing race. NaN-tolerant handlers fall back to current state if somehow the dropdown value is empty.

## v16.0 (2026-04-17)
### Major UI redesign + picker & CR controls
- **Monster Library redesigned to 3-column layout.** Filter panel left, searchable list middle with alpha chips + pager, stat block + edit form right. Replaces the old list | editor | sidepanel geometry.
- **Spell-library-style chip filters for monsters.** Type (14), Size (6), Abilities (6: Spellcasting, Legendary Acts, Mythic Acts, Lair Actions, Legend. Resist., Multiattack), Combat (4: AoE, Recharge, Reactions, Regeneration), Mobility (4: Flying, Swimming, Burrowing, Climbing), Environment (13), Source (4), Hide (2: Named, Legendary). Live counts on every chip, dim state for empty categories.
- **Settings modal behind ⚙ icon** in topbar. Tabbed: Database (import, export, reset to baked-in), Homebrew (new, paste-JSON, reset all), Export (Download Updated App with checkboxes), Stats (monster counts by source tier). Database / Homebrew / Export UI moved out of the library's old static sidepanel.
- **Text size buttons A− / A+** actually work. Previous implementation was `document.documentElement.style.fontSize` on a stylesheet full of hardcoded px values. Now uses `document.body.style.zoom` so everything scales proportionally. Also visible (previously behind `display:none`).
- **Picker pool widened from fixed top-8 to ±35% XP tolerance band.** D&D XP is strictly CR-derived (every CR 2 = 450 XP), so a stable-sort top-8 against a huge tied-XP pool was deterministic — same 8 monsters every Generate. Tolerance band pulls the full tied CR + adjacent step for real variety.
- **Fresh-roll guarantee.** `generateEncounter` builds a `prevSlugs` exclusion set from current ENC; picker filters those out preferentially. Refusal to pick the same monster on re-roll unless filters are tight enough that there's no alternative.
- **CR min/max dropdowns below the sliders** on both encounter builder and library. Bidirectionally synced: dragging a slider updates the dropdown, changing a dropdown updates the slider. Shared `RPCRMIN/RPCRMAX` (and `LIB_F.crMin/crMax`) state.
- **Auto-suggest CR clamp relaxed** — `getSuggested()` no longer forces `max ≥ min+1`. Setting min=max=2 now shows only CR 2 monsters.
- **Alpha chip jump fixed** — scroll clamping near page bottom caused letter jumps to land in mid-page. Now uses `MLIST_OFFSET` to re-slice the visible page starting at the target letter's index, so the letter always sits at row 0.
- **Version label shown** in topbar. Stripped from filename per the convention (filename stays `combat_forge_baked.html`).

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
