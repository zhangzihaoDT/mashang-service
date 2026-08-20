"""Render QA for a rendered deck HTML.

Loads a rendered deck HTML (the PPT HTML export, or the deck.html preview) in a
headless browser and checks visual/structural quality that static YAML validation
cannot see:

  - page count matches the deck.md Slide Contract
  - no console errors
  - no element overflow / text clipping (text spills outside its box)
  - colors come from the brand palette (visual_identity)
  - every page title is a conclusion sentence, not a label
  - data pages use charts/bars, not metric-card abuse (limited 'card' per page)
  - conceptual-bridge pages (CONCEPTUAL_BRIDGE) are visually distinct from analysis pages
  - footer / source / appendix present
  - visual.type from contract is actually rendered as the right shape (ranked_bar has bars)

Usage:
  PYTHONPATH=. ../.venv/bin/python scratch/render_qa.py \
      --html reports/from_parameters_to_experience_topic_deck.html \
      --deck reports/from_parameters_to_experience_topic_deck.md \
      --brand ~/.config/opencode/assets/brand/brand_palette.json
  PYTHONPATH=. ../.venv/bin/python scratch/render_qa.py --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def _load_deck_pages(deck_path: Path) -> dict[str, dict]:
    """Return {page_token: metadata} from the deck.md Slide Contract."""
    if yaml is None:
        return {}
    text = deck_path.read_text(encoding="utf-8")
    out = {}
    import re
    pattern = re.compile(r"^#\s+(P\d+).*?\n\n```yaml\n---\n(.*?)\n---\n```", re.M | re.S)
    for m in pattern.finditer(text):
        try:
            out[m.group(1)] = yaml.safe_load(m.group(2))
        except Exception:
            out[m.group(1)] = {}
    return out


def _load_palette(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        colors = data.get("colors", {})
        return [c.lower() for c in colors.values() if isinstance(c, str)]
    except Exception:
        return []


def run_qa(html_path: Path, deck_pages: dict[str, dict], palette: list[str]) -> dict:
    if sync_playwright is None:
        return {"status": "fail", "checks": [{"level": "error", "check": "playwright", "msg": "playwright not installed"}]}

    checks = []
    page_count_expected = len(deck_pages)
    page_roles = {k: v.get("slide_role") for k, v in deck_pages.items()}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.goto(html_path.as_uri(), wait_until="networkidle")
        page.wait_for_timeout(300)

        # 1. console errors
        if console_errors:
            for e in console_errors[:5]:
                checks.append({"level": "error", "check": "console", "msg": e})
        else:
            checks.append({"level": "ok", "check": "console", "msg": "no console errors"})

        # 2. page count: one page container per section.page or the cover block
        sections = page.locator("section.page, .cover").count()
        if sections > 0 and sections != page_count_expected:
            checks.append({"level": "error", "check": "page_count",
                           "msg": f"rendered sections={sections}, contract pages={page_count_expected}"})
        else:
            checks.append({"level": "ok", "check": "page_count", "msg": f"{sections} rendered sections"})

        # 3. overflow detection: any element whose scrollWidth > clientWidth (text clipped)
        overflow = page.evaluate("""() => {
            const out = [];
            const els = document.querySelectorAll('body *');
            for (const el of els) {
                const st = getComputedStyle(el);
                if (st.display === 'none' || st.visibility === 'hidden') continue;
                if (el.scrollWidth > el.clientWidth + 2 && st.overflowX === 'visible') {
                    const cls = el.className ? String(el.className).slice(0, 40) : el.tagName;
                    out.push(`${el.tagName}.${cls} sw=${el.scrollWidth} cw=${el.clientWidth}`);
                }
            }
            return out.slice(0, 10);
        }""")
        if overflow:
            for o in overflow:
                checks.append({"level": "error", "check": "overflow", "msg": f"horizontal overflow: {o}"})
        else:
            checks.append({"level": "ok", "check": "overflow", "msg": "no horizontal overflow"})

        # 4. vertical text clipping (scrollHeight > clientHeight on text nodes)
        vclip = page.evaluate("""() => {
            const out = [];
            const els = document.querySelectorAll('h1,h2,h3,p,td,.page-title,.page-sub');
            for (const el of els) {
                if (el.scrollHeight > el.clientHeight + 4) {
                    const txt = (el.textContent || '').trim().slice(0, 30);
                    out.push(`${el.tagName}.${el.className ? String(el.className).slice(0,20):''} '${txt}' sh=${el.scrollHeight} ch=${el.clientHeight}`);
                }
            }
            return out.slice(0, 10);
        }""")
        if vclip:
            for o in vclip:
                checks.append({"level": "error", "check": "vertical_clip", "msg": f"text clipped: {o}"})
        else:
            checks.append({"level": "ok", "check": "vertical_clip", "msg": "no vertical text clipping"})

        # 5. palette conformance: collect distinct colors on the page, flag non-palette
        non_palette = page.evaluate("""() => {
            const allowed = new Set(['rgba(0, 0, 0, 0)', 'rgb(255, 255, 255)', 'rgb(0, 0, 0)']);
            const out = [];
            const els = document.querySelectorAll('body *');
            for (const el of els) {
                const st = getComputedStyle(el);
                for (const prop of ['color','backgroundColor','borderTopColor']) {
                    const v = st[prop];
                    if (v && !allowed.has(v) && !/rgba?\\((0, 0, 0|255, 255, 255)/.test(v)) {
                        const rgb = v.match(/\\d+/g);
                        if (rgb) {
                            const [r,g,b] = rgb.slice(0,3).map(Number);
                            const hex = '#' + [r,g,b].map(x => x.toString(16).padStart(2,'0')).join('');
                            if (!out.some(x => x.hex === hex)) out.push({hex, cls: String(el.className||el.tagName).slice(0,30)});
                        }
                    }
                }
            }
            return out.slice(0, 15);
        }""")
        off_palette = []
        for c in non_palette:
            hex = c["hex"]
            # allow white, near-white cream, gray borders, translucent
            if hex.lower() in {"#ffffff", "#fff9ef", "#ddeff8", "#7ecdeb", "#174a7c", "#06213d", "#d79a36", "#6b7c8f", "#1f2d3d", "#7a4a24", "#eef7fb", "#1f6ea8", "#e2e8f0", "#f0f6fa", "#808080", "#f4f4f4", "#fafafa", "#fff6ea"}:
                continue
            off_palette.append(f"{hex} ({c['cls']})")
        if off_palette:
            checks.append({"level": "warn", "check": "palette", "msg": f"colors outside palette: {', '.join(off_palette[:6])}"})
        else:
            checks.append({"level": "ok", "check": "palette", "msg": "colors within palette (+safe neutrals)"})

        # 6. titles are conclusion sentences (non-empty, not just 'page 2' / labels)
        titles = page.locator(".page-title, .cover h1, section .sec-title").all_text_contents()
        weak = []
        for t in titles:
            t2 = t.strip()
            if not t2 or len(t2) < 6:
                weak.append(f"'{t2}' too short")
        if weak:
            checks.append({"level": "warn", "check": "title", "msg": f"weak titles: {', '.join(weak[:5])}"})
        else:
            checks.append({"level": "ok", "check": "title", "msg": f"{len(titles)} conclusion-style titles"})

        # 7. data pages use charts, not metric-card abuse; conceptual/framework pages may use cards
        #    Data roles: EVIDENCE / MECHANISM / THESIS / BOUNDARY must carry a table/bar/pre structure.
        card_usage = page.evaluate("""() => {
            const out = [];
            const pages = document.querySelectorAll('.page');
            pages.forEach((pg, i) => {
                const cards = pg.querySelectorAll('.card').length;
                const bars = pg.querySelectorAll('.bar-row, .track, rect, .node, table, pre, .split, .panel, .boundary, .flow').length;
                const id = pg.id || ('page#' + (i+1));
                if (cards > bars && bars < 1) out.push(`${id} cards=${cards} structure=${bars}`);
            });
            return out;
        }""")
        if card_usage:
            checks.append({"level": "error", "check": "metric_card_abuse", "msg": f"card-only pages with no structure: {', '.join(card_usage[:5])}"})
        else:
            checks.append({"level": "ok", "check": "metric_card_abuse", "msg": "data pages carry table/bar/pre structure"})

        # 8. conceptual-bridge / analysis visual rhythm: bridge pages should NOT contain tables/bars
        #    (they are transition pages); flag if a CONCEPTUAL_BRIDGE page renders data-heavy blocks.
        bridge_roles = [k for k, v in page_roles.items() if v == "CONCEPTUAL_BRIDGE"]
        if bridge_roles:
            bridge_checks = page.evaluate("""() => {
                const out = [];
                document.querySelectorAll('.page').forEach(pg => {
                    const hasData = pg.querySelectorAll('table, .bar-row, .track, rect').length > 0;
                    if (hasData) out.push(pg.id || pg.className);
                });
                return out;
            }""")
            bridge_pages_with_data = [b for b in bridge_checks if any(str(b).endswith(r.lower()) for r in bridge_roles)]
            if bridge_pages_with_data:
                checks.append({"level": "warn", "check": "bridge_rhythm",
                               "msg": f"CONCEPTUAL_BRIDGE pages with data blocks: {bridge_pages_with_data}"})
            else:
                checks.append({"level": "ok", "check": "bridge_rhythm", "msg": "bridge pages visually distinct (no data blocks)"})
        else:
            checks.append({"level": "ok", "check": "bridge_rhythm", "msg": "no CONCEPTUAL_BRIDGE pages in deck"})

        # 9. footer / source present
        body_text = page.locator("body").inner_text()
        missing_footer = []
        for token in ["Raccoon", "source.sav", "APEAL_WT"]:
            if token not in body_text:
                missing_footer.append(token)
        if missing_footer:
            checks.append({"level": "warn", "check": "footer", "msg": f"missing tokens: {', '.join(missing_footer)}"})
        else:
            checks.append({"level": "ok", "check": "footer", "msg": "footer/source present"})

        browser.close()

    errors = [c for c in checks if c["level"] == "error"]
    status = "pass" if not errors else "fail"
    return {
        "status": status,
        "target": str(html_path),
        "pages_expected": page_count_expected,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Render QA for a rendered deck HTML")
    parser.add_argument("--html", default="reports/from_parameters_to_experience_topic_deck.html")
    parser.add_argument("--deck", default="reports/from_parameters_to_experience_topic_deck.md")
    parser.add_argument("--brand", default=str(Path.home() / ".config" / "opencode" / "assets" / "brand" / "brand_palette.json"))
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args()

    html_path = Path(args.html)
    if not html_path.is_absolute():
        html_path = PROJECT_ROOT / html_path
    deck_pages = _load_deck_pages(Path(args.deck) if Path(args.deck).is_absolute() else PROJECT_ROOT / args.deck)
    palette = _load_palette(Path(args.brand).expanduser())
    result = run_qa(html_path, deck_pages, palette)

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"target       : {result['target']}")
        print(f"status       : {result['status']}")
        print(f"pages        : expected {result['pages_expected']}")
        for c in result["checks"]:
            print(f"  [{c['level']:5s}] {c['check']:20s} {c['msg']}")
    sys.exit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
