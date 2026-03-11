# Graph Overlay Tool — PyWR Edition

A desktop app for building PyWR water resource network models visually.
Place nodes on a calibrated grid, draw directed edges, assign PyWR parameters,
and export a ready-to-run PyWR JSON model.

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green)
![PyWR](https://img.shields.io/badge/Export-PyWR%20JSON%20%7C%20CSV-orange)

---

## Quick Start

```bash
# 1. Install (Pillow is optional but recommended)
pip install pillow openpyxl

# 2. Run the app
python graph_overlay_pywr.py
```

Python 3.8+ with tkinter is required. tkinter ships with the standard Python
installer on Windows and macOS. On Linux:

```bash
sudo apt install python3-tk   # Debian/Ubuntu
sudo dnf install python3-tkinter   # Fedora
```

---

## How to Build a Network — Step by Step

### Step 1 — Start the app

```bash
python graph_overlay_pywr.py
```

You will see a dark canvas with a grid and a right-side Properties / Export panel.

---

### Step 2 — (Optional) Load a background image

If you have an existing network diagram (PNG, JPG), click **Load Image** in the
top toolbar. The image appears behind the grid so you can trace over it.

Use the **Opacity** slider to make the grid more or less visible over the image.

---

### Step 3 — Calibrate the grid scale

Before placing nodes, set the grid so its cells match the scale of your diagram.

- **Scroll wheel** — zooms the grid spacing in or out
- **Grid Scale − / +** buttons — same effect

Watch the grid cells align with your background image's node positions.

Once the scale looks right, click **Lock Grid**. The toolbar switches to editing
mode. You cannot accidentally change the scale after this point.

---

### Step 4 — Place nodes

1. Choose a **node type** from the dropdown in the toolbar (e.g. `catchment`,
   `input`, `river`, `reservoir` — see full list below).
2. **Left-click** anywhere on the canvas. A node appears at that position and
   the Properties panel opens automatically on the right.
3. In the Properties panel:
   - Type a meaningful **Name** (e.g. `GW_Base`)
   - The **Type** can be changed here too
   - Click **↺ defaults** to load the standard PyWR parameters for that type
   - Edit parameter values directly (e.g. `max_flow`, `cost`, `mrf`)
   - To link a parameter to a CSV/Excel column, click the **📎** button next to it

To rename an existing node, click it to select it, then edit the Name field.

---

### Step 5 — Move nodes

To reposition a node, click and hold it, then drag it to a new position.
All connected edges move with it.

To pan the whole canvas:
- Click the **✋ Pan** button in the toolbar, then drag
- Or hold **Space** and drag
- Or use **middle-mouse drag** (three-finger drag on some trackpads)
- Or **Alt + drag**

---

### Step 6 — Draw edges

1. Click **Draw Edge** in the toolbar (it highlights orange).
2. Click the **source node** (where flow comes from).
3. Click the **destination node** (where flow goes to).
4. An arrow appears. The edge is also listed in the Properties panel when clicked.
5. Click an edge to select it and give it a name.
6. Press **Esc** to cancel an in-progress edge.
7. Click **Draw Edge** again to leave edge-drawing mode.

Edges are directed (they have an arrow). In PyWR terms, flow travels from
source to destination.

---

### Step 7 — Assign PyWR parameters

Select any node. In the Properties panel:

| Action | How |
|---|---|
| Load type defaults | Click **↺ defaults** |
| Edit a value | Click in the value field and type |
| Link to CSV column | Click **📎** next to the parameter, pick file → column |
| Add a custom parameter | Use the key/value row at the bottom, click **+ Add** |
| Remove a parameter | Click **✕** next to it |

When a value is linked to a CSV column it turns purple and shows `$ref::ColumnName`.
At export time this is converted to a PyWR `CSVParameter` or `ExcelParameter`.

---

### Step 8 — Export

Switch to the **Export** tab (or click **Export Panel** in the toolbar).

| Button | What it produces |
|---|---|
| **PyWR JSON** | A complete, ready-to-run PyWR model JSON with nodes, edges, parameters, and schematic positions |
| **CSV** | `nodes.csv` + `nodes_edges.csv` — re-importable into the tool |
| **JSON** | Flat position/node data for other tools |
| **Copy** | Copies JSON to clipboard |
| **Export PNG** | Screenshot of the current canvas |

The PyWR JSON includes `"position": {"schematic": [col, row]}` for each node,
which is used by PyWR's built-in schematic viewer.

---

### Step 9 — Save and reload your session

Click **Save Session** to save your entire canvas state (nodes, edges, view,
background image path) as a `.goverlap` file.

Click **Load Session** to reopen it later. Nothing is lost.

---

## Undo / Redo

| Action | Shortcut |
|---|---|
| Undo | Ctrl+Z (Cmd+Z on Mac) |
| Redo | Ctrl+Shift+Z (Cmd+Shift+Z on Mac) |

The **↩ Undo** and **↪ Redo** buttons in the toolbar do the same thing.
Up to 50 steps are remembered.

---

## Node Types Reference

All standard PyWR node types are available. Choose the type that matches your
network element.

### Core nodes

| Type | Colour | Use |
|---|---|---|
| `input` | Green | Abstraction source: **groundwater, borehole, pumped inflow** |
| `output` | Orange | Terminal sink: demand, treated water output |
| `link` | Yellow | Routing / conveyance (pipe, channel, bypass) |
| `storage` | Blue | Generic tank or reservoir |
| `losslink` | Pink | Link with a leakage or evaporation loss fraction |
| `delaynode` | Purple | Travel-time delay (e.g. river routing lag) |
| `breaklink` | Grey | LP solver helper for large models |
| `piecewiselink` | Deep orange | Non-linear cost tiers |
| `multisplitlink` | Light pink | Flow split with per-slot ratio enforcement |

### Virtual storage — licence accounting

| Type | Use |
|---|---|
| `virtualstorage` | Tracks flow through other nodes — licences, quotas |
| `annualvirtualstorage` | Annual licence (resets each year) |
| `seasonalvirtualstorage` | Seasonal licence (active in a defined period) |
| `monthlyvirtualstorage` | Monthly rolling licence |
| `rollingvirtualstorage` | Rolling window licence (e.g. 30-day) |

### Aggregate / monitoring (non-connectable)

| Type | Use |
|---|---|
| `aggregatednode` | Reports combined flow across multiple nodes |
| `aggregatedstorage` | Reports combined volume across multiple storages |

### River domain

| Type | Colour | Use |
|---|---|---|
| `catchment` | Green | Fixed inflow (min = max flow) |
| `discharge` | Light green | Mid-network discharge point |
| `river` | Blue | River reach |
| `reservoir` | Light blue | Reservoir with optional control curve |
| `rivergauge` | Purple | Gauge with minimum residual flow (MRF) constraint |
| `riversplit` | Pink | Fixed-ratio flow split |
| `riversplithwithgauge` | Lilac | Flow split + MRF constraint combined |

### Groundwater domain

| Type | Colour | Use |
|---|---|---|
| `keatingaquifer` | Indigo | Physics-based aquifer (Keating 2009 model) |

> **Groundwater abstraction note:**
> Use `input` for boreholes and groundwater abstraction points. Set `max_flow`
> to the licence limit, `min_flow` to 0, and `cost` to the abstraction cost
> (lower cost = preferred). To model GW split into base and top-up, place two
> `input` nodes and route both into one `link` node (the total).

---

## Controls Reference

| Action | Before Lock | After Lock |
|---|---|---|
| Scroll wheel | Adjust grid scale | Zoom view |
| Left-click | — | Place node / select node or edge |
| Click + drag (node) | — | Drag node to new position |
| Draw Edge mode | — | Click source, click destination |
| **✋ Pan** button or **Space** + drag | Pan | Pan |
| Middle-drag | Pan | Pan |
| Alt + drag | Pan | Pan |
| **◀ / ▶** strip (right edge) | — | Collapse / expand the Properties panel |
| Right-click | — | Remove nearest node or edge |
| Esc | — | Cancel edge / deselect |

---

## Importing an Existing CSV

If you have a `nodes.csv` (created by a previous Export or prepared manually),
click **Import CSV** in the Export tab. The tool also looks for a matching
`nodes_edges.csv` in the same folder and imports edges automatically.

CSV format for nodes:
```
id,name,type,col,row,px,py,max_flow,cost,...
1,GW_Base,input,4.0,3.0,160.0,120.0,50.0,1.0,
```

CSV format for edges:
```
id,name,src,dst
1,E1,GW_Base,GW_Total
```

---

## Linking Parameters to CSV / Excel

To drive a PyWR parameter from a time-series file:

1. Select a node → in the Properties panel, click **📎** next to a parameter.
2. Choose a `.csv` or `.xlsx` file.
3. Pick the column to use.
4. The value changes to `$ref::ColumnName` (shown in purple).

The exported PyWR JSON automatically converts this to:

```json
"max_flow": {
  "type": "CSVParameter",
  "url": "params.csv",
  "column": "GW_Base_MaxFlow",
  "index_col": "Date",
  "parse_dates": true
}
```

The CSV file must have a `Date` column as the first column (used as the index).

---

## Running the Exported PyWR Model

After clicking **PyWR JSON**, run the model with:

```python
from pywr.model import Model

model = Model.load("pywr_model.json")
model.run()
```

Install PyWR if needed:

```bash
pip install pywr
```

> PyWR requires a C compiler on Linux/macOS for its Cython extensions.
> On Windows, install the Visual C++ Build Tools or use a conda environment.
> Full install guide: https://pywr.github.io/pywr/

---

## Example Network — GW Base / Top-up / Total

The `examples/gw_network/` folder contains a worked example showing how to
model groundwater split into base abstraction, top-up abstraction, and a
total abstraction node where both converge.

### Topology

```
Rainfall_Catchment ──────────────────────────► River_Main
                                                    │
GW_Base   ──► GW_Total (link) ──────────────────────┘
GW_Topup  ──► GW_Total

                               River_Main
                                    │
                             River_Gauge_A   ← MRF constraint
                                    │
                              Reservoir_A
                                    │
                             River_Split_A
                           ┌────────┼────────┐
                     Demand_Urban  Demand_Irrigation  River_Outlet
```

**GW_Base** is always-on, lower-cost base-load abstraction.
**GW_Topup** is higher-cost and only used when demand cannot be met by base alone.
Both converge into **GW_Total** (a `link` node), which then feeds the river.

### Files

| File | Purpose |
|---|---|
| `nodes.csv` | All nodes with positions and parameters |
| `nodes_edges.csv` | All edges (source → destination) |
| `params.csv` | Monthly time-series: flows, abstraction limits, demands |
| `run_example.py` | Builds `pywr_model.json` and runs the PyWR simulation |

### How to run

```bash
cd examples/gw_network

# Install dependencies
pip install pywr pandas

# Build the model JSON and run the simulation
python run_example.py
```

This produces:
- `pywr_model.json` — the complete PyWR model file
- `results.csv` — simulated flows and reservoir volume for each timestep

### How to load the example into the GUI

1. Start the app: `python graph_overlay_pywr.py`
2. Click **Lock Grid**
3. In the **Export** tab, click **Import CSV**
4. Select `examples/gw_network/nodes.csv`
5. The nodes and edges load automatically onto the canvas

---

## Build a Standalone Executable

```bash
pip install pyinstaller pillow
python build.py
# Output: dist/GraphOverlayPyWR  (or .exe on Windows)
```

---

## Project Structure

```
Graph Overlay PyWR/
├── graph_overlay_pywr.py        Main application (single file, ~2000 lines)
├── build.py                     PyInstaller build script
├── requirements.txt             pillow, openpyxl
├── styles.json                  Saved node colour/shape styles (auto-created)
├── README.md                    This file
└── examples/
    └── gw_network/
        ├── nodes.csv            Example node definitions
        ├── nodes_edges.csv      Example edge definitions
        ├── params.csv           Monthly parameter time-series
        └── run_example.py       Build + run PyWR model script
```

---

## PyWR JSON Output Format

```json
{
  "metadata": {
    "title": "Graph Overlay Model",
    "description": "Generated by Graph Overlay Tool — PyWR Edition"
  },
  "timestepper": { "start": "2000-01-01", "end": "2000-12-31", "timestep": 1 },
  "nodes": [
    {
      "name": "GW_Base",
      "type": "input",
      "position": { "schematic": [4.0, 3.0] },
      "max_flow": {
        "type": "CSVParameter",
        "url": "params.csv",
        "column": "GW_Base_MaxFlow",
        "index_col": "Date",
        "parse_dates": true
      },
      "min_flow": 0.0,
      "cost": 1.0
    }
  ],
  "edges": [
    ["GW_Base", "GW_Total"],
    ["GW_Topup", "GW_Total"]
  ],
  "parameters": {},
  "recorders": {}
}
```

The `position.schematic` field is used by PyWR's schematic viewer to place
nodes at the correct grid coordinates from the tool.

---

Author: Shalini B
