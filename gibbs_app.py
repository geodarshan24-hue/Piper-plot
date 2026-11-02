"""
Gibbs diagram plotter: upload an Excel/CSV file and plot the samples.

Companion of piper_app.py (keep both files in the same folder; this one imports from it).

Run as a web app (upload button):
    pip install streamlit pandas matplotlib openpyxl
    streamlit run gibbs_app.py

Or from the command line:
    python gibbs_app.py my_data.xlsx --units mgl --out gibbs.png

Two panels are drawn:
    (a)  Na / (Na + Ca)       against TDS   (cations)
    (b)  Cl / (Cl + HCO3)     against TDS   (anions)
Ratios are calculated in meq/L. TDS is in mg/L (log scale).

Expected columns (names are matched flexibly, case-insensitive):
    Ca, Na, Cl, HCO3 (CO3 optional, it is added to HCO3), and TDS
Optional columns:
    Sample / ID / Name   -> label for each sample
    Group / Type / Class -> every class gets its own symbol and colour
If there is no TDS column, tick "Calculate TDS" (sum of all ions, needs Mg, K, SO4 too).

Same text, symbol, colour and legend controls as the Piper app.
"""
import io
import sys

import numpy as np
import pandas as pd
import matplotlib

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.path import Path
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

from piper_app import (ALIASES, EQ_WT, FONT_FAMILY, FS_DEFAULT, FS_NAMES, GRID, INK, INK_SOFT,
                       LEGEND_MS, LINE_ONLY, SCALE, SYMBOLS, TDS_ALIASES, _find,
                       _group_styles, parse_style, read_table, set_font, symbol_code)

# ----------------------------------------------------------------- Gibbs regions
LOG_X = (1.0, 5.0)                      # TDS 10 ... 100 000 mg/L
REGIONS = ["Precipitation dominance", "Rock dominance", "Evaporation dominance"]
REG_COL = {"Precipitation dominance": "#4f86a3", "Rock dominance": "#3f9a6b",
           "Evaporation dominance": "#c58a12"}
FS_GIBBS = {**FS_DEFAULT, "title": 15, "axis": 12, "tick": 10, "legend": 11, "zone": 10, "label": 7}


def dome(n=200):
    """Boundary of the rock-dominance field, a schematic dome after Gibbs (1970).
    Returns arrays (log10 TDS, ratio); the base of the dome lies on ratio = 0."""
    t = np.linspace(0, 1, n)
    x0, x1 = 1.8, 4.7                                   # TDS about 63 ... 50 000 mg/L
    x = x0 + (x1 - x0) * t
    y = 0.92 * np.sin(np.pi * t ** 0.6) ** 0.75
    return x, y


_DX, _DY = dome()
_DOME_PATH = Path(np.column_stack([np.r_[_DX, _DX[0]], np.r_[_DY, _DY[0]]]))
_APEX_X = _DX[np.argmax(_DY)]


def region_of(tds, ratio):
    """Gibbs field of every sample: inside the dome = rock; outside it, left of the
    apex = precipitation, right of the apex = evaporation."""
    pts = np.column_stack([np.log10(np.clip(tds, 1e-9, None)), ratio])
    inside = _DOME_PATH.contains_points(pts, radius=1e-9)
    return np.where(inside, REGIONS[1], np.where(pts[:, 0] < _APEX_X, REGIONS[0], REGIONS[2]))


# ------------------------------------------------------------------- data prep
def prepare_gibbs(df, units="mgl", calc_tds=False):
    cols = {ion: _find(df, names) for ion, names in ALIASES.items()}
    need = ["Ca", "Na", "Cl", "HCO3"] + (["Mg", "K", "SO4"] if calc_tds else [])
    missing = [i for i in need if cols[i] is None]
    if missing:
        raise ValueError(f"Could not find column(s) for: {', '.join(missing)}. "
                         f"Columns found: {list(df.columns)}")
    ion = pd.DataFrame(index=df.index)
    for k in EQ_WT:
        ion[k] = pd.to_numeric(df[cols[k]], errors="coerce").fillna(0) if cols[k] else 0.0
    meq = ion / pd.Series(EQ_WT) if units == "mgl" else ion
    mgl = ion if units == "mgl" else ion * pd.Series(EQ_WT)

    tc = _find(df, TDS_ALIASES)
    if calc_tds:
        tds = mgl.sum(axis=1)
    elif tc is not None:
        tds = pd.to_numeric(df[tc], errors="coerce")
    else:
        raise ValueError('No TDS column found. Add a column called "TDS" (mg/L), '
                         'or tick "Calculate TDS" to use the sum of the ions.')

    out = pd.DataFrame(index=df.index)
    out["tds"] = tds
    with np.errstate(divide="ignore", invalid="ignore"):
        out["cat_ratio"] = meq["Na"] / (meq["Na"] + meq["Ca"])
        out["an_ratio"] = meq["Cl"] / (meq["Cl"] + meq["HCO3"] + meq["CO3"])
    lc = _find(df, ["sample", "sampleid", "id", "name", "station", "well", "label"])
    gc = _find(df, ["group", "type", "class", "category", "facies", "zone"])
    out["label"] = df[lc].astype(str) if lc else [str(i + 1) for i in range(len(df))]
    out["group"] = df[gc].astype(str).str.strip() if gc else "Samples"
    out = out[out["tds"] > 0].replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=["tds"], how="any")
    out["cat_region"] = np.where(out["cat_ratio"].notna(),
                                 region_of(out["tds"].values, out["cat_ratio"].fillna(0).values), "")
    out["an_region"] = np.where(out["an_ratio"].notna(),
                                region_of(out["tds"].values, out["an_ratio"].fillna(0).values), "")
    if out[["cat_ratio", "an_ratio"]].isna().all(axis=None):
        raise ValueError("No sample could be plotted (check units, TDS and the Ca/Na/Cl/HCO3 columns).")
    return out


def summary_gibbs(data):
    """Number of samples of every group in each Gibbs field (cations and anions)."""
    rows = []
    for g, d in data.groupby("group", sort=False):
        row = {"Group": g, "n": len(d)}
        for tag, col in (("cations", "cat_region"), ("anions", "an_region")):
            vc = d[col][d[col] != ""].value_counts()
            tot = max(int(vc.sum()), 1)
            for r in REGIONS:
                row[f"{r.split()[0]} ({tag}) %"] = round(100 * vc.get(r, 0) / tot, 1)
        rows.append(row)
    return pd.DataFrame(rows).set_index("Group")


# --------------------------------------------------------------------- drawing
def _panel(ax, ycol, ylabel, letter, fs, boundaries, names, shade, show_ylabel=True):
    if shade:
        xs = np.logspace(LOG_X[0], LOG_X[1], 300)
        lx = np.log10(xs)
        ax.fill_between(xs, 0, 1, where=lx < _APEX_X, color=REG_COL[REGIONS[0]], alpha=0.10, lw=0)
        ax.fill_between(xs, 0, 1, where=lx >= _APEX_X, color=REG_COL[REGIONS[2]], alpha=0.10, lw=0)
        ax.fill(10 ** _DX, _DY, color="white", lw=0, zorder=1)
        ax.fill(10 ** _DX, _DY, color=REG_COL[REGIONS[1]], alpha=0.14, lw=0, zorder=1)
    if boundaries:
        ax.plot(10 ** _DX, _DY, color=INK_SOFT, lw=1.2, zorder=2)
    ax.set_xscale("log")
    ax.set_xlim(10 ** LOG_X[0], 10 ** LOG_X[1])
    ax.set_ylim(0, 1)
    ax.xaxis.set_major_locator(FixedLocator([10 ** k for k in range(1, 6)]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.tick_params(labelsize=fs["tick"], colors=INK, length=4)
    ax.grid(True, which="major", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_color(INK_SOFT)
    ax.set_xlabel("TDS (mg/L)", fontsize=fs["axis"], color=INK)
    ax.set_ylabel(ylabel, fontsize=fs["axis"], color=INK)
    ax.text(0.02, 0.975, f"({letter})", transform=ax.transAxes, ha="left", va="top",
            fontsize=fs["axis"] + 1, weight="bold", color=INK)
    if names:
        kw = dict(fontsize=fs["zone"], style="italic", ha="center", zorder=3)
        ax.text(10 ** 1.45, 0.62, "Precipitation\ndominance", color=REG_COL[REGIONS[0]], va="center", **kw)
        ax.text(10 ** 3.35, 0.09, "Rock dominance", color=REG_COL[REGIONS[1]], va="center",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.8), **kw)
        ax.text(10 ** 4.55, 0.62, "Evaporation\ndominance", color=REG_COL[REGIONS[2]], va="center", **kw)


LEGEND_PRESETS = {"Below the plot (default)": None, "Right of the plot": "right",
                  "Top right (inside)": "upper right", "Top left (inside)": "upper left",
                  "Bottom right (inside)": "lower right", "Bottom left (inside)": "lower left",
                  "Custom (X, Y)": "custom", "Hidden": "none"}


def gibbs_plot(data, title="", annotate=False, size=30, alpha=0.9, panels="both",
               boundaries=True, names=True, shade=False, styles=None,
               font=FONT_FAMILY, font_scale=1.0, font_sizes=None,
               legend=None, legend_cols=0, legend_box=False, figsize=None):
    """data: DataFrame from prepare_gibbs().
    panels: "both" (side by side), "stacked", "cations" or "anions".
    styles: {group: (colour, marker, filled)} overriding the automatic choice.
    legend: None (below the plot), "right", a corner ("upper right", ...), "none", or an (x, y)
            pair = top-left corner of the legend on the whole figure, 0..1.
    legend_cols: columns of the legend (0 = automatic)."""
    set_font(font)
    fs = {k: v * font_scale for k, v in {**FS_GIBBS, **(font_sizes or {})}.items()}
    groups = list(dict.fromkeys(data["group"]))
    counts = data["group"].value_counts()
    auto = _group_styles(groups)
    auto.update({g: tuple(s) for g, s in (styles or {}).items() if g in auto})
    styles = auto

    specs = {"both": (1, 2, (12.5, 5.8)), "stacked": (2, 1, (7.2, 10.6)),
             "cations": (1, 1, (6.6, 5.8)), "anions": (1, 1, (6.6, 5.8))}[panels]
    fig, axes = plt.subplots(specs[0], specs[1], figsize=figsize or specs[2], facecolor="white",
                             squeeze=False, constrained_layout=True)
    axes = axes.ravel()
    todo = [("cat_ratio", r"Na$^{{+}}$ / (Na$^{{+}}$ + Ca$^{2{+}}$)"),
            ("an_ratio", r"Cl$^{{-}}$ / (Cl$^{{-}}$ + HCO$_{3}^{{-}}$)")]
    if panels == "cations":
        todo = todo[:1]
    elif panels == "anions":
        todo = todo[1:]
    for i, (ax, (ycol, ylabel)) in enumerate(zip(axes, todo)):
        letter = "a" if panels in ("both", "stacked", "cations") and i == 0 else "b"
        _panel(ax, ycol, ylabel, letter, fs, boundaries, names, shade)
        for g in sorted(groups, key=lambda x: -counts[x]):       # big groups first
            d = data[(data["group"] == g) & data[ycol].notna()]
            col, mk, filled = styles[g]
            kw = dict(s=size * SCALE.get(mk, 1.0) * 1.8, marker=mk, alpha=alpha, zorder=5)
            if mk in LINE_ONLY:
                kw.update(c=col, linewidths=1.15)
            elif filled:
                kw.update(c=col, edgecolors="white", linewidths=0.5)
            else:
                kw.update(facecolors="none", edgecolors=col, linewidths=1.25)
            ax.scatter(d["tds"], d[ycol], **kw)
            if annotate:
                for x, y, lab in zip(d["tds"], d[ycol], d["label"]):
                    ax.annotate(lab, (x, y), xytext=(4, 4), textcoords="offset points",
                                fontsize=fs["label"], color=INK, zorder=6)
    if title:
        fig.suptitle(title, fontsize=fs["title"], weight="bold", color=INK)

    # ---- one legend for the whole figure
    single = len(groups) == 1 and groups[0] == "Samples"
    handles = []
    if not single:
        for g in groups:
            col, mk, filled = styles[g]
            solid = filled and mk not in LINE_ONLY
            handles.append(Line2D([], [], marker=mk, linestyle="none",
                                  markerfacecolor=col if solid else "none", markeredgecolor=col,
                                  markersize=LEGEND_MS.get(mk, 9), markeredgewidth=1.4,
                                  label=f"{g}   (n = {counts[g]})"))
    place = legend if legend is not None else "below"
    if handles and place != "none":
        nc = int(legend_cols) if legend_cols else (min(len(handles), 4) if place == "below" else 1)
        kw = dict(handles=handles, fontsize=fs["legend"], labelcolor=INK, handletextpad=0.5,
                  labelspacing=0.7, frameon=bool(legend_box), ncol=max(1, nc), borderaxespad=0.5)
        if legend_box:
            kw.update(facecolor="white", edgecolor=GRID, framealpha=0.95)
        if place == "below":
            fig.legend(loc="upper center", bbox_to_anchor=(0.5, -0.01), bbox_transform=fig.transFigure, **kw)
        elif place == "right":
            fig.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), bbox_transform=fig.transFigure, **kw)
        elif isinstance(place, (tuple, list)):
            fig.legend(loc="upper left", bbox_to_anchor=(float(place[0]), float(place[1])),
                       bbox_transform=fig.transFigure, **kw)
        else:
            axes[len(todo) - 1].legend(loc=place, **kw)
    return fig


def example_workbook():
    """A small Excel file (bytes) that shows the expected columns."""
    rows = [
        ["S1", "Shallow", 82, 24, 38, 3, 290, 40, 55, 640],
        ["S2", "Shallow", 64, 18, 95, 5, 310, 110, 60, 980],
        ["S3", "Shallow", 40, 22, 260, 9, 330, 330, 90, 1900],
        ["S4", "Shallow", 120, 45, 520, 14, 280, 760, 210, 3300],
        ["S5", "Shallow", 12, 4, 14, 2, 70, 12, 8, 150],
        ["D1", "Deep", 30, 10, 150, 6, 360, 80, 45, 950],
        ["D2", "Deep", 18, 6, 310, 8, 420, 230, 70, 1500],
        ["D3", "Deep", 35, 14, 640, 12, 300, 900, 180, 3600],
        ["D4", "Deep", 22, 9, 1100, 20, 250, 1700, 320, 5200],
        ["D5", "Deep", 60, 25, 4800, 90, 200, 7600, 900, 17000],
    ]
    cols = ["Sample", "Group", "Ca", "Mg", "Na", "K", "HCO3", "Cl", "SO4", "TDS"]
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=cols).to_excel(buf, index=False)
    return buf.getvalue()


# ----------------------------------------------------------------- Streamlit UI
def run_streamlit():
    import streamlit as st

    st.set_page_config(page_title="Gibbs Diagram", layout="wide")
    st.title("Gibbs Diagram Plotter")
    st.write("Upload an Excel/CSV file with columns: **Ca, Na, Cl, HCO3** (and **CO3** if you have it) and "
             "**TDS** (mg/L). Optional: **Sample** and **Group**. Ratios use meq/L. "
             "Your file is only used to draw the plot; this app does not store it.")
    st.download_button("Download an example Excel file", example_workbook(), "gibbs_example.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.sidebar:
        units = st.radio("Concentration units of the ions", ["mg/L", "meq/L"])
        calc = st.checkbox("Calculate TDS from the ions (no TDS column)", value=False)
        title = st.text_input("Title", "")
        panels = st.selectbox("Panels", ["both", "stacked", "cations", "anions"],
                              format_func=lambda p: {"both": "Cations + anions, side by side",
                                                     "stacked": "Cations + anions, one above the other",
                                                     "cations": "Cations only  Na/(Na+Ca)",
                                                     "anions": "Anions only  Cl/(Cl+HCO3)"}[p])
        boundaries = st.checkbox("Draw the dominance boundaries", value=True)
        names = st.checkbox("Write the field names", value=True)
        shade = st.checkbox("Shade the three fields", value=False)
        annotate = st.checkbox("Label samples", value=False)
        size = st.slider("Marker size", 10, 120, 30)
        alpha = st.slider("Marker opacity", 0.3, 1.0, 0.9)
        with st.expander("Text (font and sizes)"):
            font = st.text_input("Font", FONT_FAMILY)
            scale = st.slider("All text, scale", 0.6, 2.0, 1.0, 0.05)
            sizes = {k: st.slider(f"{FS_NAMES[k]} (pt)", 4.0, 40.0, float(FS_GIBBS[k]), 0.5)
                     for k in FS_GIBBS}
        with st.expander("Legend position"):
            where = st.selectbox("Place the legend", list(LEGEND_PRESETS))
            lx = ly = None
            if LEGEND_PRESETS[where] == "custom":
                lx = st.slider("X  (left to right)", 0.0, 1.0, 0.75, 0.01)
                ly = st.slider("Y  (bottom to top)", 0.0, 1.0, 0.90, 0.01)
                st.caption("X and Y give the legend's top-left corner on the whole figure.")
            lcols = st.slider("Columns (0 = automatic)", 0, 6, 0)
            lbox = st.checkbox("Draw a box around the legend", value=False)

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
        data = prepare_gibbs(df, "mgl" if units == "mg/L" else "meql", calc)
    except Exception as e:
        st.error(str(e))
        return

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

    fig = gibbs_plot(data, title=title, annotate=annotate, size=size, alpha=alpha, panels=panels,
                     boundaries=boundaries, names=names, shade=shade, styles=custom,
                     font=font, font_scale=scale, font_sizes=sizes,
                     legend=(lx, ly) if LEGEND_PRESETS[where] == "custom" else LEGEND_PRESETS[where],
                     legend_cols=lcols, legend_box=lbox)
    st.pyplot(fig)

    c1, c2 = st.columns(2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    c1.download_button("Download PNG", buf.getvalue(), "gibbs.png", "image/png")
    res = data.rename(columns={"tds": "TDS", "cat_ratio": "Na/(Na+Ca)", "an_ratio": "Cl/(Cl+HCO3)",
                               "cat_region": "cation field", "an_region": "anion field"}).round(3)
    c2.download_button("Download ratios and fields (CSV)", res.to_csv(index=False).encode(),
                       "gibbs_ratios.csv", "text/csv")
    with st.expander("Share of samples in each Gibbs field (% of the group)", expanded=True):
        st.dataframe(summary_gibbs(data))
    with st.expander("Every sample"):
        st.dataframe(res)
    st.caption("The dominance boundaries are the usual schematic outline of Gibbs (1970), drawn for "
               "guidance. Samples close to a boundary can belong to either field.")


# ------------------------------------------------------------------------- CLI
def run_cli():
    import argparse
    p = argparse.ArgumentParser(description="Gibbs diagram from an Excel/CSV file")
    p.add_argument("file", nargs="?")
    p.add_argument("--units", choices=["mgl", "meql"], default="mgl")
    p.add_argument("--calc-tds", action="store_true", help="TDS = sum of the ions (mg/L)")
    p.add_argument("--sheet", default=0)
    p.add_argument("--out", default="gibbs.png")
    p.add_argument("--title", default="")
    p.add_argument("--panels", choices=["both", "stacked", "cations", "anions"], default="both")
    p.add_argument("--annotate", action="store_true")
    p.add_argument("--no-boundaries", action="store_true")
    p.add_argument("--no-names", action="store_true")
    p.add_argument("--shade", action="store_true")
    p.add_argument("--style", action="append", default=[], metavar="GROUP=SYMBOL:COLOUR")
    p.add_argument("--font", default=FONT_FAMILY)
    p.add_argument("--font-scale", type=float, default=1.0)
    p.add_argument("--sizes", default="", metavar="title=18,axis=12",
                   help="text sizes in pt; keys: " + ", ".join(FS_GIBBS))
    p.add_argument("--legend", default=None, metavar="PLACE",
                   help='right | upper right | upper left | lower right | lower left | none | '
                        '"x,y" (top-left corner on the figure, 0..1); default: below the plot')
    p.add_argument("--legend-cols", type=int, default=0)
    p.add_argument("--legend-box", action="store_true")
    p.add_argument("--list-symbols", action="store_true")
    a = p.parse_args()
    if a.list_symbols or not a.file:
        print("Symbols:", ", ".join(SYMBOLS))
        return
    styles = dict(parse_style(s) for s in a.style)
    sizes = {}
    for part in filter(None, a.sizes.split(",")):
        k, v = part.split("=")
        if k.strip() not in FS_GIBBS:
            raise SystemExit(f"Unknown size key {k!r}. Use: {', '.join(FS_GIBBS)}")
        sizes[k.strip()] = float(v)
    legend = a.legend
    if legend and "," in legend:
        legend = tuple(float(v) for v in legend.split(","))
    data = prepare_gibbs(read_table(a.file, a.sheet), a.units, a.calc_tds)
    fig = gibbs_plot(data, title=a.title, annotate=a.annotate, panels=a.panels,
                     boundaries=not a.no_boundaries, names=not a.no_names, shade=a.shade,
                     styles=styles, font=a.font, font_scale=a.font_scale, font_sizes=sizes,
                     legend=legend, legend_cols=a.legend_cols, legend_box=a.legend_box)
    fig.savefig(a.out, dpi=300, facecolor="white", bbox_inches="tight")
    print("Saved", a.out)
    print(summary_gibbs(data).to_string())


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
        print("Run with:  streamlit run gibbs_app.py   (or)   python gibbs_app.py data.xlsx")
