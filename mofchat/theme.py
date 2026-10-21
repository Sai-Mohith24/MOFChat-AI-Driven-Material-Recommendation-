"""
The interface's visual layer: masthead, page headers, lattice motif, cards and
the sidebar status list.

DESIGN
------
"Crystal lattice." A cool porcelain ground, a deep framework-navy sidebar, and
HKUST-1 teal with copper accents: HKUST-1 (Cu-BTC) is the turquoise copper MOF,
so the two accents are the crystal and its metal. Space Grotesk for display,
IBM Plex Sans for reading, IBM Plex Mono for SQL and traces.

Colours and fonts live in `.streamlit/config.toml`, so every Streamlit widget
inherits them; this module adds only what the theme cannot express: the hero
masthead with its framework drawing, page headers, card surfaces and shadows,
the sidebar brand and status list, and the colophon.

Nothing here changes what the interface says. Answers, tables, validation
traces and caveats render exactly as before; the styling sits around them.

CHART COLOURS
-------------
TEAL and COPPER are the two data hues, checked with the data-viz palette
validator on the page ground #F4F7F8 (colour-blind separation dE 18.2, normal
vision 27.6, both >= 3:1 contrast). CONTEXT grey is reserved for points that
carry no identity (all candidates behind a Pareto front).
"""

from __future__ import annotations

import base64
import html
import math
import re

import streamlit as st

TEAL = "#0891B2"
COPPER = "#D9622B"
CONTEXT = "#C5CFD3"
PARETO_DOMAIN = ["candidate", "Pareto front", "recommended"]
PARETO_RANGE = [CONTEXT, TEAL, COPPER]
# Vega measures label widths once and caches them. On a page that opens straight onto a chart it measures
# before IBM Plex Sans has loaded, about 8% too narrow, and long y-axis labels then overflow on the left.
LABEL_CHART_PADDING = {"left": 16, "top": 5, "right": 5, "bottom": 5}


# ── drawings ────────────────────────────────────────────────────────────────

def _ring(cx: float, cy: float, vertical: bool, r: float = 8.5) -> str:
    """A benzene ring on a linker, para-connected along the linker's direction."""
    start = 30 if vertical else 0
    pts = " ".join(f"{cx + r * math.cos(math.radians(start + 60 * k)):.1f},"
                   f"{cy + r * math.sin(math.radians(start + 60 * k)):.1f}" for k in range(6))
    return f'<polygon class="r" points="{pts}"/>'


def _net(ox: float, oy: float, cols: int, rows: int, step: int, glow=frozenset()) -> str:
    """One layer of a cubic net: linkers (line + ring) between neighbouring nodes, then the metal nodes."""
    out = []
    for r in range(rows):
        for c in range(cols):
            x, y = ox + c * step, oy + r * step
            if c + 1 < cols:
                out.append(f'<line class="l" x1="{x}" y1="{y}" x2="{x + step}" y2="{y}"/>'
                           + _ring(x + step / 2, y, vertical=False))
            if r + 1 < rows:
                out.append(f'<line class="l" x1="{x}" y1="{y}" x2="{x}" y2="{y + step}"/>'
                           + _ring(x, y + step / 2, vertical=True))
    for r in range(rows):
        for c in range(cols):
            x, y = ox + c * step, oy + r * step
            extra = ' class="n g" filter="url(#glow)"' if (c, r) in glow else ' class="n"'
            out.append(f'<rect{extra} x="{x - 7}" y="{y - 7}" width="14" height="14" rx="3.5"/>')
    return "".join(out)


# st.html sanitises inline <svg>, so drawings travel as <img> data URIs and carry their own styles.
_FRAMEWORK_STYLE = """<style>
.l { stroke: #4CC9DB; stroke-width: 2.4; stroke-linecap: round; stroke-opacity: .72; }
.r { fill: #0F2C38; fill-opacity: .7; stroke: #7FDCE9; stroke-width: 1.6; }
.s { stroke: #4CC9DB; stroke-width: 1.4; stroke-opacity: .38; stroke-dasharray: 2 5; }
.n { fill: #E2884F; stroke: #FFC9A3; stroke-width: 1.4; }
.g { fill: #F2A774; }
.back { opacity: .36; }
</style><defs><filter id="glow" x="-1" y="-1" width="3" height="3"><feGaussianBlur stdDeviation="3.2" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>"""


def _img(svg: str, cls: str, size: int | None = None) -> str:
    dims = f' width="{size}" height="{size}"' if size else ""
    return (f'<img class="{cls}"{dims} alt="" aria-hidden="true" '
            f'src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}">')


def framework_svg(cols: int = 6, rows: int = 4, step: int = 92, depth: tuple[int, int] = (40, -32)) -> str:
    """A MOF-5-style framework drawn as two layers of a cubic net: copper metal
    clusters at the nodes, teal linkers with a benzene ring at each midpoint,
    dashed struts between the layers for depth."""
    pad, (dx, dy) = 24, depth
    ox, oy = pad, pad - dy
    w = 2 * pad + (cols - 1) * step + dx
    h = 2 * pad + (rows - 1) * step - dy
    struts = "".join(f'<line class="s" x1="{ox + c * step}" y1="{oy + r * step}" '
                     f'x2="{ox + c * step + dx}" y2="{oy + r * step + dy}"/>'
                     for r in range(rows) for c in range(cols))
    back = _net(ox + dx, oy + dy, cols, rows, step)
    front = _net(ox, oy, cols, rows, step, glow=frozenset({(1, 1), (3, 2), (4, 0)}))
    return (f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">{_FRAMEWORK_STYLE}'
            f'<g class="back">{back}</g>{struts}<g>{front}</g></svg>')


def cell_svg(size: int = 40, edge: str = "#22B8CF", node: str = "#E2884F") -> str:
    """A cubic unit cell: eight metal nodes joined by linkers (the brand mark)."""
    f = [(6, 14), (26, 14), (26, 34), (6, 34)]
    b = [(x + 8, y - 8) for x, y in f]

    def line(p, q, opacity):
        return (f'<line x1="{p[0]}" y1="{p[1]}" x2="{q[0]}" y2="{q[1]}" stroke="{edge}" '
                f'stroke-width="1.8" stroke-opacity="{opacity}" stroke-linecap="round"/>')

    lines = ("".join(line(b[i], b[(i + 1) % 4], .45) for i in range(4))
             + "".join(line(f[i], b[i], .7) for i in range(4))
             + "".join(line(f[i], f[(i + 1) % 4], 1) for i in range(4)))
    nodes = "".join(f'<circle cx="{x}" cy="{y}" r="2.9" fill="{node}"/>' for x, y in b + f)
    return f'<svg viewBox="0 0 40 40" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">{lines}{nodes}</svg>'


def _inline(text: str) -> str:
    """Escape text for HTML, keeping `code` and **bold** spans."""
    s = html.escape(text)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)


# ── stylesheet ──────────────────────────────────────────────────────────────

CSS = """
:root {
  --mc-ink: #0F2733; --mc-ink-soft: #4F6873; --mc-muted: #6B8590;
  --mc-ground: #F4F7F8; --mc-card: #FFFFFF; --mc-rule: #D2DEE2;
  --mc-teal: #0E7490; --mc-teal-bright: #0891B2; --mc-teal-glow: #22B8CF;
  --mc-copper: #D9622B; --mc-copper-soft: #F2A774; --mc-navy: #0B1F2A;
  --mc-shadow: 0 1px 2px rgba(15, 39, 51, .05), 0 6px 20px -8px rgba(15, 39, 51, .14);
  --mc-shadow-lg: 0 2px 4px rgba(15, 39, 51, .06), 0 22px 44px -18px rgba(15, 39, 51, .32);
  --mc-display: "Space Grotesk", "IBM Plex Sans", system-ui, sans-serif;
  --mc-mono: "IBM Plex Mono", ui-monospace, monospace;
}

/* ── page ────────────────────────────────────────────────────────────── */
.stApp { background:
    radial-gradient(1100px 520px at 105% -8%, rgba(8, 145, 178, .09), transparent 62%) fixed,
    radial-gradient(900px 480px at -12% 108%, rgba(217, 98, 43, .06), transparent 60%) fixed,
    var(--mc-ground); }
[data-testid="stHeader"] { background: rgba(244, 247, 248, .82); backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(210, 222, 226, .7); }
[data-testid="stMainBlockContainer"] { max-width: 1240px; padding-top: 4.4rem; }
[data-testid="stBottom"] > div { background: transparent; }
[data-testid="stBottomBlockContainer"] { max-width: 1240px;
  background: linear-gradient(to top, var(--mc-ground) 62%, rgba(244, 247, 248, 0)); }

/* ── navigation ──────────────────────────────────────────────────────── */
[data-testid="stTopNavLink"] { border-radius: 999px; padding: .32rem .9rem; transition: background .2s ease; }
[data-testid="stTopNavLink"]:hover { background: rgba(8, 145, 178, .09); }
[data-testid="stTopNavLink"][aria-current="page"] { background: var(--mc-navy);
  box-shadow: 0 6px 16px -8px rgba(11, 31, 42, .7); }
[data-testid="stTopNavLink"][aria-current="page"] * { color: #FFFFFF; }

/* ── headings ────────────────────────────────────────────────────────── */
[data-testid="stMainBlockContainer"] h3 { letter-spacing: -.01em; margin-top: 1.5rem; }
[data-testid="stMainBlockContainer"] [data-testid="stHeading"] h3::before { content: "";
  display: inline-block; width: .5rem; height: .5rem; border-radius: 2px; margin-right: .7rem;
  background: var(--mc-copper); transform: translateY(-.15rem) rotate(45deg);
  box-shadow: 0 0 0 3px rgba(217, 98, 43, .14); }

.mc-overline { display: flex; align-items: center; gap: .5rem; font-size: .76rem; font-weight: 600;
  letter-spacing: .16em; text-transform: uppercase; color: var(--mc-teal); }
.mc-overline img { flex: none; }
.mc-sub code, .mc-step code { font-family: var(--mc-mono); font-size: .86em; background: #E8EFF1;
  padding: .06rem .35rem; border-radius: 5px; color: #173B4A; }

/* ── masthead (chat landing) ─────────────────────────────────────────── */
.mc-hero { position: relative; overflow: hidden; isolation: isolate; border-radius: 22px;
  padding: 2.1rem 2.5rem 1.9rem; margin: 0 0 1.2rem; color: #E6F1F3; box-shadow: var(--mc-shadow-lg);
  background: radial-gradient(720px 380px at 86% 32%, rgba(34, 184, 207, .30), transparent 66%),
              linear-gradient(135deg, #0B1F2A 0%, #0D2F3D 55%, #0E4A5C 100%); }
.mc-hero::after { content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  border: 1px solid rgba(255, 255, 255, .08); }
.mc-hero-text { position: relative; z-index: 2; max-width: 640px; }
.mc-hero .mc-overline { color: var(--mc-copper-soft); }
.mc-hero h1 { font-family: var(--mc-display); font-weight: 700; font-size: clamp(2.5rem, 4.8vw, 3.6rem);
  line-height: 1; letter-spacing: -.035em; color: #FFFFFF; margin: .5rem 0 .7rem; padding: 0; }
.mc-hero h1 em { font-style: normal; color: transparent; -webkit-background-clip: text; background-clip: text;
  background-image: linear-gradient(90deg, #7FDCE9, #22B8CF 45%, #F2A774); }
.mc-hero .mc-sub { color: #B9D2D8; font-size: 1rem; line-height: 1.55; margin: 0 0 1.2rem; max-width: 560px;
  text-shadow: 0 1px 14px rgba(11, 31, 42, .9); }
.mc-hero .mc-sub code { background: rgba(255, 255, 255, .1); color: #E6F1F3; }
.mc-stats { display: flex; flex-wrap: wrap; gap: .6rem; }
.mc-stat { display: flex; align-items: baseline; gap: .45rem; padding: .5rem .9rem; border-radius: 12px;
  background: rgba(255, 255, 255, .06); border: 1px solid rgba(255, 255, 255, .13); backdrop-filter: blur(6px); }
.mc-stat b { font-family: var(--mc-display); font-size: 1.18rem; font-weight: 600; color: #FFFFFF; }
.mc-stat span { font-size: .84rem; color: #A9C4CB; }

.mc-lattice { position: absolute; z-index: 1; right: -36px; top: 50%; width: min(580px, 56%);
  transform: translateY(-50%); pointer-events: none;
  -webkit-mask-image: linear-gradient(90deg, transparent 0%, rgba(0, 0, 0, .25) 32%, #000 62%);
          mask-image: linear-gradient(90deg, transparent 0%, rgba(0, 0, 0, .25) 32%, #000 62%); }
.mc-lattice img { display: block; width: 100%; height: auto; animation: mc-drift 16s ease-in-out infinite alternate; }
@keyframes mc-drift { from { transform: translate3d(0, -6px, 0); } to { transform: translate3d(-12px, 6px, 0); } }
@media (prefers-reduced-motion: reduce) { .mc-lattice img { animation: none; } }
@media (max-width: 900px) {
  .mc-hero { padding: 1.9rem 1.4rem 1.7rem; }
  .mc-lattice { width: 92%; opacity: .3; }
}

/* ── page header (other pages) ───────────────────────────────────────── */
.mc-page { position: relative; margin: 0 0 1.7rem; padding-bottom: 1.15rem; }
.mc-page::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 2px; border-radius: 2px;
  background: linear-gradient(90deg, var(--mc-teal-bright), var(--mc-copper) 36%, rgba(210, 222, 226, .6) 70%,
                              transparent); }
.mc-page h1 { font-family: var(--mc-display); font-weight: 700; font-size: clamp(2rem, 3.6vw, 2.75rem);
  letter-spacing: -.028em; line-height: 1.1; color: var(--mc-ink); margin: .5rem 0 .55rem; padding: 0; }
.mc-page .mc-sub { color: var(--mc-ink-soft); max-width: 900px; margin: 0; line-height: 1.6; }

/* ── chat landing: suggestions and how-it-works ──────────────────────── */
.mc-label { font-size: .76rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
  color: var(--mc-muted); margin: .2rem 0 -.2rem; }
.st-key-suggestion button { background: var(--mc-card); border: 1px solid var(--mc-rule); border-radius: 999px;
  padding: .45rem 1rem; box-shadow: 0 1px 2px rgba(15, 39, 51, .05);
  transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease, color .15s ease; }
.st-key-suggestion button:hover { border-color: var(--mc-teal-bright); color: var(--mc-teal);
  transform: translateY(-1px); box-shadow: 0 8px 18px -10px rgba(8, 145, 178, .55); }
.st-key-suggestion button [data-testid="stIconMaterial"] { color: var(--mc-copper); }
.mc-steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: .8rem;
  margin-top: 1rem; }
.mc-step { position: relative; overflow: hidden; background: var(--mc-card); border: 1px solid var(--mc-rule);
  border-radius: 16px; padding: .9rem 1.05rem .95rem 1.2rem; box-shadow: var(--mc-shadow); }
.mc-step::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: linear-gradient(var(--mc-teal-bright), var(--mc-copper)); }
.mc-step-n { display: inline-grid; place-items: center; width: 1.6rem; height: 1.6rem; border-radius: 8px;
  margin-bottom: .45rem; background: #E1F2F6; color: var(--mc-teal); font-family: var(--mc-display);
  font-weight: 700; font-size: .9rem; }
.mc-step b { display: block; font-family: var(--mc-display); font-size: 1.03rem; color: var(--mc-ink);
  margin-bottom: .3rem; }
.mc-step p { margin: 0; color: var(--mc-ink-soft); font-size: .88rem; line-height: 1.5; }
/* On phones the chat sticks to the bottom; keep the landing short so the masthead and suggestions stay in reach. */
@media (max-width: 640px) { .mc-steps { display: none; } }

/* ── chat ────────────────────────────────────────────────────────────── */
[data-testid="stChatMessage"] { background: var(--mc-card); border: 1px solid var(--mc-rule); border-radius: 18px;
  padding: 1.05rem 1.25rem; margin-bottom: .9rem; box-shadow: var(--mc-shadow); }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background: linear-gradient(135deg, #E4F3F7, #EEF7F9); border-color: #C3E2EA; }
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"] {
  width: 2.15rem; height: 2.15rem; border-radius: 10px; }
[data-testid="stChatMessageAvatarUser"] { background: var(--mc-navy); }
[data-testid="stChatMessageAvatarAssistant"] { background: linear-gradient(135deg, var(--mc-teal-bright), #0E4A5C);
  box-shadow: 0 6px 14px -8px rgba(8, 145, 178, .9); }
[data-testid="stChatMessageAvatarUser"] *, [data-testid="stChatMessageAvatarAssistant"] * { color: #FFFFFF; }
[data-testid="stChatInput"] { background: var(--mc-card); border: 1px solid var(--mc-rule); border-radius: 16px;
  box-shadow: var(--mc-shadow-lg); }
[data-testid="stChatInput"]:focus-within { border-color: var(--mc-teal-bright);
  box-shadow: 0 0 0 4px rgba(8, 145, 178, .13), var(--mc-shadow-lg); }
[data-testid="stChatInput"] > div, [data-testid="stChatInput"] textarea { background: transparent; }
[data-testid="stChatInputSubmitButton"]:not(:disabled) { background: var(--mc-teal); color: #FFFFFF; border-radius: 10px; }

/* ── surfaces ────────────────────────────────────────────────────────── */
[data-testid="stExpander"] details { background: var(--mc-card); border: 1px solid var(--mc-rule); border-radius: 12px;
  box-shadow: 0 1px 2px rgba(15, 39, 51, .04); }
[data-testid="stExpander"] summary { font-weight: 500; }
[data-testid="stExpander"] summary:hover { color: var(--mc-teal); }
[data-testid="stExpander"] summary [data-testid="stIconMaterial"] { color: var(--mc-teal-bright); }
[data-testid="stMetric"] { position: relative; overflow: hidden; background: var(--mc-card); border-radius: 14px;
  box-shadow: var(--mc-shadow); }
[data-testid="stMetric"]::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px;
  background: linear-gradient(90deg, var(--mc-teal-bright), var(--mc-copper)); }
[data-testid="stMetricLabel"] p { font-size: .74rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
  color: var(--mc-muted); }
[data-testid="stMetricValue"] { font-family: var(--mc-display); letter-spacing: -.02em; color: var(--mc-ink); }
[data-testid="stForm"], .st-key-filters { background: var(--mc-card); border-radius: 16px; box-shadow: var(--mc-shadow); }
[data-testid="stDataFrame"] { border-radius: 12px; box-shadow: var(--mc-shadow); }
/* The card sits on the chart's wrapper: Vega sizes itself from its own box, so padding there would clip labels. */
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]:has([data-testid="stVegaLiteChart"]) {
  background: var(--mc-ground); border: 1px solid var(--mc-rule); border-radius: 14px; padding: .8rem .9rem .5rem; }
[data-testid="stMainBlockContainer"] [data-testid="stImage"] img { background: #FFFFFF; border: 1px solid var(--mc-rule);
  border-radius: 14px; padding: 10px; box-shadow: var(--mc-shadow); }
[data-testid="stCode"] pre { border: 1px solid var(--mc-rule); border-radius: 12px; }
[data-testid="stAlert"] { border-radius: 12px; }
[data-testid="stMainBlockContainer"] table { border-collapse: separate; border-spacing: 0; width: 100%;
  background: var(--mc-card); border: 1px solid var(--mc-rule); border-radius: 12px; overflow: hidden;
  box-shadow: var(--mc-shadow); }
[data-testid="stMainBlockContainer"] th { background: #E8EFF1; font-family: var(--mc-display); font-weight: 600; }
[data-testid="stMainBlockContainer"] th, [data-testid="stMainBlockContainer"] td { border: 0;
  border-bottom: 1px solid var(--mc-rule); padding: .65rem .9rem; vertical-align: top; }
[data-testid="stMainBlockContainer"] tr:last-child td { border-bottom: 0; }

/* ── controls ────────────────────────────────────────────────────────── */
[data-testid="stBaseButton-primaryFormSubmit"], [data-testid="stBaseButton-primary"] { border: 0;
  background: linear-gradient(135deg, #0E7490, #0B5C72); box-shadow: 0 8px 18px -10px rgba(14, 116, 144, .85);
  transition: transform .15s ease, box-shadow .15s ease; }
[data-testid="stBaseButton-primaryFormSubmit"]:hover, [data-testid="stBaseButton-primary"]:hover {
  transform: translateY(-1px); box-shadow: 0 12px 22px -10px rgba(14, 116, 144, .95); }
[data-testid="stMainBlockContainer"] [data-testid="stBaseButton-secondary"] { background: var(--mc-card); }

/* ── sidebar ─────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] { border-right: 1px solid #1B3A48;
  background: radial-gradient(520px 320px at 0% 0%, rgba(34, 184, 207, .16), transparent 62%),
              linear-gradient(180deg, #0B1F2A 0%, #0A1A23 100%); }
[data-testid="stSidebarHeader"] { margin-bottom: 0; }
[data-testid="stSidebar"] h3 { font-size: .74rem; font-weight: 600; letter-spacing: .16em; text-transform: uppercase;
  color: #7FA3AE; margin-top: 1.1rem; }
[data-testid="stSidebar"] .stButton button { background: rgba(255, 255, 255, .04); border: 1px solid #24485A;
  color: #DCE8EB; }
[data-testid="stSidebar"] .stButton button:hover { background: rgba(34, 184, 207, .12); border-color: var(--mc-teal-glow);
  color: #FFFFFF; }
[data-testid="stSidebar"] [data-testid="stExpander"] details { background: rgba(255, 255, 255, .03);
  border-color: #24485A; box-shadow: none; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover { color: #FFFFFF; }
.mc-brand { display: flex; align-items: center; gap: .8rem; padding: 0 0 1.15rem; margin: -.4rem 0 .2rem;
  border-bottom: 1px solid #1E3E4D; }
.mc-brand img { flex: none; filter: drop-shadow(0 0 10px rgba(34, 184, 207, .4)); }
.mc-brand-name { font-family: var(--mc-display); font-weight: 700; font-size: 1.4rem; letter-spacing: -.025em;
  line-height: 1.1; color: #FFFFFF; }
.mc-brand-name em { font-style: normal; color: #5FD0E0; }
.mc-brand-tag { font-size: .75rem; letter-spacing: .03em; color: #7FA3AE; }
.stApp .mc-status { list-style: none; margin: .2rem 0 .5rem; padding: 0; display: grid; gap: .4rem; }
.stApp .mc-status li { display: flex; align-items: flex-start; gap: .7rem; margin: 0; padding: .55rem .75rem;
  border-radius: 10px; background: rgba(255, 255, 255, .035); border: 1px solid rgba(255, 255, 255, .06); }
.mc-status .dot { flex: none; width: .55rem; height: .55rem; margin-top: .4rem; border-radius: 50%;
  background: #34D399; box-shadow: 0 0 0 3px rgba(52, 211, 153, .16), 0 0 10px rgba(52, 211, 153, .55); }
.mc-status li.bad .dot { background: #F87171; box-shadow: 0 0 0 3px rgba(248, 113, 113, .16); }
.mc-status b { display: block; font-weight: 500; font-size: .9rem; line-height: 1.3; color: #E6F1F3; }
.mc-status small { display: block; margin-top: .1rem; font-size: .78rem; line-height: 1.35; color: #8FB0BA; }

/* ── colophon ────────────────────────────────────────────────────────── */
.mc-colophon { display: flex; flex-wrap: wrap; justify-content: space-between; gap: .4rem 1.2rem;
  margin-top: 3.2rem; padding-top: 1rem; border-top: 1px solid var(--mc-rule); font-size: .82rem;
  color: var(--mc-muted); }
.mc-colophon b { font-family: var(--mc-display); font-weight: 600; color: var(--mc-ink-soft); }
"""


# ── components ──────────────────────────────────────────────────────────────

def apply_theme() -> None:
    """Inject the stylesheet. Call once per script run, before any output."""
    st.html(f"<style>{CSS}</style>")


def brand() -> None:
    """Sidebar wordmark: unit-cell mark, name and course line."""
    st.html(f'<div class="mc-brand">{_img(cell_svg(42), "mc-mark", 42)}<div>'
            '<div class="mc-brand-name">MOF<em>Chat</em></div>'
            '<div class="mc-brand-tag">Team 09 · 22AIE452</div></div></div>')


def hero(title: str, accent: str, overline: str, subtitle: str, stats: list[tuple[str, str]]) -> None:
    """Landing masthead: overline, title (accent part in the teal-copper gradient), subtitle,
    stat chips, and the framework drawing on the right."""
    chips = "".join(f'<div class="mc-stat"><b>{html.escape(v)}</b><span>{html.escape(k)}</span></div>'
                    for v, k in stats)
    st.html(f'<div class="mc-hero"><div class="mc-hero-text">'
            f'<div class="mc-overline">{html.escape(overline)}</div>'
            f'<h1>{html.escape(title)}<em>{html.escape(accent)}</em></h1>'
            f'<p class="mc-sub">{_inline(subtitle)}</p><div class="mc-stats">{chips}</div></div>'
            f'<div class="mc-lattice">{_img(framework_svg(), "mc-framework")}</div></div>')


def page_header(title: str, overline: str, subtitle: str = "") -> None:
    """Title block for a page: overline with the unit-cell mark, title, subtitle and a teal-copper rule."""
    sub = f'<p class="mc-sub">{_inline(subtitle)}</p>' if subtitle else ""
    st.html(f'<div class="mc-page"><div class="mc-overline">{_img(cell_svg(18, "#0891B2", "#D9622B"), "mc-mark", 18)}'
            f'{html.escape(overline)}</div><h1>{html.escape(title)}</h1>{sub}</div>')


def section_label(text: str) -> None:
    st.html(f'<div class="mc-label">{html.escape(text)}</div>')


def steps(items: list[tuple[str, str]]) -> None:
    """A numbered strip of (title, text) cards."""
    cards = "".join(f'<div class="mc-step"><span class="mc-step-n">{i}</span><b>{html.escape(t)}</b>'
                    f'<p>{_inline(p)}</p></div>' for i, (t, p) in enumerate(items, 1))
    st.html(f'<div class="mc-steps">{cards}</div>')


def status_list(items: list[tuple[bool, str, str]]) -> None:
    """Sidebar system status: (ok, name, detail). The detail always says the state in words, so the
    dot colour is never the only signal."""
    rows = "".join(f'<li class="{"ok" if ok else "bad"}"><span class="dot"></span><div>'
                   f'<b>{html.escape(name)}</b><small>{html.escape(detail)}</small></div></li>'
                   for ok, name, detail in items)
    st.html(f'<ul class="mc-status">{rows}</ul>')


def colophon() -> None:
    st.html('<div class="mc-colophon"><span><b>MOFChat</b> · Team 09 · 22AIE452 Data Driven Material '
            'Modeling and Simulation</span><span>Data: CoRE-MOF 2019, as used by ChatMOF '
            '(Kang &amp; Kim, <i>Nat. Commun.</i> 2024)</span></div>')
