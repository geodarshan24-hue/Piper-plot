# Piper, Gibbs and Map Plotter

This folder holds three tools in one web app: the **Piper diagram** (this file), the **Gibbs diagram**
(`README_GIBBS.md`) and the **sample map** coloured by Piper field (`README_MAP.md`). The Gibbs and Map
pages open from the page menu on the left of the web app.

Upload an Excel or CSV file of water-chemistry data and get a publication-style Piper diagram
(cation triangle, anion triangle and the central diamond) with the 6 numbered diamond fields, a summary panel,
and full control of symbols, colours, text and legend position.

---

## 1. Quick start (web app)

1. Install Python 3.9 or newer, then in a terminal:

       pip install -r requirements.txt
       streamlit run piper_app.py

   A page opens in your browser. (If it is already hosted, just open the link you were given.)
2. Choose the **concentration units** in the left sidebar: `mg/L` (default) or `meq/L`.
3. Click **Browse files** and upload your Excel (`.xlsx`, `.xls`) or `.csv` file.
   If the workbook has several sheets, pick the sheet from the drop-down.
4. The plot appears at once. Change anything in the sidebar and it redraws.
5. Click **Download PNG** (300 dpi) for the figure, or **Download classification (CSV)**: every sample with its Piper field number and name.
   Below the plot, a table shows how many samples of each group fall in each field, and you can
   list which samples belong to which field.

Not sure how your file should look? Click **Download example Excel** on the page, or use
`example_data.xlsx` from this folder, and replace the numbers with yours.

---

## 2. How to format your Excel sheet

### One row = one water sample. The first row holds the column headings.

| Column | Required? | What to put | Heading names that are accepted |
|---|---|---|---|
| Ca | Yes | Calcium | Ca, Ca2+, Calcium |
| Mg | Yes | Magnesium | Mg, Mg2+, Magnesium |
| Na | Yes | Sodium | Na, Na+, Sodium |
| K | Yes | Potassium | K, K+, Potassium |
| HCO3 | Yes | Bicarbonate | HCO3, Bicarbonate, HCO3-, Alkalinity |
| Cl | Yes | Chloride | Cl, Cl-, Chloride |
| SO4 | Yes | Sulphate | SO4, SO4 2-, Sulfate, Sulphate |
| CO3 | Optional | Carbonate (added to HCO3) | CO3, Carbonate |
| Sample | Optional | Sample / well name (shown if you tick "Label samples") | Sample, Sample ID, ID, Name, Station, Well, Label |
| Group | Optional | Class name used for colours and legend | Group, Type, Class, Category, Facies, Zone |
| TDS | Optional | TDS in mg/L (used for "Marker size by TDS") | TDS, TDS (mg/L), Total dissolved solids |

* Heading names are **not case-sensitive**, and spaces, `+`, `-` and digits-as-charge are ignored
  (`Ca`, `CA`, `Ca2+`, `calcium` all work).
* Column order does not matter. Extra columns (pH, EC, date ...) are ignored.
* Use **one unit for all ions**: all in mg/L, or all in meq/L. Tell the app which in the sidebar.
  Do not mix units, and do not use %.
* Numbers only in the ion columns. Do not write `<0.1`, `BDL` or `ND`; type `0` instead.
  Empty or text cells are read as 0.
* Keep it a plain table: no merged cells, no blank rows in the middle, no totals row, no units in
  a second heading row.
* Make sure each sample has at least one cation and one anion value. A row with all zeros in
  cations or anions cannot be plotted and is skipped.

### Example

| Sample | Group | Ca | Mg | Na | K | HCO3 | Cl | SO4 | TDS |
|---|---|---|---|---|---|---|---|---|---|
| S1 | Shallow | 82 | 24 | 38 | 3 | 290 | 40 | 55 | 640 |
| S2 | Shallow | 64 | 18 | 95 | 5 | 310 | 110 | 60 | 980 |
| D1 | Deep | 30 | 10 | 150 | 6 | 360 | 80 | 45 | 950 |
| D2 | Deep | 18 | 6 | 310 | 8 | 420 | 230 | 70 | 1500 |

### Writing the Group column

The **Group** text decides the colour and symbol of each sample. Samples with the same text form
one class (one legend entry).

* **No Group column** - every sample is plotted as one class called "Samples".
* **Shallow and Deep** - write `Shallow` / `Deep` (any capitalisation). The app uses the preset
  style: **blue `+` for Shallow, pink open circle for Deep**.
* **Depth plus salinity** - write names such as `Shallow fresh`, `Shallow brackish`,
  `Shallow saline`, `Deep fresh`, `Deep brackish`, `Deep saline`. Symbol shows depth
  (`+` / circle) and colour shows salinity (blue = fresh, orange = brackish, purple = saline).
  Every row must contain one depth word and one salinity word for this to apply.
* **Years or anything else** - for example `2015 Shallow`, `2015 Deep`, `2022 Shallow`,
  `2022 Deep`. Any other names are given different colours and symbols automatically, and you can
  change every one of them in the sidebar (section 3).
* Spell each class exactly the same way in every row. Extra spaces at the ends are ignored, but
  `Deep`, `deep` and `Deeper` count as different classes.

---

## 3. Using the controls (left sidebar)

| Control | What it does |
|---|---|
| Concentration units | `mg/L` converts to meq/L first; choose `meq/L` if your numbers are already meq/L |
| Title | Text shown above the diagram |
| Show the 6 fields | Shades, outlines (dotted lines) and numbers the six diamond fields (see section 4) |
| List the 6 fields (second legend) | A separate legend that names fields 1-6; you can place it anywhere ("Place the field list" in the legend section) |
| Field summary panel | Adds a side panel with the legend, sample counts and the % of each group's samples in every field |
| Label samples | Writes the Sample name next to every point |
| Marker size / Opacity | Size and transparency of the symbols |
| Marker size by TDS | Bigger symbol = higher TDS (needs a TDS column); a size key is added to the legend |
| **Text (font and sizes)** | Font is Times New Roman. Change the size of title, axis names, tick numbers, legend, captions, zone names and sample labels, or scale everything at once |
| **Legend position** | Pick a preset (top/bottom/left/right corners, middle left/right, hidden) or choose *Custom (X, Y)* and move the two sliders. X goes left to right, Y goes bottom to top. You can also set the number of columns and add a frame |
| **Symbol and colour of each class** | Appears after you upload a file. For every class choose the symbol (plus, cross, open/filled circle, square, triangle, diamond, star ...) and pick any colour |

Tip: the legend can be moved only with the sliders, not by dragging it with the mouse.

---

## 4. How the plot is computed

1. If units are mg/L, each ion is divided by its equivalent weight
   (Ca 20.04, Mg 12.15, Na 22.99, K 39.10, HCO3 61.02, CO3 30.00, Cl 35.45, SO4 48.03) to get meq/L.
2. Cations are expressed as % of total cations (Ca, Mg, Na+K) and anions as % of total anions
   (HCO3+CO3, SO4, Cl).
3. The same sample is drawn three times: in the cation triangle, the anion triangle and the
   diamond (from Ca+Mg and SO4+Cl).
4. **The 6 diamond fields.** Let a = Ca+Mg (%) and b = SO4+Cl (%) (the two diamond axes):

   | Field | Name | Rule |
   |---|---|---|
   | 1 | Ca-Mg-Cl-SO4 (permanent hardness) | a + b >= 150 (top corner) |
   | 2 | Ca-Mg-HCO3 (fresh recharge) | a >= 50 and b < 50 (left corner) |
   | 3 | Na-K-HCO3 (evolved / alkali) | a + b <= 50 (bottom corner) |
   | 4 | Mixed Ca-Na-HCO3 | a < 50 and b < 50 (and a + b > 50) |
   | 5 | Mixed Ca-Mg-Cl | a >= 50 and b >= 50 (and a + b < 150) |
   | 6 | Na-K-Cl (saline / marine) | a < 50 and b >= 50 (right corner) |

   A sample exactly on a boundary goes to the field listed first in the rules above. The CSV download
   has the columns `field` (1-6), `water_type` (name) and `facies` (dominant ions) for every sample.

---

## 5. Common problems

| Message / problem | Fix |
|---|---|
| "Could not find column(s) for: ..." | A required heading is missing or spelt differently. Rename it to one of the accepted names in the table above. The message also lists the columns the app found |
| Plot is empty or points missing | Check that cations and anions are not blank/0 for those rows and that units match the sidebar choice |
| All points sit in one corner | The units are probably wrong (meq/L data read as mg/L, or the reverse) |
| Two classes look the same | Open "Symbol and colour of each class" and change one of them |
| Sheet not the one you want | Choose the correct sheet in the drop-down shown after upload |
| Fonts look different on the web version | The server uses Liberation Serif (same look and width as Times New Roman). On your own computer the real Times New Roman is used |

---

## 6. Command line (no web page)

    python piper_app.py example_data.xlsx --out piper.png
    python piper_app.py data.xlsx --sheet "Sheet2" --units meql --zones --summary
    python piper_app.py data.xlsx --style "Deep=circle:#e8508a" --style "Shallow=plus:#2a6fd6"
    python piper_app.py data.xlsx --legend "0.75,0.93" --legend-cols 2 --legend-box
    python piper_app.py data.xlsx --font-scale 1.2 --sizes "title=18,legend=14"
    python piper_app.py --list-symbols

Options: `--units mgl|meql`, `--sheet`, `--out`, `--title`, `--annotate`, `--zones`, `--summary`,
`--size-by-tds`, `--style GROUP=SYMBOL:COLOUR` (repeatable), `--font`, `--font-scale`, `--sizes`,
`--legend` (`"upper right"`, `"lower left"`, `none`, or `"x,y"` in 0-1 figure coordinates),
`--legend-cols`, `--legend-box`, `--no-field-list`, `--field-legend` (same choices as `--legend`),
`--classify-csv FILE` (save every sample with its field), `--list-symbols`. The command also prints how
many samples of each group fall in each field.

---

## 7. Put it online for everyone (Streamlit Community Cloud, free)

1. Create a **public** GitHub repository and upload `piper_app.py`, `gibbs_app.py`, `map_app.py`, the
   `pages` folder (containing `1_Gibbs_Diagram.py` and `2_Sample_Map.py`), `requirements.txt` and `packages.txt` (code only; never
   upload your data).
2. Go to https://share.streamlit.io, sign in with GitHub and click **Create app**.
3. Choose the repository, branch `main`, main file `piper_app.py`, then **Deploy**.
4. Share the link you get. It shows the Piper page, and the Gibbs page is in the menu on the left. Users upload their own file; the app is only a plotting tool.

To let people on the same Wi-Fi/LAN use your own computer instead:

    streamlit run piper_app.py --server.address 0.0.0.0
