# Graph Overlay Tool — PyWR Edition

A cross-platform desktop app for overlaying a zoomable graph-paper grid on a
network diagram, placing **typed nodes**, drawing **directed edges**, and
exporting directly to **PyWR** water resource model format.

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green)
![PyWR](https://img.shields.io/badge/Export-PyWR%20JSON%20%7C%20CSV-orange)

---

## What's New vs the Base Tool

| Feature | Base Tool | PyWR Edition |
|---|---|---|
| Place nodes | ✓ | ✓ |
| CSV export | ✗ | ✓ |
| PyWR JSON export | ✗ | ✓ |
| Node types (catchment, river…) | ✗ | ✓ |
| Node naming / rename | ✗ | ✓ double-click |
| Directed edge drawing | ✗ | ✓ |
| Load background image | ✗ | ✓ (requires pillow) |

---

## PyWR Node Types

Each node is colour-coded by type:

| Type | Colour | PyWR Use |
|---|---|---|
| `catchment` | green | Inflow source |
| `river` | blue | Flow link |
| `reservoir` / `storage` | light blue | Storage node |
| `demand` | red | Water demand |
| `link` | yellow | Routing node |
| `output` | orange | Terminal sink |
| `river_gauge` | purple | Measurement point |
| `river_split` | pink | Flow split |

---

## How It Works

### Phase 1 — Calibrate the Grid
- **Load Image** — load your network diagram as background (PNG/JPG, requires `pillow`)
- **Scroll wheel** — adjust grid spacing to match your diagram's scale
- **Opacity** slider — see the image beneath the grid
- Click **Lock Grid** when ready

### Phase 2 — Place Nodes & Draw Edges
- Select **Node Type** from the dropdown
- **Left-click** to place a node (auto-named N1, N2…)
- **Double-click** a node to rename it
- Click **Draw Edge**, then click source → target node to create a directed edge
- **Right-click** a node or edge to remove it
- **Esc** cancels an in-progress edge

### Export
- **Save CSV** — `id, name, type, col, row, px, py` — load directly into pandas
- **PyWR JSON** — ready-to-run PyWR model skeleton with your nodes and edges
- **Save JSON** — flat position data for other tools
- **Copy JSON** — copies to clipboard

---

## Loading the CSV into PyWR

```python
import pandas as pd
from pywr.model import Model

# Load positions
nodes_df = pd.read_csv("nodes.csv")

# Build PyWR model from exported JSON
model = Model.load("pywr_model.json")
model.run()
```

---

## Run Directly

Python 3.8+ with tkinter (standard) required.
Pillow is optional — only needed for loading background images.

```bash
pip install pillow          # optional, for background images
python graph_overlay_pywr.py
```

---

## Build Standalone Executable

```bash
pip install pyinstaller pillow
python build.py
# Output → dist/GraphOverlayPyWR  (or .exe on Windows)
```

---

## Controls Reference

| Action | Before Lock (Phase 1) | After Lock — Node Mode | After Lock — Edge Mode |
|---|---|---|---|
| Scroll wheel | Adjust grid scale | Zoom entire view | Zoom entire view |
| Left click | — | Place a node | Select source / target |
| Double-click | — | Rename node | — |
| Middle-drag / Alt+drag | Pan | Pan | Pan |
| Right click | — | Remove node | Remove node or edge |
| Esc | — | — | Cancel edge selection |

---

## Output Formats

### CSV
```
id,name,type,col,row,px,py
1,N1,catchment,2.5,1.0,100.0,40.0
2,N2,river,4.0,3.5,160.0,140.0
```

### PyWR JSON
```json
{
  "metadata": { "title": "Graph Overlay Model" },
  "timestepper": { "start": "2000-01-01", "end": "2000-12-31", "timestep": 1 },
  "nodes": [
    { "name": "N1", "type": "catchment", "comment": "grid col=2.5 row=1.0" },
    { "name": "N2", "type": "river",     "comment": "grid col=4.0 row=3.5" }
  ],
  "edges": [["N1", "N2"]],
  "parameters": {},
  "recorders": {}
}
```

---

## Project Structure

```
Graph Overlay PyWR/
├── graph_overlay_pywr.py   ← Main application (single file)
├── build.py                ← PyInstaller build script
├── requirements.txt        ← pillow (optional)
└── README.md               ← This file
```
