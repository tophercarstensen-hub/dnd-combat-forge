"""
Bake monster + spell JSON databases into the Combat Forge HTML.

Default workflow:
    python bake_monsters.py

Reads:  combat_forge.html  (stripped source)
Reads:  monsters_final.json
Reads:  spells_final.json  (optional — skipped if missing)
Writes: combat_forge_baked.html

Replaces the `const MONSTER_DATA=...;` and `const SPELL_DATA=...;`
declarations with base64-encoded _decodeB64Utf8(...) calls.
"""

import argparse
import base64
import json
import re
import sys
from pathlib import Path

MONSTER_DATA_RE = re.compile(
    r"const MONSTER_DATA=(?:_decodeB64Utf8\('[^']*'\)|JSON\.parse\(atob\('[^']*'\)\)|\[[\s\S]*?\]);"
)
SPELL_DATA_RE = re.compile(
    r"const SPELL_DATA=(?:_decodeB64Utf8\('[^']*'\)|JSON\.parse\(atob\('[^']*'\)\)|\[[\s\S]*?\]);"
)


def _bake_const(html: str, regex, data: list, label: str) -> str:
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    b64 = base64.b64encode(compact.encode("utf-8")).decode("ascii")
    replacement = f"const {label}=_decodeB64Utf8('{b64}');"
    return regex.sub(lambda _: replacement, html, count=1)


def bake(in_html: Path, monsters_json: Path, spells_json: Path | None,
         out_html: Path) -> None:
    html = in_html.read_text(encoding="utf-8")

    if not MONSTER_DATA_RE.search(html):
        sys.exit(
            f"error: could not find `const MONSTER_DATA=...;` in {in_html}. "
            "Is this the right HTML file?"
        )

    monsters = json.loads(monsters_json.read_text(encoding="utf-8"))
    if not isinstance(monsters, list):
        sys.exit(f"error: {monsters_json} must contain a JSON array")

    html = _bake_const(html, MONSTER_DATA_RE, monsters, "MONSTER_DATA")
    print(f"baked {len(monsters):,} monsters from {monsters_json.name}")

    if spells_json and spells_json.exists() and SPELL_DATA_RE.search(html):
        spells = json.loads(spells_json.read_text(encoding="utf-8"))
        if isinstance(spells, list):
            html = _bake_const(html, SPELL_DATA_RE, spells, "SPELL_DATA")
            print(f"baked {len(spells):,} spells from {spells_json.name}")
    else:
        print("spells_final.json not found or SPELL_DATA placeholder missing — skipping spells")

    out_html.write_bytes(html.encode("utf-8"))
    print(f"  {in_html.name}  ({in_html.stat().st_size / 1024:.1f} KB)")
    print(f"  -> {out_html.name}  ({out_html.stat().st_size / 1024 / 1024:.2f} MB)")


def main() -> None:
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--in", dest="in_html", type=Path,
                   default=here / "combat_forge.html",
                   help="stripped source HTML (default: combat_forge.html)")
    p.add_argument("--monsters", type=Path,
                   default=here / "monsters_final.json",
                   help="monster JSON array (default: monsters_final.json)")
    p.add_argument("--spells", type=Path,
                   default=here / "spells_final.json",
                   help="spell JSON array (default: spells_final.json)")
    p.add_argument("--out", dest="out_html", type=Path,
                   default=here / "combat_forge_baked.html",
                   help="output HTML (default: combat_forge_baked.html)")
    args = p.parse_args()

    for f in (args.in_html, args.monsters):
        if not f.exists():
            sys.exit(f"error: {f} not found")

    bake(args.in_html, args.monsters, args.spells, args.out_html)


if __name__ == "__main__":
    main()
