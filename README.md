# Combat Forge

A single-file D&D 5e encounter builder and combat calculator for Dungeon Masters — browse a database of thousands of monsters and spells, build an encounter, and run 1,000 Monte Carlo combat simulations against your actual party to see how dangerous it really is before you run it at the table.

## Get it

Download `combat_forge_baked.html` from the [latest release](https://github.com/tophercarstensen-hub/dnd-combat-forge/releases/latest) and open it in any browser (Chrome, Firefox, Edge, Safari). That's it — no install, no server, no account.

- **Works fully offline** for everything except monster portraits — those load live from this repo, so you'll need an internet connection to see art. Everything else (monster stats, spells, encounter building, simulations) works with no connection at all.
- **One file, no setup.** Just double-click it once downloaded.
- Don't use `combat_forge.html` (without `_baked`) — that's the stripped source file used for development; it has no monster or spell data in it and won't work as an app on its own.

## Using it

- **Builder + Sim** (main tab): add party members on the right (class, level, gear), add monsters to the encounter in the center panel (browse/filter on the left, or use Generate Encounter), then hit Simulate to run 1,000 combat rounds and see survival odds, expected rounds, and a difficulty rating.
- **Generate Encounter**: pick an encounter type (Boss, Duo, Squad, Horde, etc.) and a difficulty (Low → Deadly), and it'll auto-pick monsters from your CR/type/environment filters that actually hit that difficulty against your specific party — not just generic XP-budget math.
- **Monster Library**: full searchable database with filters for CR, type, size, environment, source book, and dozens of ability/combat tags. Click any monster for its full stat block and lore.
- **Spell Library**: same idea, for spells — filterable by level, school, class, and damage/effect type.
- **2014 / 2024 ruleset toggle** (top bar): switches which DMG encounter-building math the app uses.

## Updates

New versions get published as [GitHub Releases](https://github.com/tophercarstensen-hub/dnd-combat-forge/releases) with the ready-to-use file attached — just grab the latest one. Check the [Changelog](CHANGELOG.md) for what changed.

## For developers

See [`Combat Calc/CLAUDE.md`](CLAUDE.md) for the build pipeline, data schema, and project architecture if you want to modify the app or its monster/spell database.
