#!/usr/bin/env python3
"""Render the design system to a page and screenshot it.

The design brief asks each batch for "screenshots or rendered UI evidence".
This builds that evidence from the real SCSS rather than a hand-written copy
of it: the tokens and components are compiled with libsass exactly as Odoo
would compile them, so what the screenshots show is what the asset bundle
actually produces. A showcase that drifted from the source would be worse
than none.

The page doubles as the component reference - the thing to look at before
inventing a fourth way to draw a status pill.

Usage:
    python tools/render_design_system.py [--out DIR]

Needs libsass (`pip install libsass`) and Playwright with Chromium for the
screenshots. Without Playwright it still writes the HTML and says so.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCSS_DIR = REPO / "sinclaire_base/static/src/scss"
DEFAULT_OUT = REPO / "docs/design-system"

WIDTHS = [("desktop", 1440, 900), ("tablet", 834, 1112), ("mobile", 390, 844)]


def compile_scss() -> str:
    import sass

    source = "\n".join((SCSS_DIR / name).read_text(encoding="utf-8") for name in ("_tokens.scss", "_components.scss"))
    return sass.compile(string=source, output_style="expanded")


def page(css: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sinclaire Design System</title>
<style>
{css}
* {{ box-sizing: border-box; }}
body {{
  background: var(--sin-bg);
  color: var(--sin-text);
  font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: var(--sin-text-base);
  line-height: 1.5;
  margin: 0;
  padding: var(--sin-space-5);
}}
h1 {{ font-size: var(--sin-text-2xl); margin: 0 0 var(--sin-space-1); }}
.lede {{ color: var(--sin-text-muted-text); margin: 0 0 var(--sin-space-6); max-width: 70ch; }}
section {{ margin-bottom: var(--sin-space-7); }}
.swatches {{ display: grid; gap: var(--sin-space-3);
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }}
.swatch {{ border: 1px solid var(--sin-border); border-radius: var(--sin-radius); overflow: hidden; }}
.swatch__chip {{ height: 56px; }}
.swatch__meta {{ background: var(--sin-surface); font-size: var(--sin-text-xs); padding: var(--sin-space-2); }}
.swatch__name {{ font-weight: var(--sin-weight-semibold); }}
.swatch__hex {{ color: var(--sin-text-muted-text); font-family: var(--sin-font-numeric); }}
.pair {{ display: flex; flex-wrap: wrap; gap: var(--sin-space-2); }}
input.demo {{ background: var(--sin-surface); border: 1px solid var(--sin-border-control);
  border-radius: var(--sin-radius-sm); font-size: var(--sin-text-base); padding: var(--sin-space-2); }}
</style>
</head>
<body>

<h1>Sinclaire Design System</h1>
<p class="lede">Phase&nbsp;1. Compiled from the same SCSS the Odoo asset bundle loads, so this page
cannot drift from the running product. Every contrast pairing shown here is enforced by
<code>tools/check_contrast.py</code> in CI.</p>

<section>
  <h2 class="sin-section-title">Palette</h2>
  <p class="lede">Brand colours as specified, with the derived text variants beside them. Five of the
  brand colours cannot carry normal-size text on these backgrounds; the <code>-text</code> variants are
  the same hue darkened until they clear 4.5:1 on the page background.</p>
  <div class="swatches">
    {"".join(_swatch(n, v, note) for n, v, note in SWATCHES)}
  </div>
</section>

<section>
  <h2 class="sin-section-title">Status</h2>
  <p class="lede">Each pill carries a glyph as well as a colour, so the state survives a monochrome
  print and a red-green colour deficiency.</p>
  <div class="pair">
    <span class="sin-status sin-status--ok">Cleared</span>
    <span class="sin-status sin-status--warn">Due in 5 days</span>
    <span class="sin-status sin-status--critical">Bounced</span>
    <span class="sin-status sin-status--info">In hand</span>
    <span class="sin-status sin-status--neutral">Expected</span>
  </div>
</section>

<section>
  <h2 class="sin-section-title">KPI cards</h2>
  <div class="sin-grid">
    <div class="sin-card"><div class="sin-kpi">
      <span class="sin-kpi__label">Portfolio occupancy</span>
      <span class="sin-kpi__value">87.4%</span>
      <span class="sin-kpi__meta">142 of 163 units let</span>
      <span class="sin-kpi__period">As at 14 Nov 2026</span>
    </div></div>
    <div class="sin-card"><div class="sin-kpi">
      <span class="sin-kpi__label">Rent collected</span>
      <span class="sin-kpi__value sin-kpi__value--ok">AED 2.84m</span>
      <span class="sin-kpi__meta">of AED 3.01m invoiced</span>
      <span class="sin-kpi__period">Year to date</span>
    </div></div>
    <div class="sin-card"><div class="sin-kpi">
      <span class="sin-kpi__label">Overdue rent</span>
      <span class="sin-kpi__value sin-kpi__value--critical">AED 171k</span>
      <span class="sin-kpi__meta">across 9 tenancies</span>
      <span class="sin-kpi__period">As at 14 Nov 2026</span>
    </div></div>
    <div class="sin-card"><div class="sin-kpi">
      <span class="sin-kpi__label">Cheques not yet handed over</span>
      <span class="sin-kpi__value sin-kpi__value--warn">6</span>
      <span class="sin-kpi__meta">3 leases affected</span>
      <span class="sin-kpi__period">As at 14 Nov 2026</span>
    </div></div>
  </div>
</section>

<section>
  <h2 class="sin-section-title">Building cards</h2>
  <p class="lede">The operating model sits on the face of the card because it decides whose money the
  rent is. Note the third figure changes with it: a head-leased building reports gross margin, an
  owner-managed one reports rent administered for the landlord. Showing a margin on an owner-managed
  building would report the landlord's income as the company's.</p>
  <div class="sin-grid">
    {"".join(_building(**b) for b in BUILDINGS)}
  </div>
</section>

<section>
  <h2 class="sin-section-title">Blocked action</h2>
  <p class="lede">A disabled button that will not say why is the single most common complaint about
  internal systems. The unit release rules already produce this list of reasons.</p>
  <div class="sin-card" style="max-width:520px">
    <div class="sin-blocked">
      <div class="sin-blocked__title">This unit cannot be released for marketing yet</div>
      <ul class="sin-blocked__list">
        <li>No market rent has been set</li>
        <li>The DEWA premises number is missing</li>
        <li>The building has no analytic account</li>
      </ul>
    </div>
  </div>
</section>

<section>
  <h2 class="sin-section-title">Empty state</h2>
  <div class="sin-card" style="max-width:520px">
    <div class="sin-empty">
      <div class="sin-empty__title">No cheques recorded against this tenancy</div>
      <p class="sin-empty__body">The lease expects 4 cheques for the year. Register them from the
      tenancy, or mark them expected if the tenant has not handed them over yet.</p>
    </div>
  </div>
</section>

<section>
  <h2 class="sin-section-title">Control outline</h2>
  <p class="lede">Interactive outlines use <code>--sin-border-control</code> at 3:1, which WCAG 1.4.11
  requires of a control boundary. Dividers stay quieter; a hairline at 3:1 would be loud.</p>
  <input class="demo" value="Search buildings" aria-label="Search buildings">
</section>

</body>
</html>
"""


SWATCHES = [
    ("--sin-navy", "#14243A", "text ok"),
    ("--sin-navy-deep", "#203654", "text ok"),
    ("--sin-blue", "#315DCE", "text ok"),
    ("--sin-text", "#17243A", "body copy"),
    ("--sin-text-muted", "#68788F", "large text only"),
    ("--sin-text-muted-text", "#637288", "body copy"),
    ("--sin-teal", "#0F9D92", "fills, large numerals"),
    ("--sin-teal-text", "#0C7F76", "body copy"),
    ("--sin-emerald", "#15966B", "fills, large numerals"),
    ("--sin-emerald-text", "#12815C", "body copy"),
    ("--sin-amber", "#E7A43B", "fill only, never text"),
    ("--sin-amber-text", "#9C6613", "body copy"),
    ("--sin-red", "#D94D57", "fills, large numerals"),
    ("--sin-red-text", "#D3333E", "body copy"),
    ("--sin-border-control", "#7B91AF", "control outlines"),
]


def _swatch(name: str, value: str, note: str) -> str:
    return (
        f'<div class="swatch"><div class="swatch__chip" style="background:{value}"></div>'
        f'<div class="swatch__meta"><div class="swatch__name">{name}</div>'
        f'<div class="swatch__hex">{value} · {note}</div></div></div>'
    )


# Three buildings chosen to exercise the cases that differ, not three that
# look alike: a healthy head lease, an owner-managed building whose money is
# the landlord's, and a head lease whose coverage has gone under 1.0.
BUILDINGS = [
    {
        "name": "Marina Heights",
        "where": "Dubai Marina",
        "model_slug": "head-lease",
        "model_label": "Head Lease",
        "units": 48,
        "occ": "92%",
        "money": "AED 410k",
        "money_label": "Gross margin",
        "pct": 92,
        "tone": "ok",
        "nxt": "2 leases expire within 60 days",
    },
    {
        "name": "Jumeirah Gardens",
        "where": "Al Wasl",
        "model_slug": "owner-management",
        "model_label": "Owner Management",
        "units": 26,
        "occ": "73%",
        "money": "AED 1.9m",
        "money_label": "Managed rent",
        "pct": 73,
        "tone": "warn",
        "nxt": "Owner statement for October not yet issued",
    },
    {
        "name": "Barsha Point",
        "where": "Al Barsha 1",
        "model_slug": "head-lease",
        "model_label": "Head Lease",
        "units": 34,
        "occ": "58%",
        "money": "AED −22k",
        "money_label": "Gross margin",
        "pct": 58,
        "tone": "critical",
        "nxt": "Coverage below 1.0 — review the head lease",
    },
]


def _building(name, where, model_slug, model_label, units, occ, money, money_label, pct, tone, nxt) -> str:
    return f"""
    <div class="sin-card sin-card--actionable" tabindex="0">
      <div class="sin-building">
        <div class="sin-building__head">
          <div class="sin-building__identity">
            <h3 class="sin-building__name">{name}</h3>
            <div class="sin-building__location">{where}</div>
          </div>
          <span class="sin-building__model sin-building__model--{model_slug}">{model_label}</span>
        </div>
        <div class="sin-meter"><div class="sin-meter__fill sin-meter__fill--{tone}"
             style="width:{pct}%"></div></div>
        <div class="sin-building__stats">
          <div class="sin-building__stat">
            <span class="sin-building__stat-value">{units}</span>
            <span class="sin-building__stat-label">Units</span></div>
          <div class="sin-building__stat">
            <span class="sin-building__stat-value">{occ}</span>
            <span class="sin-building__stat-label">Occupancy</span></div>
          <div class="sin-building__stat">
            <span class="sin-building__stat-value">{money}</span>
            <span class="sin-building__stat-label">{money_label}</span></div>
        </div>
        <div class="sin-building__next">Next: {nxt}</div>
      </div>
    </div>"""


def shoot(html_path: Path, out: Path) -> list[Path]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed - wrote the HTML only, no screenshots")
        return []
    shots = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, width, height in WIDTHS:
            pg = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=2)
            pg.goto(html_path.as_uri())
            pg.wait_for_timeout(250)
            target = out / f"design-system-{label}.png"
            pg.screenshot(path=str(target), full_page=True)
            shots.append(target)
            pg.close()
        browser.close()
    return shots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    css = compile_scss()
    html_path = out / "index.html"
    html_path.write_text(page(css), encoding="utf-8")
    print(f"wrote {html_path.relative_to(REPO)}")

    for shot in shoot(html_path, out):
        print(f"wrote {shot.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
