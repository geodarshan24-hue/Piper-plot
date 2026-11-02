"""
Piper diagram plotter: upload an Excel/CSV file and plot the samples.

Run as a web app (upload button):
    pip install streamlit pandas matplotlib openpyxl
    streamlit run piper_app.py

Or from the command line:
    python piper_app.py my_data.xlsx --units mgl --out piper.png

Expected columns (names are matched flexibly, case-insensitive):
    Ca, Mg, Na, K, HCO3, CO3 (optional), Cl, SO4
Optional columns:
    Sample / ID / Name   -> label for each sample
    Group / Type / Class -> every class gets its own symbol and colour
    TDS                  -> marker size follows TDS (mg/L)
Every sample is also put into one of the 6 fields of the Piper diamond (see QUADS); the number of the
field is shown in the plot, in the tables and in the downloaded CSV.
Values are in mg/L (default) or meq/L.

All text is Times New Roman (falls back to a Times-like font if it is not installed).
Font sizes can be changed in the web app (sidebar -> "Text") or with --font-scale / --sizes.

Symbols and colours: in the web app pick them for each class in the sidebar.
From the command line use  --style "Deep=circle:#e8508a" --style "Shallow=plus:#2a6fd6"
(symbol names: see SYMBOLS below, or run  python piper_app.py --list-symbols).
Default: groups named "Shallow" / "Deep" get a blue + and a pink open circle; if the names also
say fresh / brackish / saline, colour = salinity and symbol = depth.
"""
import io
import re
import sys

import numpy as np
import pandas as pd
import matplotlib

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.colors import to_rgba
from matplotlib.patches import Patch

H = np.sqrt(3) / 2           # height factor for an equilateral triangle
GAP = 20                     # horizontal gap between the two triangles
LX0, RX0 = 0, 100 + GAP      # x-origins of cation / anion triangles
DB = (100 + GAP / 2, GAP / 2 * np.sqrt(3))  # bottom vertex of the diamond

# Equivalent weights (mg per meq) used to convert mg/L -> meq/L
EQ_WT = {"Ca": 20.04, "Mg": 12.15, "Na": 22.99, "K": 39.10,
         "HCO3": 61.02, "CO3": 30.00, "Cl": 35.45, "SO4": 48.03}

ALIASES = {
    "Ca": ["ca", "ca2", "calcium"],
    "Mg": ["mg", "mg2", "magnesium"],
    "Na": ["na", "na1", "sodium"],
    "K": ["k", "k1", "potassium"],
    "HCO3": ["hco3", "bicarbonate", "hco3co3", "alkalinity"],
    "CO3": ["co3", "carbonate", "co32"],
    "Cl": ["cl", "chloride", "cl1"],
    "SO4": ["so4", "sulfate", "sulphate", "so42"],
}
LABEL_ALIASES = ["sample", "sampleid", "id", "name", "station", "well", "label"]
GROUP_ALIASES = ["group", "type", "class", "category", "facies", "zone"]
TDS_ALIASES = ["tds", "tdsmgl", "totaldissolvedsolids"]

# ----------------------------------------------------------------- fonts / sizes
FONT_FAMILY = "Times New Roman"
FONT_FALLBACK = ["Liberation Serif", "Nimbus Roman", "TeX Gyre Termes", "STIXGeneral", "DejaVu Serif"]

# font sizes in points (the web app and --sizes let you change them)
FS_DEFAULT = {"title": 16, "axis": 11, "tick": 9, "legend": 12, "note": 10, "zone": 10, "label": 7}
FS_NAMES = {"title": "Title", "axis": "Axis names (Ca, Mg, Na+K ...)", "tick": "Tick numbers",
            "legend": "Legend / group names", "note": "Captions (Cations / Anions)",
            "zone": "Water-type zone names", "label": "Sample labels"}


def set_font(family=FONT_FAMILY):
    """Times New Roman for everything (also for the sub/superscripts in the ion names)."""
    stack = [family] + [f for f in FONT_FALLBACK if f != family]
    plt.rcParams.update({"font.family": "serif", "font.serif": stack,
                         "mathtext.fontset": "stix", "mathtext.default": "regular",
                         "axes.unicode_minus": False})


def _font_sizes(font_scale=1.0, font_sizes=None):
    fs = {**FS_DEFAULT, **(font_sizes or {})}
    return {k: v * font_scale for k, v in fs.items()}


_SUB = {"₂": "2", "₃": "3", "₄": "4"}


def _chem(s):
    """'HCO₃' -> mathtext so the subscript is drawn in the same serif font."""
    return re.sub("[₂₃₄]", lambda m: "$_{%s}$" % _SUB[m.group()], s)


# ------------------------------------------------------------------- colours
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK_SOFT = "#2b2a28", "#6b6a66"
GRID, EDGE, PANEL = "#dcdbd6", "#55544f", "#f7f6f3"

# The 6 fields of the Piper diamond (field number = position in the list + 1):
#   a = Ca + Mg (%),  b = SO4 + Cl (%)
#   1  a + b >= 150                    Ca-Mg-Cl-SO4    (top corner)
#   2  a >= 50 and b < 50              Ca-Mg-HCO3      (left corner)
#   3  a + b <= 50                     Na-K-HCO3       (bottom corner)
#   4  a < 50 and b < 50 (a + b > 50)  Mixed Ca-Na-HCO3
#   5  a >= 50 and b >= 50 (a+b<150)   Mixed Ca-Mg-Cl
#   6  a < 50 and b >= 50              Na-K-Cl         (right corner)
QUADS = [   # name, meaning, colour
    ("Ca–Mg–Cl–SO₄",     "permanent hardness", "#c58a12"),
    ("Ca–Mg–HCO₃",       "fresh recharge",     "#3f9a6b"),
    ("Na–K–HCO₃",        "evolved / alkali",   "#4f86a3"),
    ("Mixed Ca–Na–HCO₃", "mixed type",         "#8a77b0"),
    ("Mixed Ca–Mg–Cl",   "mixed type",         "#a0673a"),
    ("Na–K–Cl",          "saline / marine",    "#c8506a"),
]
# every field as a polygon in (Ca+Mg, SO4+Cl) coordinates, and where its number is written
FIELD_POLY = [
    [(100, 50), (100, 100), (50, 100)],
    [(50, 0), (100, 0), (100, 50), (50, 50)],
    [(0, 0), (50, 0), (0, 50)],
    [(50, 0), (50, 50), (0, 50)],
    [(50, 50), (100, 50), (50, 100)],
    [(0, 50), (50, 50), (50, 100), (0, 100)],
]
FIELD_NUM_AT = [(86, 86), (80, 20), (11, 11), (34, 34), (72, 72), (20, 80)]

# --------------------------------------------------------------------- symbols
# code: (label shown in the menu, matplotlib marker, filled?)
SYMBOLS = {
    "plus":                 ("Plus  +", "+", False),
    "cross":                ("Cross  ×", "x", False),
    "circle":               ("Open circle  ○", "o", False),
    "circle-filled":        ("Filled circle  ●", "o", True),
    "square":               ("Open square  □", "s", False),
    "square-filled":        ("Filled square  ■", "s", True),
    "triangle":             ("Open triangle  △", "^", False),
    "triangle-filled":      ("Filled triangle  ▲", "^", True),
    "triangle-down":        ("Open inverted triangle  ▽", "v", False),
    "triangle-down-filled": ("Filled inverted triangle  ▼", "v", True),
    "diamond":              ("Open diamond  ◇", "D", False),
    "diamond-filled":       ("Filled diamond  ◆", "D", True),
    "star":                 ("Open star  ☆", "*", False),
    "star-filled":          ("Filled star  ★", "*", True),
    "y-mark":               ("Thin Y symbol", "1", False),
}
LINE_ONLY = {"+", "x", "1"}                       # symbols that are only lines (no inside)
SCALE = {"+": 1.15, "x": 0.85, "1": 1.5, "o": 1.0, "s": 0.85, "^": 1.05, "v": 1.05, "D": 0.8, "*": 1.7}
LEGEND_MS = {"+": 10, "x": 8, "1": 11, "o": 9, "s": 8, "^": 9, "v": 9, "D": 7, "*": 13}
_MARKER_TO_CODE = {(m, f): c for c, (_, m, f) in SYMBOLS.items()}

DEPTH_COL = {"shallow": "#2a6fd6", "deep": "#e8508a"}      # blue + / pink circle
SAL_COL = {"fresh": "#2a78d6", "brack": "#eb6834", "salin": "#6250d6"}
DEPTH_MK = {"shallow": "+", "deep": "o"}
CYCLE_MK = ["+", "x", "o", "1"]


def symbol_code(marker, filled):
    return _MARKER_TO_CODE.get((marker, filled), "plus")


def parse_style(spec):
    """'Deep=circle:#e8508a'  ->  ('Deep', ('#e8508a', 'o', False))"""
    try:
        name, rest = spec.split("=", 1)
        code, colour = rest.rsplit(":", 1)
    except ValueError:
        raise ValueError(f'Bad --style "{spec}". Use  GROUP=SYMBOL:COLOUR  e.g. "Deep=circle:#e8508a"')
    code = code.strip().lower()
    if code not in SYMBOLS:
        raise ValueError(f'Unknown symbol "{code}". Choose from: {", ".join(SYMBOLS)}')
    return name.strip(), (colour.strip(), SYMBOLS[code][1], SYMBOLS[code][2])


# ------------------------------------------------------------------ data prep
def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower().replace("+", "").replace("-", ""))


def _find(df, names):
    lookup = {_norm(c): c for c in df.columns}
    for n in names:
        if n in lookup:
            return lookup[n]
    return None


def prepare(df, units="mgl"):
    """Return a DataFrame of % meq/L for all ions plus label/group/TDS and
    the Piper-diamond field (1-6) of every sample."""
    cols = {}
    for ion, names in ALIASES.items():
        c = _find(df, names)
        if c is not None:
            cols[ion] = c
    missing = [i for i in ["Ca", "Mg", "Na", "K", "HCO3", "Cl", "SO4"] if i not in cols]
    if missing:
        raise ValueError(
            f"Could not find column(s) for: {', '.join(missing)}. "
            f"Columns found: {list(df.columns)}")

    ions = pd.DataFrame(index=df.index)
    for ion in EQ_WT:
        if ion in cols:
            ions[ion] = pd.to_numeric(df[cols[ion]], errors="coerce").fillna(0)
        else:
            ions[ion] = 0.0
    if units == "mgl":
        for ion in EQ_WT:
            ions[ion] = ions[ion] / EQ_WT[ion]

    out = pd.DataFrame(index=df.index)
    cat = ions["Ca"] + ions["Mg"] + ions["Na"] + ions["K"]
    an = ions["HCO3"] + ions["CO3"] + ions["Cl"] + ions["SO4"]
    out["Ca"] = 100 * ions["Ca"] / cat
    out["Mg"] = 100 * ions["Mg"] / cat
    out["NaK"] = 100 * (ions["Na"] + ions["K"]) / cat
    out["HCO3"] = 100 * (ions["HCO3"] + ions["CO3"]) / an
    out["SO4"] = 100 * ions["SO4"] / an
    out["Cl"] = 100 * ions["Cl"] / an

    lc = _find(df, LABEL_ALIASES)
    gc = _find(df, GROUP_ALIASES)
    tc = _find(df, TDS_ALIASES)
    out["label"] = df[lc].astype(str) if lc else [str(i + 1) for i in range(len(df))]
    out["group"] = df[gc].astype(str).str.strip() if gc else "Samples"
    out["tds"] = pd.to_numeric(df[tc], errors="coerce") if tc else np.nan
    out = out.dropna(subset=["Ca", "Mg", "NaK", "HCO3", "SO4", "Cl"])
    return classify(out)


def classify(out):
    """Add the diamond field (1-6, see QUADS) and the dominant-ion facies of every sample."""
    a = out["Ca"] + out["Mg"]
    b = out["SO4"] + out["Cl"]
    q = np.select([a + b >= 150, a + b <= 50, (a >= 50) & (b < 50),
                   (a < 50) & (b >= 50), (a >= 50) & (b >= 50)],
                  [0, 2, 1, 5, 4], default=3)
    out["quad"] = q
    out["field"] = q + 1
    out["water_type"] = [QUADS[i][0] for i in q]

    def dom(row):
        c = ("Ca" if row.Ca > 50 else "Mg" if row.Mg > 50 else "Na+K" if row.NaK > 50 else "Mixed")
        a = ("HCO3" if row.HCO3 > 50 else "SO4" if row.SO4 > 50 else "Cl" if row.Cl > 50 else "Mixed")
        return f"{c} – {a}"
    out["facies"] = out.apply(dom, axis=1)
    return out


def summary_table(data):
    g = data.groupby("group", sort=False)
    t = g[["Ca", "Mg", "NaK", "HCO3", "SO4", "Cl"]].mean().round(1)
    t.insert(0, "n", g.size())
    t["most common field"] = g["quad"].agg(
        lambda s: f"{int(s.mode().iloc[0]) + 1}. {QUADS[int(s.mode().iloc[0])][0]}")
    return t


def field_table(data):
    """Number of samples (and % of the group) of every group in each of the 6 fields."""
    cnt = pd.crosstab(data["group"], data["quad"]).reindex(
        index=list(dict.fromkeys(data["group"])), columns=range(6), fill_value=0)
    pct = cnt.div(cnt.sum(axis=1), axis=0) * 100
    t = pd.DataFrame({f"{i + 1}. {QUADS[i][0]}": [f"{c} ({p:.0f}%)" for c, p in zip(cnt[i], pct[i])]
                      for i in range(6)}, index=cnt.index)
    t.insert(0, "n", cnt.sum(axis=1))
    return t


# ------------------------------------------------------------------- geometry
def _tri_xy(left, right, top, x0):
    """Ternary -> cartesian (left, right, top are %, left+right+top = 100)."""
    return x0 + right + top / 2, top * H


def _diamond_xy(ca_mg, so4_cl):
    return (DB[0] + 0.5 * (so4_cl - ca_mg),
            DB[1] + H * (so4_cl + ca_mg))


def draw_frame(ax, zones=True, fs=None):
    fs = fs or _font_sizes()
    grid = dict(color=GRID, lw=0.7, zorder=1)
    edge = dict(color=EDGE, lw=1.1, zorder=2, solid_joinstyle="miter")
    tick = dict(fontsize=fs["tick"], color=INK_SOFT, zorder=3)
    title = dict(fontsize=fs["axis"], weight="bold", color=INK, zorder=3)
    bx, by = DB

    # --- triangles
    for x0 in (LX0, RX0):
        ax.fill([x0, x0 + 100, x0 + 50], [0, 0, 100 * H], color=PANEL, zorder=0)
        for k in (20, 40, 60, 80):
            ax.plot([x0 + k / 2, x0 + 100 - k / 2], [k * H, k * H], **grid)
            ax.plot([x0 + 100 - k, x0 + (100 - k) / 2], [0, (100 - k) * H], **grid)
            ax.plot([x0 + k, x0 + k + (100 - k) / 2], [0, (100 - k) * H], **grid)
            ax.text(x0 + k, -2.5, str(k), ha="center", va="top", **tick)
            ax.text(x0 + 100 - k / 2 + 2.5, k * H, str(k), ha="left", va="center", **tick)
            ax.text(x0 + k / 2 - 2.5, k * H, str(100 - k), ha="right", va="center", **tick)
        ax.plot([x0, x0 + 100, x0 + 50, x0], [0, 0, 100 * H, 0], **edge)

    # --- diamond
    ax.fill([bx, bx - 50, bx, bx + 50], [by, by + 100 * H, by + 200 * H, by + 100 * H],
            color=PANEL, zorder=0)
    if zones:   # the 6 fields
        for (name, desc, col), poly in zip(QUADS, FIELD_POLY):
            xs, ys = zip(*[_diamond_xy(c, d) for c, d in poly])
            ax.fill(xs, ys, color=col, alpha=0.13, zorder=0.5, lw=0)
        # names of the four corner fields sit outside the left / right / top vertices (points would
        # hide them), the bottom one just inside its corner
        lab = {0: (bx, by + 200 * H + 12, "center"),
               1: (bx - 54, by + 100 * H + 4, "right"),
               2: (bx, by + 42 * H, "center"),
               5: (bx + 54, by + 100 * H + 4, "left")}
        for q, (x, y, ha) in lab.items():
            name, desc, col = QUADS[q]
            ax.text(x, y + 3, _chem(name), ha=ha, va="center", fontsize=fs["zone"], weight="bold",
                    color=col, zorder=1.5)
            ax.text(x, y - 3, desc, ha=ha, va="center", fontsize=fs["zone"] - 1, style="italic",
                    color=col, zorder=1.5)
        for i, c in enumerate(FIELD_NUM_AT):
            x, y = _diamond_xy(*c)
            ax.text(x, y, str(i + 1), ha="center", va="center", fontsize=fs["zone"] + 3,
                    color=INK, zorder=6, path_effects=[pe.withStroke(linewidth=2.6, foreground="white",
                                                                      alpha=0.85)])
    for k in (20, 40, 60, 80):
        sx, sy = bx - k / 2, by + k * H            # Ca+Mg = k
        ax.plot([sx, sx + 50], [sy, sy + 100 * H], **grid)
        sx, sy = bx + k / 2, by + k * H            # SO4+Cl = k
        ax.plot([sx, sx - 50], [sy, sy + 100 * H], **grid)
        ax.text(bx - 50 + k / 2 - 2.5, by + 100 * H + k * H + 1, str(k), ha="right", va="center", **tick)
        ax.text(bx + 50 - k / 2 + 2.5, by + 100 * H + k * H + 1, str(k), ha="left", va="center", **tick)
    if zones:   # dotted lines between the fields
        for p, q in (((50, 0), (50, 100)), ((0, 50), (100, 50)), ((100, 50), (50, 100)), ((50, 0), (0, 50))):
            (x1, y1), (x2, y2) = _diamond_xy(*p), _diamond_xy(*q)
            ax.plot([x1, x2], [y1, y2], color=INK, lw=1.0, ls=(0, (1.2, 2.2)), zorder=1.2)
    ax.plot([bx, bx - 50, bx, bx + 50, bx], [by, by + 100 * H, by + 200 * H, by + 100 * H, by], **edge)

    # --- axis titles (Times New Roman through mathtext, so sub/superscripts match)
    ax.text(LX0 + 50, 100 * H + 4, r"Mg$^{2{+}}$", ha="center", **title)
    ax.text(LX0 - 3, -9, r"Ca$^{2{+}}$", ha="center", va="top", **title)
    ax.text(LX0 + 102, -9, r"Na$^{{+}}$ + K$^{{+}}$", ha="right", va="top", **title)
    ax.text(RX0 + 50, 100 * H + 4, r"SO$_{4}^{2{-}}$", ha="center", **title)
    ax.text(RX0 - 2, -9, r"HCO$_{3}^{{-}}$ + CO$_{3}^{2{-}}$", ha="left", va="top", **title)
    ax.text(RX0 + 103, -9, r"Cl$^{{-}}$", ha="center", va="top", **title)
    ax.text(bx - 42, by + 100 * H + 50 * H + 6, r"SO$_{4}^{2{-}}$ + Cl$^{{-}}$  (%)", ha="center",
            va="center", rotation=60, **title)
    ax.text(bx + 42, by + 100 * H + 50 * H + 6, r"Ca$^{2{+}}$ + Mg$^{2{+}}$  (%)", ha="center",
            va="center", rotation=-60, **title)
    ax.text(LX0 + 50, -19, "Cations (% meq/L)", ha="center", va="top", fontsize=fs["note"], color=INK_SOFT)
    ax.text(RX0 + 50, -19, "Anions (% meq/L)", ha="center", va="top", fontsize=fs["note"], color=INK_SOFT)

    ax.set_xlim(-14, 236)
    ax.set_ylim(-26, 212)
    ax.set_aspect("equal")
    ax.axis("off")


# --------------------------------------------------------------------- styling
def _group_styles(groups):
    """group -> (colour, marker, filled).
    Shallow/Deep groups: blue + (shallow) and pink open circle (deep). If the names also contain
    fresh / brackish / saline, colour = salinity, otherwise colour = depth.
    Any other names: colours and symbols are cycled."""
    parsed = {}
    for g in groups:
        gl = g.lower()
        parsed[g] = (next((k for k in DEPTH_MK if k in gl), None),
                     next((c for k, c in SAL_COL.items() if k in gl), None))
    styles = None
    if all(dp for dp, _ in parsed.values()):
        if all(sc is None for _, sc in parsed.values()):
            styles = {g: (DEPTH_COL[dp], DEPTH_MK[dp], False) for g, (dp, _) in parsed.items()}
        elif all(sc is not None for _, sc in parsed.values()):
            styles = {g: (sc, DEPTH_MK[dp], False) for g, (dp, sc) in parsed.items()}
    if styles is None or len(set(styles.values())) < len(groups):
        styles = {g: (COLORS[i % len(COLORS)], CYCLE_MK[i % len(CYCLE_MK)], False)
                  for i, g in enumerate(groups)}
    return styles


def _sizes(tds, base, use_tds):
    """Marker areas. With TDS: log-scaled between 0.35x and 2x of base."""
    if not use_tds or tds.notna().sum() < 2:
        return np.full(len(tds), float(base)), None
    lg = np.log10(tds.clip(lower=1))
    lo, hi = np.nanpercentile(lg, 2), np.nanpercentile(lg, 98)
    f = ((lg - lo) / (hi - lo if hi > lo else 1)).clip(0, 1).fillna(0.5)
    s = base * (0.35 + 1.65 * f)
    ref = [10 ** v for v in (lo, (lo + hi) / 2, hi)]
    return s.values, ref


def piper_plot(data, title="Piper Diagram", annotate=False, size=30, alpha=0.9,
               zones=False, size_by_tds=False, summary=False, styles=None,
               font=FONT_FAMILY, font_scale=1.0, font_sizes=None,
               legend=None, legend_cols=1, legend_box=False, figsize=None, field_list=None,
               field_legend=None):
    """data: DataFrame returned by prepare().
    styles: optional {group: (colour, marker, filled)} that overrides the automatic choice.
    font_scale / font_sizes: change the text sizes (see FS_DEFAULT for the keys).
    legend: None (default place), a preset ("upper right", "upper left", "lower right",
            "lower left", "center right", "center left", "none" = hide) or an (x, y) pair:
            the position of the legend's top-left corner on the whole figure, 0..1
            (x: left -> right, y: bottom -> top).
    legend_cols / legend_box: number of columns, draw a frame around the legend.
    field_list: list the 6 diamond fields in a second legend (default: when zones=True and no summary).
    field_legend: where that list goes (same choices as legend; default: upper left of the plot).
    summary=True adds a side panel with the field share of every group."""
    set_font(font)
    fs = _font_sizes(font_scale, font_sizes)
    groups = list(dict.fromkeys(data["group"]))
    counts = data["group"].value_counts()
    auto = _group_styles(groups)
    auto.update({g: tuple(s) for g, s in (styles or {}).items() if g in auto})
    styles = auto
    sizes, ref = _sizes(data["tds"], size, size_by_tds)
    data = data.assign(_s=sizes)

    if summary:
        fig = plt.figure(figsize=figsize or (16, 9.4), facecolor="white")
        gs = fig.add_gridspec(2, 2, width_ratios=[2.15, 1], height_ratios=[1.0, 1.05],
                              left=0.015, right=0.985, top=0.885, bottom=0.14, wspace=0.04, hspace=0.30)
        ax = fig.add_subplot(gs[:, 0])
        ax_leg = fig.add_subplot(gs[0, 1])
        ax_bar = fig.add_subplot(gs[1, 1])
    else:
        fig, ax = plt.subplots(figsize=figsize or (11.5, 9.2), facecolor="white")
    draw_frame(ax, zones, fs)

    # biggest group first, so small groups stay visible on top
    for g in sorted(groups, key=lambda x: -counts[x]):
        d = data[data["group"] == g]
        col, mk, filled = styles[g]
        kw = dict(s=d["_s"] * SCALE.get(mk, 1.0), marker=mk, alpha=alpha, zorder=5)
        if mk in LINE_ONLY:                     # + x Y : lines only
            kw.update(c=col, linewidths=1.15)
        elif filled:                            # solid symbol with a thin white edge
            kw.update(c=col, edgecolors="white", linewidths=0.5)
        else:                                   # open symbol
            kw.update(facecolors="none", edgecolors=col, linewidths=1.25)
        cx, cy = _tri_xy(d["Ca"], d["NaK"], d["Mg"], LX0)
        ax_, ay = _tri_xy(d["HCO3"], d["Cl"], d["SO4"], RX0)
        dx, dy = _diamond_xy(d["Ca"] + d["Mg"], d["SO4"] + d["Cl"])
        for xs, ys in ((cx, cy), (ax_, ay), (dx, dy)):
            ax.scatter(xs, ys, **kw)
        if annotate:
            for xs, ys in ((cx, cy), (ax_, ay), (dx, dy)):
                for x, y, lab in zip(xs, ys, d["label"]):
                    ax.annotate(lab, (x, y), xytext=(4, 4), textcoords="offset points",
                                fontsize=fs["label"], color=INK, zorder=6)

    # ---- one legend: groups (+ the TDS size key), placed where the user wants it
    single = len(groups) == 1 and groups[0] == "Samples"

    def _handle(g):
        col, mk, filled = styles[g]
        solid = filled and mk not in LINE_ONLY
        return Line2D([], [], marker=mk, linestyle="none", markerfacecolor=col if solid else "none",
                      markeredgecolor=col, markersize=LEGEND_MS.get(mk, 9), markeredgewidth=1.4,
                      label=f"{g}   (n = {counts[g]})")
    handles = [] if single else [_handle(g) for g in groups]
    if ref is not None:
        if handles:
            handles.append(Line2D([], [], linestyle="none", label=" "))
        handles.append(Line2D([], [], linestyle="none", label="Marker size = TDS"))
        handles += [Line2D([], [], marker="o", linestyle="none", markerfacecolor="none",
                           markeredgecolor="#8a8984", markeredgewidth=1.0,
                           markersize=np.sqrt(size * (0.35 + 1.65 * f)), label=f"{v:,.0f} mg/L")
                    for f, v in zip((0, 0.5, 1), ref)]

    if field_list is None:
        field_list = bool(zones and not summary)

    def _legend(hnd, place, title=None, cols=1, box=False):
        """Draw one legend: 'panel' = the summary panel, (x, y) = anywhere on the figure,
        otherwise a corner of the plot."""
        kw = dict(handles=hnd, fontsize=fs["legend"], labelcolor=INK, handletextpad=0.5,
                  labelspacing=0.7, frameon=bool(box), ncol=max(1, int(cols)), borderaxespad=0.5)
        if title:
            kw.update(title=title, title_fontsize=fs["legend"] + 0.5)
        if box:
            kw.update(facecolor="white", edgecolor=GRID, framealpha=0.95)
        if place == "panel":                                   # summary layout: own panel
            leg = ax_leg.legend(loc="upper left", **kw)
        elif isinstance(place, (tuple, list)):                 # any spot on the figure
            leg = fig.legend(loc="upper left", bbox_to_anchor=(float(place[0]), float(place[1])),
                             bbox_transform=fig.transFigure, **kw)
        else:                                                  # preset corner of the plot
            leg = ax.legend(loc=place, **kw)
            ax.add_artist(leg)                                 # keeps it when a second legend is added
        if title:
            leg._legend_box.align = "left"
            leg.get_title().set_weight("bold")
        return leg

    place = legend if legend is not None else ("panel" if summary else "upper right")
    if summary:
        ax_leg.axis("off")
    if handles and place != "none":
        _legend(handles, place, "Water group" if place == "panel" else None, legend_cols, legend_box)
    fplace = field_legend if field_legend is not None else "upper left"
    if field_list and fplace != "none":
        _legend([Patch(facecolor=to_rgba(c, 0.5), edgecolor="none", label=f"{i + 1}   {_chem(n)}")
                 for i, (n, d, c) in enumerate(QUADS)], fplace, "Diamond fields", 1, legend_box)

    if summary:
        # diamond-field composition per group
        pct = pd.crosstab(data["group"], data["quad"]).reindex(index=groups, columns=range(6), fill_value=0)
        pct = pct.div(pct.sum(axis=1), axis=0) * 100
        ypos = np.arange(len(groups))[::-1]
        left = np.zeros(len(groups))
        for q, (name, desc, col) in enumerate(QUADS):
            w = pct[q].values
            ax_bar.barh(ypos, w, left=left, height=0.64, color=col, edgecolor="white", linewidth=1.6)
            for y, l, v in zip(ypos, left, w):
                if v >= 9:
                    ax_bar.text(l + v / 2, y, f"{v:.0f}%", ha="center", va="center",
                                fontsize=fs["tick"], color="white", weight="bold")
            left += w
        ax_bar.set_yticks(ypos)
        ax_bar.set_yticklabels(groups, fontsize=fs["legend"] - 1.5, color=INK)
        ax_bar.set_xlim(0, 100)
        ax_bar.set_xticks([0, 25, 50, 75, 100])
        ax_bar.set_xticklabels(["0", "25", "50", "75", "100 %"], fontsize=fs["tick"], color=INK_SOFT)
        ax_bar.tick_params(length=0)
        for sp in ax_bar.spines.values():
            sp.set_visible(False)
        ax_bar.set_title("Diamond field of each group (% of samples)", loc="left", fontsize=fs["legend"],
                         weight="bold", color=INK, pad=8)
        ax_bar.legend(handles=[Patch(color=c, label=f"{i + 1}  {_chem(n)}  –  {d}")
                               for i, (n, d, c) in enumerate(QUADS)],
                      loc="upper left", bbox_to_anchor=(-0.02, -0.13), frameon=False, ncol=2,
                      fontsize=fs["tick"], labelcolor=INK, handlelength=1.2, columnspacing=1.2)
        share = np.bincount(data["quad"], minlength=6) / len(data) * 100
        order = np.argsort(-share)
        txt = f"{len(data):,} samples   ·   " + "   ·   ".join(
            f"{i + 1} {_chem(QUADS[i][0])} {share[i]:.0f}%" for i in order if share[i] >= 0.5)
        fig.text(0.015, 0.975, title, fontsize=fs["title"] + 3, weight="bold", color=INK, va="top")
        fig.text(0.015, 0.925, txt, fontsize=fs["legend"], color=INK_SOFT, va="top")
    else:
        ax.set_title(title, fontsize=fs["title"], weight="bold", loc="left", color=INK, pad=8)
        fig.tight_layout()
    return fig


LEGEND_PRESETS = {"Default": None, "Top right": "upper right", "Top left": "upper left",
                  "Bottom right": "lower right", "Bottom left": "lower left",
                  "Middle right": "center right", "Middle left": "center left",
                  "Custom (X, Y)": "custom", "Hidden": "none"}


def example_workbook():
    """A small Excel file (bytes) that shows the expected columns."""
    rows = [
        ["S1", "Shallow", 82, 24, 38, 3, 290, 40, 55, 640],
        ["S2", "Shallow", 64, 18, 95, 5, 310, 110, 60, 980],
        ["S3", "Shallow", 40, 22, 260, 9, 330, 330, 90, 1900],
        ["S4", "Shallow", 120, 45, 520, 14, 280, 760, 210, 3300],
        ["D1", "Deep", 30, 10, 150, 6, 360, 80, 45, 950],
        ["D2", "Deep", 18, 6, 310, 8, 420, 230, 70, 1500],
        ["D3", "Deep", 35, 14, 640, 12, 300, 900, 180, 3600],
        ["D4", "Deep", 22, 9, 1100, 20, 250, 1700, 320, 5200],
    ]
    cols = ["Sample", "Group", "Ca", "Mg", "Na", "K", "HCO3", "Cl", "SO4", "TDS"]
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=cols).to_excel(buf, index=False)
    return buf.getvalue()


def read_table(file, sheet_name=0):
    name = getattr(file, "name", str(file)).lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    return pd.read_excel(file, sheet_name=sheet_name)


# ----------------------------------------------------------------- Streamlit UI
def run_streamlit():
    import streamlit as st

    st.set_page_config(page_title="Piper Diagram", layout="wide")
    st.title("Piper Diagram Plotter")
    st.write("Upload an Excel/CSV file with columns: **Ca, Mg, Na, K, HCO3, (CO3), Cl, SO4** "
             "and optionally **Sample**, **Group** and **TDS** (all in mg/L or meq/L). "
             "Your file is only used to draw the plot; this app does not store it.")
    st.download_button("Download an example Excel file", example_workbook(), "piper_example.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.sidebar:
        units = st.radio("Concentration units", ["mg/L", "meq/L"])
        title = st.text_input("Title", "Piper Diagram")
        zones = st.checkbox("Show the 6 fields in the diamond", value=False)
        flist = st.checkbox("List the 6 fields (second legend)", value=True)
        summary = st.checkbox("Add field summary panel (bars per group)", value=False)
        annotate = st.checkbox("Label samples", value=False)
        size = st.slider("Marker size", 10, 120, 30)
        alpha = st.slider("Marker opacity", 0.3, 1.0, 0.9)
        size_tds = st.checkbox("Marker size by TDS (if a TDS column exists)", value=False)
        with st.expander("Text (font and sizes)"):
            font = st.text_input("Font", FONT_FAMILY)
            scale = st.slider("All text, scale", 0.6, 2.0, 1.0, 0.05)
            sizes = {k: st.slider(f"{FS_NAMES[k]} (pt)", 4.0, 40.0, float(FS_DEFAULT[k]), 0.5)
                     for k in FS_DEFAULT}
        with st.expander("Legend position"):
            where = st.selectbox("Place the legend", list(LEGEND_PRESETS))
            lx = ly = None
            if LEGEND_PRESETS[where] == "custom":
                lx = st.slider("X  (left to right)", 0.0, 1.0, 0.72, 0.01)
                ly = st.slider("Y  (bottom to top)", 0.0, 1.0, 0.93, 0.01)
                st.caption("X and Y give the legend's top-left corner on the whole figure.")
            lcols = st.slider("Columns", 1, 4, 1)
            lbox = st.checkbox("Draw a box around the legend", value=False)
            st.markdown("**Field list** (the 6 diamond fields)")
            fwhere = st.selectbox("Place the field list", list(LEGEND_PRESETS), key="fwhere",
                                  format_func=lambda k: "Default (top left)" if k == "Default" else k)
            fx = fy = None
            if LEGEND_PRESETS[fwhere] == "custom":
                fx = st.slider("X  (left to right) ", 0.0, 1.0, 0.02, 0.01, key="fx")
                fy = st.slider("Y  (bottom to top) ", 0.0, 1.0, 0.95, 0.01, key="fy")

    up = st.file_uploader("Upload data", type=["xlsx", "xls", "csv"])
    if up is None:
        st.info("Waiting for a file...")
        return

    sheet = 0
    if not up.name.lower().endswith(".csv"):
        sheets = pd.ExcelFile(up).sheet_names
        sheet = st.selectbox("Sheet", sheets)
        up.seek(0)
    try:
        df = read_table(up, sheet)
        data = prepare(df, "mgl" if units == "mg/L" else "meql")
    except Exception as e:
        st.error(str(e))
        return

    # symbol + colour for every class
    groups = list(dict.fromkeys(data["group"]))
    auto = _group_styles(groups)
    codes = list(SYMBOLS)
    custom = {}
    with st.sidebar.expander("Symbol and colour of each class", expanded=True):
        for g in groups:
            col0, mk0, filled0 = auto[g]
            c1, c2 = st.columns([3, 1])
            code = c1.selectbox(g, codes, index=codes.index(symbol_code(mk0, filled0)),
                                format_func=lambda c: SYMBOLS[c][0], key=f"sym_{g}")
            colour = c2.color_picker(f"Colour of {g}", col0, key=f"col_{g}", label_visibility="collapsed")
            custom[g] = (colour, SYMBOLS[code][1], SYMBOLS[code][2])

    fig = piper_plot(data, title=title, annotate=annotate, size=size, alpha=alpha,
                     zones=zones, size_by_tds=size_tds, summary=summary, styles=custom,
                     font=font, font_scale=scale, font_sizes=sizes,
                     legend=(lx, ly) if LEGEND_PRESETS[where] == "custom" else LEGEND_PRESETS[where],
                     legend_cols=lcols, legend_box=lbox, field_list=flist,
                     field_legend=(fx, fy) if LEGEND_PRESETS[fwhere] == "custom" else LEGEND_PRESETS[fwhere])
    st.pyplot(fig)

    c1, c2 = st.columns(2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    c1.download_button("Download PNG", buf.getvalue(), "piper.png", "image/png")
    res = data[["label", "group", "Ca", "Mg", "NaK", "HCO3", "SO4", "Cl", "field", "water_type", "facies"]].round(2)
    c2.download_button("Download classification (CSV)", res.to_csv(index=False).encode(),
                       "piper_classification.csv", "text/csv")
    with st.expander("Summary by group (mean % meq/L)", expanded=True):
        st.dataframe(summary_table(data))
    with st.expander("How many samples of each group fall in each of the 6 fields", expanded=True):
        st.dataframe(field_table(data))
    with st.expander("Which samples belong to which field", expanded=True):
        names = [f"{i + 1}. {n}" for i, (n, d, c) in enumerate(QUADS)]
        pick = st.multiselect("Show only these fields", names, default=names)
        keep = [int(p.split(".")[0]) for p in pick]
        st.dataframe(res[res["field"].isin(keep)].rename(columns={"water_type": "field name"}))
        st.caption(f"{int(res['field'].isin(keep).sum())} of {len(res)} samples shown.")


# ------------------------------------------------------------------------- CLI
def run_cli():
    import argparse
    p = argparse.ArgumentParser(description="Piper diagram from an Excel/CSV file")
    p.add_argument("file", nargs="?")
    p.add_argument("--units", choices=["mgl", "meql"], default="mgl")
    p.add_argument("--sheet", default=0)
    p.add_argument("--out", default="piper.png")
    p.add_argument("--title", default="Piper Diagram")
    p.add_argument("--annotate", action="store_true")
    p.add_argument("--zones", action="store_true", help="shade and number the 6 diamond fields")
    p.add_argument("--summary", action="store_true", help="add a panel with the field share of every group")
    p.add_argument("--size-by-tds", action="store_true")
    p.add_argument("--style", action="append", default=[], metavar="GROUP=SYMBOL:COLOUR",
                   help='symbol + colour of one class, e.g. --style "Deep=circle:#e8508a" (repeatable)')
    p.add_argument("--font", default=FONT_FAMILY)
    p.add_argument("--font-scale", type=float, default=1.0, help="multiply all text sizes")
    p.add_argument("--sizes", default="", metavar="title=18,axis=12",
                   help="text sizes in pt; keys: " + ", ".join(FS_DEFAULT))
    p.add_argument("--legend", default=None, metavar="PLACE",
                   help='upper right | upper left | lower right | lower left | center right | '
                        'center left | none | "x,y" (top-left corner on the figure, 0..1)')
    p.add_argument("--legend-cols", type=int, default=1)
    p.add_argument("--legend-box", action="store_true")
    p.add_argument("--no-field-list", action="store_true", help="do not list the 6 fields (second legend)")
    p.add_argument("--field-legend", default=None, metavar="PLACE",
                   help="where the field list goes: same choices as --legend (default: upper left)")
    p.add_argument("--classify-csv", metavar="FILE", help="save the field of every sample to a CSV file")
    p.add_argument("--list-symbols", action="store_true")
    a = p.parse_args()
    if a.list_symbols or not a.file:
        print("Symbols:", ", ".join(SYMBOLS))
        return
    styles = dict(parse_style(s) for s in a.style)
    sizes = {}
    for part in filter(None, a.sizes.split(",")):
        k, v = part.split("=")
        if k.strip() not in FS_DEFAULT:
            raise SystemExit(f"Unknown size key {k!r}. Use: {', '.join(FS_DEFAULT)}")
        sizes[k.strip()] = float(v)
    legend = a.legend
    if legend and "," in legend:
        legend = tuple(float(v) for v in legend.split(","))
    flegend = a.field_legend
    if flegend and "," in flegend:
        flegend = tuple(float(v) for v in flegend.split(","))
    df = read_table(a.file, a.sheet)
    data = prepare(df, a.units)
    fig = piper_plot(data, title=a.title, annotate=a.annotate, zones=a.zones,
                     size_by_tds=a.size_by_tds, summary=a.summary, styles=styles,
                     font=a.font, font_scale=a.font_scale, font_sizes=sizes,
                     legend=legend, legend_cols=a.legend_cols, legend_box=a.legend_box,
                     field_list=False if a.no_field_list else None, field_legend=flegend)
    fig.savefig(a.out, dpi=300, facecolor="white", bbox_inches="tight")
    print("Saved", a.out)
    print(summary_table(data).to_string())
    print(field_table(data).to_string())
    if a.classify_csv:
        data[["label", "group", "Ca", "Mg", "NaK", "HCO3", "SO4", "Cl", "field", "water_type", "facies"]] \
            .round(2).to_csv(a.classify_csv, index=False)
        print("Saved", a.classify_csv)


if __name__ == "__main__":
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        try:
            in_streamlit = get_script_run_ctx(suppress_warning=True) is not None
        except TypeError:                      # older Streamlit versions
            in_streamlit = get_script_run_ctx() is not None
    except Exception:
        in_streamlit = False

    if in_streamlit:
        run_streamlit()
    elif len(sys.argv) > 1:
        matplotlib.use("Agg")
        run_cli()
    else:
        print("Run with:  streamlit run piper_app.py   (or)   python piper_app.py data.xlsx")
