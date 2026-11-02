"""
Sample map: put the samples on a map (latitude / longitude) and colour them by the Piper-diamond
field (1-6) or by group.

Companion of piper_app.py (keep both files in the same folder; this one imports from it).

Run as a web app (upload button):
    pip install streamlit pandas matplotlib openpyxl
    streamlit run map_app.py

Or from the command line (a static map as a PNG):
    python map_app.py my_data.xlsx --units mgl --out map.png --color-by field

Expected columns (names are matched flexibly, case-insensitive):
    Ca, Mg, Na, K, HCO3, CO3 (optional), Cl, SO4        (to find the Piper field of every sample)
    Latitude, Longitude                                  (decimal degrees, WGS84)
Optional: Sample, Group (as in the Piper app).

Two maps are made:
    * an interactive map with a street background (zoom, pan, hover to read a sample)
    * a static map for a report (Times New Roman, scale bar, north arrow, symbols per group)
"""
import io
import json
import re
import sys

import numpy as np
import pandas as pd
import matplotlib

import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

from piper_app import (FONT_FAMILY, FS_NAMES, GRID, INK, INK_SOFT, LEGEND_MS, LEGEND_PRESETS,
                       LINE_ONLY, QUADS, SCALE, SYMBOLS, _group_styles, _norm, field_table,
                       parse_style, prepare, read_table, set_font, symbol_code)

FS_MAP = {"title": 15, "axis": 12, "tick": 10, "legend": 11, "label": 8}
LAT_NAMES = ["lat", "latitude", "latdd", "latdeg", "latitud"]
LON_NAMES = ["lon", "long", "lng", "longitude", "londd", "londeg", "longitud"]


# ------------------------------------------------------------------- data prep
def _find_coord(df, names, prefixes):
    lookup = {_norm(c): c for c in df.columns}
    for n in names:
        if n in lookup:
            return lookup[n]
    for k, c in lookup.items():                       # e.g. "Latitude (N)" -> "latituden"
        if k.startswith(prefixes):
            return c
    return None


def prepare_map(df, units="mgl"):
    """Piper classification + coordinates. Returns (data, notes)."""
    latc = _find_coord(df, LAT_NAMES, ("lat",))
    lonc = _find_coord(df, LON_NAMES, ("lon", "lng"))
    if latc is None or lonc is None:
        raise ValueError("Could not find the coordinate columns. Add two columns named "
                         '"Latitude" and "Longitude" (decimal degrees). '
                         f"Columns found: {list(df.columns)}")
    data = prepare(df, units)
    data["lat"] = pd.to_numeric(df.loc[data.index, latc], errors="coerce")
    data["lon"] = pd.to_numeric(df.loc[data.index, lonc], errors="coerce")
    notes = []
    bad = data["lat"].isna() | data["lon"].isna()
    if bad.any():
        notes.append(f"{int(bad.sum())} sample(s) have an empty or non-numeric latitude/longitude "
                     "(write decimal degrees, e.g. 25.6123) and are left out of the map.")
    data = data[~bad]
    out = (data["lat"].abs() > 90) | (data["lon"].abs() > 180)
    if len(data) and out.mean() > 0.5:
        raise ValueError("The coordinates look like projected values (UTM, metres) and not decimal "
                         "degrees. Convert them to latitude/longitude (WGS84) first.")
    if out.any():
        notes.append(f"{int(out.sum())} sample(s) have coordinates outside the valid range "
                     "(latitude -90..90, longitude -180..180) and are left out.")
    data = data[~out]
    if data.empty:
        raise ValueError("No sample with valid coordinates is left to plot.")
    return data, notes


def to_geojson(data):
    feats = []
    for _, r in data.iterrows():
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"])]},
                      "properties": {"sample": str(r["label"]), "group": str(r["group"]),
                                     "field": int(r["field"]), "field_name": str(r["water_type"]),
                                     "facies": str(r["facies"])}})
    return json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False)


def _colours(data, colour_by, styles):
    """Hex colour of every row."""
    if colour_by == "field":
        return [QUADS[int(q)][2] for q in data["quad"]]
    return [styles[g][0] for g in data["group"]]


# ------------------------------------------------------------------ static map
def _nice_km(span_km):
    raw = span_km / 5
    p = 10 ** np.floor(np.log10(raw))
    for m in (1, 2, 5, 10):
        if m * p >= raw:
            return m * p
    return 10 * p


def map_plot(data, colour_by="field", title="", annotate=False, size=45, alpha=0.9,
             scale_bar=True, north_arrow=True, styles=None,
             font=FONT_FAMILY, font_scale=1.0, font_sizes=None,
             legend=None, legend_cols=1, legend_box=False, figsize=None):
    """Static map. colour_by: "field" (colour = Piper field, symbol = group) or "group"
    (colour and symbol = the style of the group).
    legend: None (right of the map), a corner ("upper right" ...), "none", or (x, y) = top-left corner of
    the legend on the whole figure, 0..1."""
    set_font(font)
    fs = {k: v * font_scale for k, v in {**FS_MAP, **(font_sizes or {})}.items()}
    groups = list(dict.fromkeys(data["group"]))
    counts = data["group"].value_counts()
    auto = _group_styles(groups)
    auto.update({g: tuple(s) for g, s in (styles or {}).items() if g in auto})
    styles = auto
    cols = _colours(data, colour_by, styles)
    data = data.assign(_c=cols)

    fig, ax = plt.subplots(figsize=figsize or (8.6, 7.4), facecolor="white", constrained_layout=True)
    lat0 = float(data["lat"].mean())
    xmin, xmax = data["lon"].min(), data["lon"].max()
    ymin, ymax = data["lat"].min(), data["lat"].max()
    pad_x = max((xmax - xmin) * 0.08, 0.002)
    pad_y = max((ymax - ymin) * 0.08, 0.002)
    ax.set_xlim(xmin - pad_x, xmax + pad_x)
    ax.set_ylim(ymin - pad_y, ymax + pad_y)
    ax.set_aspect(1 / np.cos(np.radians(lat0)))
    ax.grid(True, color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{abs(v):.3f}°{'E' if v >= 0 else 'W'}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{abs(v):.3f}°{'N' if v >= 0 else 'S'}"))
    ax.tick_params(labelsize=fs["tick"], colors=INK)
    for sp in ax.spines.values():
        sp.set_color(INK_SOFT)
    ax.set_xlabel("Longitude", fontsize=fs["axis"], color=INK)
    ax.set_ylabel("Latitude", fontsize=fs["axis"], color=INK)
    if title:
        ax.set_title(title, fontsize=fs["title"], weight="bold", color=INK, loc="left")

    for g in sorted(groups, key=lambda x: -counts[x]):
        d = data[data["group"] == g]
        _, mk, filled = styles[g]
        kw = dict(s=size * SCALE.get(mk, 1.0), marker=mk, alpha=alpha, zorder=5)
        if mk in LINE_ONLY:
            kw.update(c=d["_c"].tolist(), linewidths=1.4)
        elif filled:
            kw.update(c=d["_c"].tolist(), edgecolors="white", linewidths=0.5)
        else:
            kw.update(facecolors="none", edgecolors=d["_c"].tolist(), linewidths=1.4)
        ax.scatter(d["lon"], d["lat"], **kw)
        if annotate:
            for x, y, lab in zip(d["lon"], d["lat"], d["label"]):
                ax.annotate(lab, (x, y), xytext=(4, 4), textcoords="offset points",
                            fontsize=fs["label"], color=INK, zorder=6)

    if scale_bar:                                             # km bar, lower left
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        km_per_deg = 111.32 * np.cos(np.radians(lat0))
        km = _nice_km((x1 - x0) * km_per_deg)
        w = km / km_per_deg
        bx, by = x0 + (x1 - x0) * 0.04, y0 + (y1 - y0) * 0.05
        ax.plot([bx, bx + w], [by, by], color=INK, lw=3, solid_capstyle="butt", zorder=7)
        ax.text(bx + w / 2, by + (y1 - y0) * 0.012, f"{km:g} km", ha="center", va="bottom",
                fontsize=fs["tick"], color=INK, zorder=7)
    if north_arrow:                                           # arrow, top right
        ax.annotate("", xy=(0.95, 0.925), xytext=(0.95, 0.835), xycoords="axes fraction",
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.6), zorder=7)
        ax.text(0.95, 0.935, "N", transform=ax.transAxes, ha="center", va="bottom",
                fontsize=fs["axis"], weight="bold", color=INK, zorder=7)

    # ---- one legend
    def head(t):
        return Line2D([], [], linestyle="none", label=t)
    handles = []
    if colour_by == "field":
        present = sorted(data["quad"].unique())
        handles.append(head("Piper field"))
        for q in present:
            n = int((data["quad"] == q).sum())
            handles.append(Line2D([], [], marker="o", linestyle="none", markerfacecolor=QUADS[q][2],
                                  markeredgecolor="white", markersize=9,
                                  label=f"{q + 1}  {QUADS[q][0]}   (n = {n})"))
        if len(groups) > 1:
            handles += [head(" "), head("Group (symbol)")]
    if colour_by == "group" or len(groups) > 1:
        for g in groups:
            col, mk, filled = styles[g]
            col = "#555555" if colour_by == "field" else col
            solid = filled and mk not in LINE_ONLY
            handles.append(Line2D([], [], marker=mk, linestyle="none",
                                  markerfacecolor=col if solid else "none", markeredgecolor=col,
                                  markersize=LEGEND_MS.get(mk, 9), markeredgewidth=1.4,
                                  label=f"{g}   (n = {counts[g]})"))
    place = legend if legend is not None else "outside"
    if handles and place != "none":
        kw = dict(handles=handles, fontsize=fs["legend"], labelcolor=INK, handletextpad=0.5,
                  labelspacing=0.6, frameon=bool(legend_box), ncol=max(1, int(legend_cols)),
                  borderaxespad=0.6)
        if legend_box:
            kw.update(facecolor="white", edgecolor=GRID, framealpha=0.95)
        if isinstance(place, (tuple, list)):
            leg = fig.legend(loc="upper left", bbox_to_anchor=(float(place[0]), float(place[1])),
                             bbox_transform=fig.transFigure, **kw)
        elif place == "outside":                               # default: right of the map
            leg = ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), **kw)
        else:
            leg = ax.legend(loc=place, **kw)
        for t in leg.get_texts():                              # bold section headings
            if t.get_text() in ("Piper field", "Group (symbol)"):
                t.set_weight("bold")
    return fig


# ------------------------------------------------------------- interactive map
def deck_map(data, colour_by="field", styles=None, size=7, alpha=0.9, style="light"):
    import pydeck as pdk
    groups = list(dict.fromkeys(data["group"]))
    auto = _group_styles(groups)
    auto.update({g: tuple(s) for g, s in (styles or {}).items() if g in auto})
    cols = _colours(data, colour_by, auto)
    d = pd.DataFrame({"lon": data["lon"].values, "lat": data["lat"].values,
                      "label": data["label"].astype(str).values, "group": data["group"].values,
                      "field_txt": [f"{int(q) + 1}. {QUADS[int(q)][0]}" for q in data["quad"]],
                      "colour": [[int(v * 255) for v in to_rgb(c)] + [int(alpha * 255)] for c in cols]})
    layer = pdk.Layer("ScatterplotLayer", d, get_position=["lon", "lat"], get_fill_color="colour",
                      get_line_color=[255, 255, 255, 230], stroked=True, line_width_min_pixels=1,
                      get_radius=size, radius_units=pdk.types.String("pixels"), pickable=True)
    try:
        view = pdk.data_utils.compute_view(d[["lon", "lat"]].values.tolist(), 0.8)
        if not np.isfinite(view.zoom):
            raise ValueError
    except Exception:
        view = pdk.ViewState(latitude=float(d["lat"].mean()), longitude=float(d["lon"].mean()), zoom=11)
    return pdk.Deck(layers=[layer], initial_view_state=view, map_style=style,
                    tooltip={"html": "<b>{label}</b><br/>Group: {group}<br/>Field: {field_txt}",
                             "style": {"fontFamily": "Times New Roman, Liberation Serif, serif"}})


def example_workbook():
    """A small Excel file (bytes) that shows the expected columns (dummy coordinates)."""
    rows = [
        ["S1", "Shallow", 82, 24, 38, 3, 290, 40, 55, 25.601, 85.101],
        ["S2", "Shallow", 64, 18, 95, 5, 310, 110, 60, 25.623, 85.140],
        ["S3", "Shallow", 40, 22, 260, 9, 330, 330, 90, 25.655, 85.172],
        ["S4", "Shallow", 120, 45, 520, 14, 280, 760, 210, 25.690, 85.205],
        ["D1", "Deep", 30, 10, 150, 6, 360, 80, 45, 25.610, 85.120],
        ["D2", "Deep", 18, 6, 310, 8, 420, 230, 70, 25.640, 85.155],
        ["D3", "Deep", 35, 14, 640, 12, 300, 900, 180, 25.672, 85.188],
        ["D4", "Deep", 22, 9, 1100, 20, 250, 1700, 320, 25.705, 85.230],
    ]
    cols = ["Sample", "Group", "Ca", "Mg", "Na", "K", "HCO3", "Cl", "SO4", "Latitude", "Longitude"]
    buf = io.BytesIO()
    pd.DataFrame(rows, columns=cols).to_excel(buf, index=False)
    return buf.getvalue()


def _export_cols(data):
    return data[["label", "group", "lat", "lon", "Ca", "Mg", "NaK", "HCO3", "SO4", "Cl",
                 "field", "water_type", "facies"]].round(4)


# ----------------------------------------------------------------- Streamlit UI
def run_streamlit():
    import streamlit as st

    st.set_page_config(page_title="Sample map", layout="wide")
    st.title("Sample map by Piper field")
    st.write("Upload an Excel/CSV file with **Latitude** and **Longitude** (decimal degrees) and the ions "
             "**Ca, Mg, Na, K, HCO3, (CO3), Cl, SO4**; optional **Sample** and **Group**. "
             "Every sample is placed in one of the 6 Piper-diamond fields and shown on the map. "
             "Your file is only used to draw the maps; this app does not store it.")
    st.download_button("Download an example Excel file", example_workbook(), "map_example.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.sidebar:
        units = st.radio("Concentration units", ["mg/L", "meq/L"])
        colour_by = st.radio("Colour the samples by", ["field", "group"],
                             format_func=lambda k: {"field": "Piper field (1-6)", "group": "Group"}[k])
        title = st.text_input("Title (static map)", "")
        annotate = st.checkbox("Label samples (static map)", value=False)
        size = st.slider("Marker size (static map)", 10, 150, 45)
        alpha = st.slider("Marker opacity", 0.3, 1.0, 0.9)
        sbar = st.checkbox("Scale bar", value=True)
        narrow = st.checkbox("North arrow", value=True)
        bg = st.selectbox("Background of the interactive map", ["light", "road", "dark"])
        dsize = st.slider("Marker size (interactive map, pixels)", 3, 20, 7)
        with st.expander("Text (font and sizes)"):
            font = st.text_input("Font", FONT_FAMILY)
            scale = st.slider("All text, scale", 0.6, 2.0, 1.0, 0.05)
            sizes = {k: st.slider(f"{FS_NAMES[k]} (pt)", 4.0, 40.0, float(FS_MAP[k]), 0.5) for k in FS_MAP}
        with st.expander("Legend position (static map)"):
            where = st.selectbox("Place the legend", list(LEGEND_PRESETS),
                                 format_func=lambda k: "Right of the map (default)" if k == "Default" else k)
            lx = ly = None
            if LEGEND_PRESETS[where] == "custom":
                lx = st.slider("X  (left to right)", 0.0, 1.0, 0.75, 0.01)
                ly = st.slider("Y  (bottom to top)", 0.0, 1.0, 0.90, 0.01)
            lcols = st.slider("Columns", 1, 4, 1)
            lbox = st.checkbox("Draw a box around the legend", value=False)

    up = st.file_uploader("Upload data", type=["xlsx", "xls", "csv"])
    if up is None:
        st.info("Waiting for a file...")
        return
    sheet = 0
    if not up.name.lower().endswith(".csv"):
        sheet = st.selectbox("Sheet", pd.ExcelFile(up).sheet_names)
        up.seek(0)
    try:
        data, notes = prepare_map(read_table(up, sheet), "mgl" if units == "mg/L" else "meql")
    except Exception as e:
        st.error(str(e))
        return
    for n in notes:
        st.warning(n)

    # which samples to show
    groups_all = list(dict.fromkeys(data["group"]))
    fnames = [f"{i + 1}. {n}" for i, (n, d, c) in enumerate(QUADS)]
    c1, c2 = st.columns(2)
    g_pick = c1.multiselect("Groups to show", groups_all, default=groups_all)
    f_pick = c2.multiselect("Piper fields to show", fnames, default=fnames)
    keep = [int(p.split(".")[0]) for p in f_pick]
    data = data[data["group"].isin(g_pick) & data["field"].isin(keep)]
    if data.empty:
        st.info("No sample matches the selection.")
        return

    # symbol (and colour in group mode) of every class
    groups = list(dict.fromkeys(data["group"]))
    auto = _group_styles(groups)
    codes = list(SYMBOLS)
    custom = {}
    with st.sidebar.expander("Symbol and colour of each group", expanded=True):
        st.caption("Symbols are used on the static map; colours only when you colour by group.")
        for g in groups:
            col0, mk0, filled0 = auto[g]
            a, b = st.columns([3, 1])
            code = a.selectbox(g, codes, index=codes.index(symbol_code(mk0, filled0)),
                               format_func=lambda c: SYMBOLS[c][0], key=f"sym_{g}")
            colour = b.color_picker(f"Colour of {g}", col0, key=f"col_{g}", label_visibility="collapsed")
            custom[g] = (colour, SYMBOLS[code][1], SYMBOLS[code][2])

    st.subheader("Interactive map")
    st.caption("Zoom with the mouse wheel, drag to move, hover over a point to read the sample, group and "
               "field. The interactive map shows coloured circles; the symbols are used on the static map.")
    try:
        st.pydeck_chart(deck_map(data, colour_by, custom, dsize, alpha, bg))
    except Exception as e:                                    # background tiles / pydeck problems
        st.warning(f"The interactive map could not be drawn here ({e}). The static map below still works.")
    if colour_by == "field":
        present = sorted(data["quad"].unique())
        st.markdown("  ".join(f"<span style='color:{QUADS[q][2]};font-size:20px'>●</span> "
                              f"{q + 1}. {QUADS[q][0]}" for q in present), unsafe_allow_html=True)

    st.subheader("Static map (for a report)")
    fig = map_plot(data, colour_by, title, annotate, size, alpha, sbar, narrow, custom,
                   font, scale, sizes,
                   legend=(lx, ly) if LEGEND_PRESETS[where] == "custom" else LEGEND_PRESETS[where],
                   legend_cols=lcols, legend_box=lbox)
    st.pyplot(fig)

    a, b, c = st.columns(3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight", facecolor="white")
    a.download_button("Download PNG", buf.getvalue(), "sample_map.png", "image/png")
    res = _export_cols(data)
    b.download_button("Download samples + field (CSV)", res.to_csv(index=False).encode(),
                      "samples_with_field.csv", "text/csv")
    c.download_button("Download GeoJSON (for QGIS / ArcGIS)", to_geojson(data).encode(),
                      "samples.geojson", "application/geo+json")
    with st.expander("How many samples of each group fall in each field", expanded=True):
        st.dataframe(field_table(data))
    with st.expander("Every sample with its coordinates and field"):
        st.dataframe(res.rename(columns={"water_type": "field name"}))


# ------------------------------------------------------------------------- CLI
def run_cli():
    import argparse
    p = argparse.ArgumentParser(description="Static sample map coloured by Piper field")
    p.add_argument("file", nargs="?")
    p.add_argument("--units", choices=["mgl", "meql"], default="mgl")
    p.add_argument("--sheet", default=0)
    p.add_argument("--out", default="sample_map.png")
    p.add_argument("--title", default="")
    p.add_argument("--color-by", choices=["field", "group"], default="field")
    p.add_argument("--annotate", action="store_true")
    p.add_argument("--no-scale-bar", action="store_true")
    p.add_argument("--no-north-arrow", action="store_true")
    p.add_argument("--style", action="append", default=[], metavar="GROUP=SYMBOL:COLOUR")
    p.add_argument("--font", default=FONT_FAMILY)
    p.add_argument("--font-scale", type=float, default=1.0)
    p.add_argument("--legend", default=None, metavar="PLACE",
                   help='upper right | upper left | lower right | lower left | center right | '
                        'center left | none | "x,y" (top-left corner on the figure, 0..1)')
    p.add_argument("--legend-cols", type=int, default=1)
    p.add_argument("--legend-box", action="store_true")
    p.add_argument("--csv", metavar="FILE", help="also save the samples with their field to a CSV file")
    p.add_argument("--geojson", metavar="FILE", help="also save the samples as GeoJSON")
    p.add_argument("--list-symbols", action="store_true")
    a = p.parse_args()
    if a.list_symbols or not a.file:
        print("Symbols:", ", ".join(SYMBOLS))
        return
    styles = dict(parse_style(s) for s in a.style)
    legend = a.legend
    if legend and "," in legend:
        legend = tuple(float(v) for v in legend.split(","))
    data, notes = prepare_map(read_table(a.file, a.sheet), a.units)
    for n in notes:
        print("Note:", n)
    fig = map_plot(data, a.color_by, a.title, a.annotate, scale_bar=not a.no_scale_bar,
                   north_arrow=not a.no_north_arrow, styles=styles, font=a.font,
                   font_scale=a.font_scale, legend=legend, legend_cols=a.legend_cols,
                   legend_box=a.legend_box)
    fig.savefig(a.out, dpi=300, facecolor="white", bbox_inches="tight")
    print("Saved", a.out)
    print(field_table(data).to_string())
    if a.csv:
        _export_cols(data).to_csv(a.csv, index=False)
        print("Saved", a.csv)
    if a.geojson:
        open(a.geojson, "w", encoding="utf-8").write(to_geojson(data))
        print("Saved", a.geojson)


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
        print("Run with:  streamlit run map_app.py   (or)   python map_app.py data.xlsx")
