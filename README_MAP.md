# Sample Map by Piper Field

Upload an Excel or CSV file with **latitude / longitude** and the major ions. Every sample is placed in one
of the **6 fields of the Piper diamond** and shown on a map, so you can see the spatial distribution of
the water types. You get two maps:

* an **interactive map** (street background, zoom, pan, hover to read the sample name, group and field);
* a **static map** for a report: Times New Roman text, scale bar, north arrow, a different symbol for
  every group, movable legend, 300 dpi PNG.

---

## 1. Quick start

    pip install -r requirements.txt
    streamlit run piper_app.py

Open the **Sample Map** page from the page menu on the left. (Only this page: `streamlit run map_app.py`.)

1. Choose the units of the ions (`mg/L` or `meq/L`).
2. Upload the Excel (`.xlsx`, `.xls`) or `.csv` file; pick the sheet if there are several.
3. Choose how to colour the samples: **by Piper field (1-6)** or **by group**.
4. Use "Groups to show" and "Piper fields to show" to display only some samples.
5. Download: **PNG** (static map), **CSV** (every sample with coordinates and field) or **GeoJSON**
   (opens in QGIS / ArcGIS / Google Earth Pro as a point layer).

Click **Download an example Excel file** on the page (or use `map_example_data.xlsx`) to see the layout.

---

## 2. How to format your Excel sheet

One row = one sample, first row = column headings. It is the same table as for the Piper diagram, plus
two coordinate columns.

| Column | Required? | What to put | Accepted headings |
|---|---|---|---|
| **Latitude** | **Yes** | Decimal degrees, north positive | Latitude, Lat, Latitude (N) ... (any heading starting with `lat`) |
| **Longitude** | **Yes** | Decimal degrees, east positive | Longitude, Lon, Long, Lng, Longitude (E) ... (any heading starting with `lon`) |
| Ca, Mg, Na, K, HCO3, Cl, SO4 | Yes | Major ions (same unit for all) | Same names as in the Piper diagram: Ca, Mg, Na, K, HCO3, Cl, SO4 (and Calcium, Sulphate, ...) |
| CO3 | Optional | Carbonate (added to HCO3) | CO3, Carbonate |
| Sample | Optional | Sample name (hover text and labels) | Sample, ID, Name, Station, Well, Label |
| Group | Optional | Class used for symbols/colours and the filter | Group, Type, Class, Category, Facies, Zone |

* **Coordinates must be decimal degrees in WGS84** (for example `25.6123` and `85.1402`), as numbers in
  separate columns. Degree-minute-second text such as `25°36'44"N`, or UTM values in metres, cannot be
  used; convert them first (in Excel, QGIS or an online converter).
* Southern latitudes and western longitudes are negative.
* Do not swap the columns: latitude is about -90..90 (north-south), longitude about -180..180 (east-west).
* A row with an empty or non-numeric coordinate is left out (the page tells you how many). If most
  values lie outside the valid range, the page stops and says the data look like UTM.
* Rules for the ion columns, units, `0` instead of `BDL`, and the Group column are the same as in the
  Piper README (`README.md`, section 2).

### Example

| Sample | Group | Ca | Mg | Na | K | HCO3 | Cl | SO4 | Latitude | Longitude |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | Shallow | 82 | 24 | 38 | 3 | 290 | 40 | 55 | 25.601 | 85.101 |
| D1 | Deep | 30 | 10 | 150 | 6 | 360 | 80 | 45 | 25.610 | 85.120 |

---

## 3. Piper fields used for the colours

| Field | Name | Rule (a = Ca+Mg %, b = SO4+Cl %) |
|---|---|---|
| 1 | Ca-Mg-Cl-SO4 | a + b >= 150 |
| 2 | Ca-Mg-HCO3 | a >= 50 and b < 50 |
| 3 | Na-K-HCO3 | a + b <= 50 |
| 4 | Mixed Ca-Na-HCO3 | a < 50 and b < 50 (and a + b > 50) |
| 5 | Mixed Ca-Mg-Cl | a >= 50 and b >= 50 (and a + b < 150) |
| 6 | Na-K-Cl | a < 50 and b >= 50 |

These are the same fields as in the Piper diamond (see `README.md`, section 4). The table under the maps
shows how many samples of each group fall in each field.

---

## 4. Sidebar controls

| Control | What it does |
|---|---|
| Colour the samples by | **Piper field**: colour = field, and on the static map the symbol = group. **Group**: colour and symbol come from the group's style |
| Title, Label samples | Title and sample names on the static map |
| Marker size / opacity | Size of the symbols (static map; the interactive map has its own size in pixels) |
| Scale bar, North arrow | Switch them on or off on the static map |
| Background of the interactive map | light, road or dark |
| Text (font and sizes) | Times New Roman; sizes of title, axes, ticks, legend, labels, plus one overall scale |
| Legend position | Right of the map (default), a corner inside the map, hidden, or **Custom (X, Y)** with sliders; columns and frame |
| Symbol and colour of each group | Pick the symbol (plus, cross, circle, square, triangle, diamond, star ...) and colour of every group |

The interactive map draws coloured circles only; symbols are used on the static map.

---

## 5. Notes and limits

* The interactive map needs an internet connection in the browser for the street background. If it is
  blocked, the points still show on a blank background.
* The static map has no street background. For a map with roads, rivers or satellite images, download
  the **GeoJSON** (or the CSV with Latitude/Longitude) and add it as a point layer in QGIS or ArcGIS,
  colouring by the `field` column.
* The scale bar is correct for the middle latitude of your samples and is meant for small and medium areas.

---

## 6. Common problems

| Message / problem | Fix |
|---|---|
| "Could not find the coordinate columns" | Add columns called `Latitude` and `Longitude` |
| "The coordinates look like projected values" | Your coordinates are UTM metres; convert to decimal degrees |
| "N sample(s) have an empty or non-numeric latitude/longitude" | Fill in or remove those rows; use numbers, not `25°36'N` |
| Points appear in the wrong place (e.g. in the ocean) | Latitude and longitude are probably swapped, or the sign is wrong (southern/western values must be negative) |
| "Could not find column(s) for ..." | A required ion column is missing; rename it to an accepted heading |
| All samples are in field 6 or 2 | Check the units setting (mg/L or meq/L) |

---

## 7. Command line

    python map_app.py data.xlsx --out sample_map.png
    python map_app.py data.xlsx --color-by group --style "Deep=circle:#e8508a" --style "Shallow=plus:#2a6fd6"
    python map_app.py data.xlsx --legend "lower right" --legend-box --title "Sample locations"
    python map_app.py data.xlsx --csv samples_with_field.csv --geojson samples.geojson
    python map_app.py --list-symbols

Options: `--units mgl|meql`, `--sheet`, `--out`, `--title`, `--color-by field|group`, `--annotate`,
`--no-scale-bar`, `--no-north-arrow`, `--style GROUP=SYMBOL:COLOUR`, `--font`, `--font-scale`,
`--legend` (`"upper right"`, `"lower left"`, `none` or `"x,y"`; default: right of the map),
`--legend-cols`, `--legend-box`, `--csv`, `--geojson`, `--list-symbols`.

---

## 8. Putting it online

Deploy as described in `README.md`: upload `piper_app.py`, `gibbs_app.py`, `map_app.py`, the `pages` folder,
`requirements.txt` and `packages.txt` to the GitHub repository, main file `piper_app.py`. One link serves
Piper, Gibbs and the Sample Map.
