# Gibbs Diagram Plotter

Upload an Excel or CSV file of water-chemistry data and get a Gibbs diagram: two panels showing
(a) **Na / (Na + Ca)** and (b) **Cl / (Cl + HCO3)** against **TDS** (log scale), with the
precipitation, rock and evaporation dominance fields. You control symbols, colours, text and legend
position, exactly as in the Piper app. The table below the plot gives the share of each group in
each field.

---

## 1. Quick start

**Web app (Piper and Gibbs together)**

    pip install -r requirements.txt
    streamlit run piper_app.py

The Piper page opens first. Click **Gibbs Diagram** in the left page menu.
To open only the Gibbs page directly: `streamlit run gibbs_app.py`.

1. Choose the **units of the ions** in the sidebar (`mg/L` or `meq/L`). TDS is always in mg/L.
2. Upload your Excel (`.xlsx`, `.xls`) or `.csv` file. Pick the sheet if there are several.
3. The plot appears at once; every sidebar change redraws it.
4. **Download PNG** (300 dpi) or **Download ratios and fields (CSV)**.

Click **Download an example Excel file** on the page (or use `gibbs_example_data.xlsx`) to see the layout.

---

## 2. How to format your Excel sheet

One row = one water sample, first row = column headings.

| Column | Required? | What to put | Accepted headings |
|---|---|---|---|
| Ca | Yes | Calcium | Ca, Ca2+, Calcium |
| Na | Yes | Sodium | Na, Na+, Sodium |
| Cl | Yes | Chloride | Cl, Cl-, Chloride |
| HCO3 | Yes | Bicarbonate | HCO3, Bicarbonate, HCO3-, Alkalinity |
| CO3 | Optional | Carbonate (added to HCO3 in the anion ratio) | CO3, Carbonate |
| **TDS** | **Yes** (see below) | Total dissolved solids **in mg/L** | TDS, TDS (mg/L), Total dissolved solids |
| Sample | Optional | Sample name (shown with "Label samples") | Sample, Sample ID, ID, Name, Station, Well, Label |
| Group | Optional | Class used for colours and legend | Group, Type, Class, Category, Facies, Zone |
| Mg, K, SO4 | Only if TDS is calculated | Needed to add up the TDS | Mg, K, SO4 (Sulphate, Sulfate) |

* Headings are not case-sensitive; extra columns (pH, EC, date ...) are ignored; order does not matter.
* **TDS is plotted as it is in your file (mg/L)**. No TDS column? Tick **Calculate TDS from the ions**:
  TDS = sum of Ca, Mg, Na, K, HCO3, CO3, Cl and SO4 in mg/L (needs the Mg, K and SO4 columns too).
  If your ions are in meq/L they are converted to mg/L first.
* All ions in **one unit** (all mg/L or all meq/L), set in the sidebar. The ratios are calculated
  from meq/L, so the unit choice matters.
* Numbers only. Write `0` instead of `BDL`, `ND` or `<0.1`. Empty cells count as 0.
* No merged cells, blank rows, totals row or a second heading row.
* A sample is skipped if its TDS is empty or 0. If Na + Ca = 0 it is missing from panel (a), and if
  Cl + HCO3 = 0 it is missing from panel (b).

### Example

| Sample | Group | Ca | Mg | Na | K | HCO3 | Cl | SO4 | TDS |
|---|---|---|---|---|---|---|---|---|---|
| S1 | Shallow | 82 | 24 | 38 | 3 | 290 | 40 | 55 | 640 |
| S2 | Shallow | 64 | 18 | 95 | 5 | 310 | 110 | 60 | 980 |
| D1 | Deep | 30 | 10 | 150 | 6 | 360 | 80 | 45 | 950 |
| D2 | Deep | 18 | 6 | 310 | 8 | 420 | 230 | 70 | 1500 |

### The Group column

The **Group** text gives each class its own symbol, colour and legend entry (with the sample count).

* No Group column: all samples form one class, "Samples".
* `Shallow` / `Deep`: preset style, **blue `+` for Shallow and pink open circle for Deep**.
* Names that also contain fresh / brackish / saline (`Deep brackish water`): symbol = depth,
  colour = salinity (blue fresh, orange brackish, purple saline).
* Any other names (for example `2015 Shallow`, `2022 Deep`): automatic different colours and
  symbols, which you can change for each class in the sidebar.
* Spell a class exactly the same in every row; `Deep`, `deep` and `Deeper` are different classes.

---

## 3. Sidebar controls

| Control | What it does |
|---|---|
| Units of the ions | `mg/L` or `meq/L` for Ca, Na, Cl, HCO3 ... (TDS stays mg/L) |
| Calculate TDS from the ions | Use when your file has no TDS column |
| Title | Optional title above the figure |
| Panels | Cations and anions side by side, one above the other, or only one of them |
| Draw the dominance boundaries / Write the field names / Shade the three fields | Switch parts of the background on or off |
| Label samples, Marker size, Marker opacity | Look of the points |
| Text (font and sizes) | Times New Roman; sizes of title, axis names, tick numbers, legend, field names and sample labels, plus one scale for everything |
| Legend position | Below the plot (default), right of the plot, a corner inside the last panel, hidden, or **Custom (X, Y)** with two sliders (X left to right, Y bottom to top); number of columns (0 = automatic) and an optional frame |
| Symbol and colour of each class | Choose the symbol (plus, cross, open/filled circle, square, triangle, diamond, star ...) and any colour for every class |

The legend moves with the sliders, not by dragging with the mouse.

---

## 4. How it is calculated

1. mg/L values are divided by the equivalent weights (Ca 20.04, Na 22.99, Cl 35.45, HCO3 61.02,
   CO3 30.00) to give meq/L.
2. Cations: **Na / (Na + Ca)**. Anions: **Cl / (Cl + HCO3 + CO3)**. (Na is not combined with K.)
3. Each sample is plotted at (TDS, ratio) on a log x-axis from 10 to 100,000 mg/L.
4. Fields: inside the dome = **rock dominance**; outside it, left of the dome's top =
   **precipitation dominance**, right of it = **evaporation dominance**.
5. The dome is the usual schematic outline of Gibbs (1970), drawn for guidance and not digitised
   from the original figure. Samples close to a line can belong to either field, so treat the
   percentages as approximate.

---

## 5. Common problems

| Message / problem | Fix |
|---|---|
| "No TDS column found" | Add a column named `TDS` (mg/L), or tick "Calculate TDS from the ions" |
| "Could not find column(s) for ..." | Rename the heading to one of the accepted names above |
| All points at the far right | TDS is probably in the wrong unit (use mg/L, not g/L) or ions are in the wrong unit |
| Some points missing in one panel | Na + Ca or Cl + HCO3 is 0 for those samples |
| Two classes look alike | Change one in "Symbol and colour of each class" |
| Fonts differ on the web version | The server uses Liberation Serif (same look as Times New Roman) |

---

## 6. Command line

    python gibbs_app.py data.xlsx --out gibbs.png
    python gibbs_app.py data.xlsx --calc-tds --units meql --panels stacked --shade
    python gibbs_app.py data.xlsx --style "Deep=circle:#e8508a" --style "Shallow=plus:#2a6fd6"
    python gibbs_app.py data.xlsx --legend right --legend-cols 1 --legend-box
    python gibbs_app.py data.xlsx --legend "0.75,0.9" --font-scale 1.2 --sizes "title=18,legend=13"
    python gibbs_app.py --list-symbols

Options: `--units mgl|meql`, `--calc-tds`, `--sheet`, `--out`, `--title`, `--panels both|stacked|cations|anions`,
`--annotate`, `--no-boundaries`, `--no-names`, `--shade`, `--style GROUP=SYMBOL:COLOUR` (repeatable),
`--font`, `--font-scale`, `--sizes`, `--legend` (`right`, `"upper right"`, `"lower left"`, `none` or `"x,y"`
in 0-1 figure coordinates; default below the plot), `--legend-cols`, `--legend-box`, `--list-symbols`.
The command also prints the table of samples per field.

---

## 7. Putting it online

Deploy exactly as for the Piper app (see `README.md`): upload all files, including `gibbs_app.py` and
the `pages` folder, to the GitHub repository and set the main file to `piper_app.py`. One link then
serves both diagrams: Piper on the first page, Gibbs and the Sample Map in the page menu.
