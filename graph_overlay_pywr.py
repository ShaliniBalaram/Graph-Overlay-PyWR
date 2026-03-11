#!/usr/bin/env python3
"""
Graph Overlay Tool — PyWR Edition
==================================
A cross-platform desktop app for overlaying a transparent, zoomable
graph-paper grid on a network diagram, placing typed nodes, drawing
directed edges, and exporting for PyWR water resource models.

Workflow:
  Phase 1 – Load an image (optional) and calibrate grid scale.
  Phase 2 – Lock the grid. Click to place a node — the Properties panel
            opens automatically so you can set Name, Type, and Parameters.
            Click an existing node to re-open its properties. Draw edges,
            then export to CSV or PyWR JSON.

Controls:
  Scroll Wheel        → Grid zoom (before lock) / View zoom (after lock)
  Left Click          → Place new node OR select existing node
  Middle-Drag         → Pan
  Alt+Drag            → Pan (no middle button)
  Right-Click         → Remove nearest node or edge
  Escape              → Deselect node / cancel edge selection
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import csv
import math
import platform

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ── Constants ──────────────────────────────────────────────────────────────────
INITIAL_GRID_SIZE = 40
MIN_GRID_ZOOM     = 0.15
MAX_GRID_ZOOM     = 6.0
MIN_GLOBAL_ZOOM   = 0.05
MAX_GLOBAL_ZOOM   = 12.0
MAJOR_EVERY       = 5

# Colors
BG         = "#0e0e12"
PANEL_BG   = "#16161c"
BORDER_CLR = "#2a2a35"
ACCENT     = "#7c7cff"
NODE_CLR   = "#00ffa3"
TEXT_CLR   = "#cccccc"
DIM_CLR    = "#666666"
EDGE_CLR   = "#ff922b"
SEL_CLR    = "#ffdd00"
ENTRY_BG   = "#22222e"

# PyWR node types and colours
PYWR_NODE_TYPES = [
    "catchment", "river", "reservoir", "storage",
    "demand", "link", "output", "river_gauge", "river_split", "other",
]
PYWR_COLORS = {
    "catchment":   "#51cf66",
    "river":       "#339af0",
    "reservoir":   "#74c0fc",
    "storage":     "#4dabf7",
    "demand":      "#ff6b6b",
    "link":        "#fcc419",
    "output":      "#ff922b",
    "river_gauge": "#cc5de8",
    "river_split": "#f783ac",
    "other":       "#00ffa3",
}

# Suggested PyWR parameters per node type (name → default value)
TYPE_DEFAULTS: dict[str, dict[str, str]] = {
    "catchment":   {"flow": ""},
    "river":       {"cost": "0.0", "min_flow": "0.0"},
    "reservoir":   {"max_volume": "", "min_volume": "0.0",
                    "initial_volume": "", "cost": "0.0"},
    "storage":     {"max_volume": "", "min_volume": "0.0",
                    "initial_volume": "", "cost": "0.0"},
    "demand":      {"max_flow": "", "cost": "-10.0"},
    "link":        {"cost": "0.0", "max_flow": "", "min_flow": "0.0"},
    "output":      {"max_flow": "", "cost": "-500.0"},
    "river_gauge": {"flow_parameter": "", "threshold": ""},
    "river_split": {"factors": "0.5, 0.5"},
    "other":       {},
}

# Sample network (shown when no image is loaded)
SAMPLE_NODES = [
    {"id": "A", "x": 200, "y": 150, "color": "#ff6b6b"},
    {"id": "B", "x": 450, "y": 120, "color": "#51cf66"},
    {"id": "C", "x": 350, "y": 320, "color": "#339af0"},
    {"id": "D", "x": 580, "y": 300, "color": "#fcc419"},
    {"id": "E", "x": 150, "y": 380, "color": "#cc5de8"},
    {"id": "F", "x": 500, "y": 480, "color": "#ff922b"},
]
SAMPLE_EDGES = [
    ("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"),
    ("C", "E"), ("D", "F"), ("E", "F"), ("A", "E"),
]
NODE_MAP = {n["id"]: n for n in SAMPLE_NODES}


class GraphOverlayApp:
    """Main application — PyWR Edition with Node Properties panel."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Graph Overlay Tool — PyWR Edition")
        self.root.configure(bg=BG)
        self.root.geometry("1300x800")
        self.root.minsize(950, 580)

        # ── Core state ─────────────────────────────────────────────────────
        self.grid_zoom    = 1.0
        self.global_zoom  = 1.0
        self.grid_locked  = False
        self.pan_x        = 0.0
        self.pan_y        = 0.0
        self.grid_opacity = 0.45
        self.show_network = True

        self.placed_nodes: list[dict]  = []
        self.placed_edges: list[tuple] = []
        self.node_counter = 1

        self.edge_mode     = False
        self._edge_src     = None

        # Selection
        self._selected_id  = None   # id of selected node (for property editing)

        # Background image
        self._bg_image = None
        self._bg_photo = None

        # Pan drag
        self._pan_dragging = False
        self._pan_start_x  = 0
        self._pan_start_y  = 0
        self._pan_start_ox = 0.0
        self._pan_start_oy = 0.0

        # Hover
        self._hover_coord  = None
        self._hover_screen = (0, 0)

        # Props panel live vars (rebuilt per selection)
        self._name_var     = None
        self._type_var     = None
        self._param_vars: dict[str, tk.StringVar] = {}

        # Default node type for new placements (toolbar dropdown)
        self._new_node_type = tk.StringVar(value="river")

        # ── Build UI ───────────────────────────────────────────────────────
        self._build_toolbar()
        self._build_main_area()
        self._build_statusbar()

        self.root.after(50, self.redraw)

    # ══════════════════════════════════════════════════════════════════════════
    # UI Construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_toolbar(self):
        bar   = tk.Frame(self.root, bg=PANEL_BG)
        bar.pack(side=tk.TOP, fill=tk.X)
        inner = tk.Frame(bar, bg=PANEL_BG, padx=12, pady=8)
        inner.pack(fill=tk.X)

        tk.Label(inner, text="GRAPH OVERLAY — PyWR", bg=PANEL_BG, fg=ACCENT,
                 font=("Courier", 11, "bold")).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(inner, text="Load Image", command=self._load_image,
                  **self._btn()).pack(side=tk.LEFT, padx=2)
        self._sep(inner)

        # Grid scale
        self.grid_frame = tk.Frame(inner, bg=PANEL_BG)
        self.grid_frame.pack(side=tk.LEFT, padx=4)
        tk.Label(self.grid_frame, text="Grid Scale", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(self.grid_frame, text="−", command=self._grid_zoom_out,
                  **self._btn()).pack(side=tk.LEFT)
        self.grid_zoom_lbl = tk.Label(self.grid_frame, text="1.00×", width=6,
                                      bg=PANEL_BG, fg=TEXT_CLR, font=("Courier", 10))
        self.grid_zoom_lbl.pack(side=tk.LEFT)
        tk.Button(self.grid_frame, text="+", command=self._grid_zoom_in,
                  **self._btn()).pack(side=tk.LEFT)
        self._sep(inner)

        # Opacity
        tk.Label(inner, text="Opacity", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(4, 4))
        self.opacity_var = tk.DoubleVar(value=self.grid_opacity)
        ttk.Scale(inner, from_=0.05, to=1.0, variable=self.opacity_var,
                  length=80, command=self._on_opacity).pack(side=tk.LEFT)
        self.opacity_lbl = tk.Label(inner, text="45%", width=4, bg=PANEL_BG,
                                    fg=DIM_CLR, font=("Courier", 9))
        self.opacity_lbl.pack(side=tk.LEFT)
        self._sep(inner)

        # Lock
        self.lock_btn = tk.Button(inner, text="🔓 Lock Grid",
                                  command=self._toggle_lock, **self._btn(wide=True))
        self.lock_btn.pack(side=tk.LEFT, padx=4)

        # Post-lock controls
        self.post_lock_frame = tk.Frame(inner, bg=PANEL_BG)

        self._sep(self.post_lock_frame)
        tk.Label(self.post_lock_frame, text="View Zoom", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(4, 4))
        tk.Button(self.post_lock_frame, text="−", command=self._global_zoom_out,
                  **self._btn()).pack(side=tk.LEFT)
        self.global_zoom_lbl = tk.Label(self.post_lock_frame, text="1.00×", width=6,
                                        bg=PANEL_BG, fg=TEXT_CLR, font=("Courier", 10))
        self.global_zoom_lbl.pack(side=tk.LEFT)
        tk.Button(self.post_lock_frame, text="+", command=self._global_zoom_in,
                  **self._btn()).pack(side=tk.LEFT)
        tk.Button(self.post_lock_frame, text="Reset", command=self._reset_view,
                  **self._btn()).pack(side=tk.LEFT, padx=(4, 0))
        self._sep(self.post_lock_frame)

        # Default node type (used when clicking empty canvas)
        tk.Label(self.post_lock_frame, text="New Node", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Combobox(self.post_lock_frame, textvariable=self._new_node_type,
                     values=PYWR_NODE_TYPES, state="readonly", width=11,
                     font=("Courier", 9)).pack(side=tk.LEFT)
        self._sep(self.post_lock_frame)

        # Edge mode
        self.edge_btn = tk.Button(self.post_lock_frame, text="Draw Edge",
                                  command=self._toggle_edge_mode, **self._btn())
        self.edge_btn.pack(side=tk.LEFT, padx=2)
        self._sep(self.post_lock_frame)

        tk.Button(self.post_lock_frame, text="Undo", command=self._undo_node,
                  **self._btn(fg="#ff6b6b")).pack(side=tk.LEFT, padx=2)
        tk.Button(self.post_lock_frame, text="Clear All", command=self._clear_nodes,
                  **self._btn(fg="#ff6b6b")).pack(side=tk.LEFT, padx=2)

        # Right: Export tab toggle
        right = tk.Frame(inner, bg=PANEL_BG)
        right.pack(side=tk.RIGHT)
        self.export_tab_btn = tk.Button(right, text="Export Panel",
                                        command=self._switch_to_export,
                                        **self._btn(wide=True))
        self.export_tab_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.net_var = tk.BooleanVar(value=True)
        tk.Checkbutton(right, text="Sample Net", variable=self.net_var,
                       bg=PANEL_BG, fg=DIM_CLR, selectcolor=BG,
                       activebackground=PANEL_BG, activeforeground=TEXT_CLR,
                       font=("Courier", 9), command=self._on_toggle_network
                       ).pack(side=tk.RIGHT, padx=8)

    def _build_main_area(self):
        self.main_frame = tk.Frame(self.root, bg=BG)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Canvas
        self.canvas = tk.Canvas(self.main_frame, bg=BG, highlightthickness=0, cursor="arrow")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>",          self._on_click)
        self.canvas.bind("<Motion>",            self._on_motion)
        self.canvas.bind("<Button-2>",          self._on_pan_start)
        self.canvas.bind("<B2-Motion>",         self._on_pan_motion)
        self.canvas.bind("<ButtonRelease-2>",   self._on_pan_end)
        self.canvas.bind("<Alt-Button-1>",      self._on_pan_start)
        self.canvas.bind("<Alt-B1-Motion>",     self._on_pan_motion)
        self.canvas.bind("<Alt-ButtonRelease-1>", self._on_pan_end)
        self.canvas.bind("<Button-3>",          self._on_right_click)
        self.canvas.bind("<Leave>",             self._on_leave)
        self.canvas.bind("<Configure>",         lambda e: self.redraw())
        self.root.bind("<Escape>",              self._on_escape)

        if platform.system() == "Darwin":
            self.canvas.bind("<MouseWheel>", self._on_scroll_mac)
        else:
            self.canvas.bind("<MouseWheel>", self._on_scroll_win)
            self.canvas.bind("<Button-4>",   lambda e: self._do_scroll(1.08, e))
            self.canvas.bind("<Button-5>",   lambda e: self._do_scroll(0.92, e))

        # ── Right panel (always present, tabbed) ──
        self.right_panel = tk.Frame(self.main_frame, bg=PANEL_BG, width=340)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_panel.pack_propagate(False)

        # Style notebook for dark theme
        style = ttk.Style()
        style.configure("Dark.TNotebook",        background=PANEL_BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",    background=BORDER_CLR, foreground=DIM_CLR,
                         font=("Courier", 9, "bold"), padding=[10, 4])
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", BG)])

        self.notebook = ttk.Notebook(self.right_panel, style="Dark.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.props_tab   = tk.Frame(self.notebook, bg=PANEL_BG)
        self.export_tab  = tk.Frame(self.notebook, bg=PANEL_BG)
        self.notebook.add(self.props_tab,  text=" Properties ")
        self.notebook.add(self.export_tab, text="  Export  ")

        self._refresh_props()
        self._refresh_export()

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=PANEL_BG)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_lbl = tk.Label(bar, text="", bg=PANEL_BG, fg=DIM_CLR,
                                   font=("Courier", 9), anchor="w", padx=12, pady=4)
        self.status_lbl.pack(fill=tk.X)

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _btn(fg=TEXT_CLR, wide=False):
        return dict(bg="#2a2a35", fg=fg, activebackground="#3a3a48",
                    activeforeground="#ffffff", relief="flat", bd=0,
                    font=("Courier", 10, "bold"),
                    padx=12 if wide else 6, pady=2, cursor="hand2")

    def _sep(self, parent):
        tk.Frame(parent, width=1, height=22, bg=BORDER_CLR).pack(side=tk.LEFT, padx=6)

    @property
    def effective_grid_size(self):
        return INITIAL_GRID_SIZE * self.grid_zoom

    def screen_to_grid(self, sx, sy):
        gx  = (sx - self.pan_x) / self.global_zoom
        gy  = (sy - self.pan_y) / self.global_zoom
        egs = self.effective_grid_size
        return {"col": round(gx / egs, 2), "row": round(gy / egs, 2),
                "px":  round(gx, 1),       "py":  round(gy, 1)}

    def world_to_screen(self, wx, wy):
        return (wx * self.global_zoom + self.pan_x,
                wy * self.global_zoom + self.pan_y)

    def _node_by_id(self, nid):
        for n in self.placed_nodes:
            if n["id"] == nid:
                return n
        return None

    def _nearest_placed_node(self, ex, ey, threshold=25):
        best_i, best_d = -1, float("inf")
        for i, nd in enumerate(self.placed_nodes):
            sx, sy = self.world_to_screen(nd["px"], nd["py"])
            d = math.hypot(ex - sx, ey - sy)
            if d < best_d:
                best_d, best_i = d, i
        if best_d < threshold * max(1.0, self.global_zoom) and best_i >= 0:
            return best_i, best_d
        return -1, float("inf")

    @staticmethod
    def _point_to_segment(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx*dx + dy*dy)))
        return math.hypot(px - (ax + t*dx), py - (ay + t*dy))

    # ══════════════════════════════════════════════════════════════════════════
    # Node Properties Panel
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_props(self):
        """Rebuild the Properties tab for the currently selected node."""
        for w in self.props_tab.winfo_children():
            w.destroy()
        self._param_vars.clear()

        nd = self._node_by_id(self._selected_id)

        if nd is None:
            # No selection — placeholder
            tk.Label(self.props_tab,
                     text="\n  Click a node to\n  view / edit its\n  properties.",
                     bg=PANEL_BG, fg=DIM_CLR, font=("Courier", 10),
                     justify="left").pack(pady=50, padx=14, anchor="w")
            tk.Label(self.props_tab,
                     text="  Or place a new node —\n  the panel opens automatically.",
                     bg=PANEL_BG, fg="#444455", font=("Courier", 9),
                     justify="left").pack(padx=14, anchor="w")
            return

        # ── Header ──
        color = PYWR_COLORS.get(nd["type"], NODE_CLR)
        hdr = tk.Frame(self.props_tab, bg=color)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"  NODE #{nd['id']}",
                 bg=color, fg=BG, font=("Courier", 11, "bold"),
                 anchor="w", pady=6).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(hdr, text="✕", command=self._deselect,
                  bg=color, fg=BG, font=("Courier", 10, "bold"), relief="flat",
                  padx=8, cursor="hand2").pack(side=tk.RIGHT)

        tk.Label(self.props_tab,
                 text=f"  col={nd['col']}  row={nd['row']}",
                 bg=PANEL_BG, fg=DIM_CLR, font=("Courier", 8),
                 anchor="w").pack(fill=tk.X, pady=(4, 0))

        self._hsep()

        # ── Name ──
        self._field_label("Name")
        self._name_var = tk.StringVar(value=nd["name"])
        e = tk.Entry(self.props_tab, textvariable=self._name_var,
                     bg=ENTRY_BG, fg=TEXT_CLR, font=("Courier", 10),
                     relief="flat", insertbackground=TEXT_CLR)
        e.pack(fill=tk.X, padx=10, pady=(0, 6))
        self._name_var.trace_add("write", lambda *_: self._apply_name())

        # ── Type ──
        self._field_label("Type")
        self._type_var = tk.StringVar(value=nd["type"])
        cb = ttk.Combobox(self.props_tab, textvariable=self._type_var,
                          values=PYWR_NODE_TYPES, state="readonly",
                          font=("Courier", 10))
        cb.pack(fill=tk.X, padx=10, pady=(0, 2))
        self._type_var.trace_add("write", lambda *_: self._apply_type())

        self._hsep()

        # ── Parameters ──
        phdr = tk.Frame(self.props_tab, bg=PANEL_BG)
        phdr.pack(fill=tk.X, padx=10, pady=(4, 2))
        tk.Label(phdr, text="PARAMETERS", bg=PANEL_BG, fg=NODE_CLR,
                 font=("Courier", 9, "bold")).pack(side=tk.LEFT)
        tk.Button(phdr, text="↺ load defaults", command=self._load_defaults,
                  bg=PANEL_BG, fg=DIM_CLR, font=("Courier", 8), relief="flat",
                  padx=4, cursor="hand2").pack(side=tk.RIGHT)

        # Scrollable params area
        outer = tk.Frame(self.props_tab, bg=PANEL_BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=10)

        pcanvas = tk.Canvas(outer, bg=PANEL_BG, highlightthickness=0, height=260)
        psb     = ttk.Scrollbar(outer, orient="vertical", command=pcanvas.yview)
        self._params_inner = tk.Frame(pcanvas, bg=PANEL_BG)
        self._params_inner.bind(
            "<Configure>",
            lambda e: pcanvas.configure(scrollregion=pcanvas.bbox("all")))
        pcanvas.create_window((0, 0), window=self._params_inner, anchor="nw")
        pcanvas.configure(yscrollcommand=psb.set)
        pcanvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        psb.pack(side=tk.RIGHT, fill=tk.Y)

        self._pcanvas = pcanvas   # keep ref for mousewheel binding
        self._bind_scroll(pcanvas)
        self._rebuild_param_rows(nd)

        self._hsep()

        # ── Add custom parameter ──
        tk.Label(self.props_tab, text="Add parameter", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 8), anchor="w").pack(fill=tk.X, padx=10)
        add_row = tk.Frame(self.props_tab, bg=PANEL_BG)
        add_row.pack(fill=tk.X, padx=10, pady=(2, 6))

        self._new_key_var = tk.StringVar()
        self._new_val_var = tk.StringVar()
        tk.Entry(add_row, textvariable=self._new_key_var, bg=ENTRY_BG, fg=TEXT_CLR,
                 font=("Courier", 9), relief="flat", width=11,
                 insertbackground=TEXT_CLR).pack(side=tk.LEFT, padx=(0, 2))
        tk.Entry(add_row, textvariable=self._new_val_var, bg=ENTRY_BG, fg=NODE_CLR,
                 font=("Courier", 9), relief="flat", width=9,
                 insertbackground=NODE_CLR).pack(side=tk.LEFT, padx=(0, 2))
        tk.Button(add_row, text="+ Add", command=self._add_custom_param,
                  bg=ACCENT, fg=BG, font=("Courier", 9, "bold"), relief="flat",
                  padx=4, pady=1, cursor="hand2").pack(side=tk.LEFT)

    def _rebuild_param_rows(self, nd):
        """Populate the scrollable param table from nd['params']."""
        for w in self._params_inner.winfo_children():
            w.destroy()
        self._param_vars.clear()

        if not nd.get("params"):
            tk.Label(self._params_inner,
                     text="  (no parameters — click ↺ load defaults\n   or add custom below)",
                     bg=PANEL_BG, fg="#444455", font=("Courier", 8),
                     justify="left").pack(anchor="w", pady=6)
            return

        for key, val in nd["params"].items():
            self._add_param_row_widget(nd, key, str(val))

    def _add_param_row_widget(self, nd, key, val):
        """Add one key-value row widget."""
        row = tk.Frame(self._params_inner, bg=PANEL_BG)
        row.pack(fill=tk.X, pady=1)

        tk.Label(row, text=key, bg=PANEL_BG, fg=TEXT_CLR,
                 font=("Courier", 9), width=15, anchor="w").pack(side=tk.LEFT)

        var = tk.StringVar(value=val)
        self._param_vars[key] = var

        e = tk.Entry(row, textvariable=var, bg=ENTRY_BG, fg=NODE_CLR,
                     font=("Courier", 9), relief="flat", width=9,
                     insertbackground=NODE_CLR)
        e.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 2))

        def on_change(*args, k=key, v=var):
            n = self._node_by_id(self._selected_id)
            if n:
                n["params"][k] = v.get()
        var.trace_add("write", on_change)

        def remove(k=key):
            n = self._node_by_id(self._selected_id)
            if n and k in n.get("params", {}):
                del n["params"][k]
            self._rebuild_param_rows(n)
        tk.Button(row, text="✕", command=remove,
                  bg=PANEL_BG, fg="#554444", font=("Courier", 8), relief="flat",
                  padx=2, cursor="hand2").pack(side=tk.LEFT)

    def _apply_name(self):
        nd = self._node_by_id(self._selected_id)
        if nd and self._name_var:
            nd["name"] = self._name_var.get()
            self.redraw()

    def _apply_type(self):
        nd = self._node_by_id(self._selected_id)
        if nd and self._type_var:
            nd["type"] = self._type_var.get()
            self._new_node_type.set(nd["type"])   # sync toolbar dropdown
            self.redraw()

    def _load_defaults(self):
        """Merge type-default parameters into the selected node (don't overwrite)."""
        nd = self._node_by_id(self._selected_id)
        if nd is None:
            return
        defaults = TYPE_DEFAULTS.get(nd["type"], {})
        if not defaults:
            return
        params = nd.setdefault("params", {})
        for k, v in defaults.items():
            if k not in params:
                params[k] = v
        self._rebuild_param_rows(nd)

    def _add_custom_param(self):
        key = (self._new_key_var.get() if self._new_key_var else "").strip()
        val = (self._new_val_var.get() if self._new_val_var else "").strip()
        if not key:
            return
        nd = self._node_by_id(self._selected_id)
        if nd is None:
            return
        params = nd.setdefault("params", {})
        params[key] = val
        self._new_key_var.set("")
        self._new_val_var.set("")
        self._rebuild_param_rows(nd)

    def _deselect(self):
        self._selected_id = None
        self._refresh_props()
        self.redraw()

    def _field_label(self, text):
        tk.Label(self.props_tab, text=text, bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 8), anchor="w").pack(fill=tk.X, padx=10, pady=(6, 1))

    def _hsep(self):
        tk.Frame(self.props_tab, height=1, bg=BORDER_CLR).pack(fill=tk.X, padx=6, pady=4)

    def _bind_scroll(self, widget):
        """Bind mousewheel to a canvas widget for scrolling."""
        if platform.system() == "Darwin":
            widget.bind("<MouseWheel>",
                        lambda e: widget.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        else:
            widget.bind("<MouseWheel>",
                        lambda e: widget.yview_scroll(-1 if e.delta > 0 else 1, "units"))
            widget.bind("<Button-4>", lambda e: widget.yview_scroll(-1, "units"))
            widget.bind("<Button-5>", lambda e: widget.yview_scroll(1,  "units"))

    def _switch_to_export(self):
        self.notebook.select(1)
        self._refresh_export()

    def _switch_to_props(self):
        self.notebook.select(0)

    # ══════════════════════════════════════════════════════════════════════════
    # Image Loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_image(self):
        if not PIL_AVAILABLE:
            messagebox.showwarning("Pillow Not Installed",
                                   "pip install pillow")
            return
        path = filedialog.askopenfilename(
            title="Open Background Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("All", "*.*")])
        if not path:
            return
        try:
            self._bg_image = Image.open(path)
            self.net_var.set(False)
            self.show_network = False
            self.redraw()
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image:\n{e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Drawing
    # ══════════════════════════════════════════════════════════════════════════

    def redraw(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return

        gz         = self.global_zoom
        egs        = self.effective_grid_size
        step       = egs * gz
        major_step = step * MAJOR_EVERY

        # Background image
        if self._bg_image:
            iw = max(1, int(self._bg_image.width  * gz))
            ih = max(1, int(self._bg_image.height * gz))
            self._bg_photo = ImageTk.PhotoImage(
                self._bg_image.resize((iw, ih), Image.LANCZOS))
            c.create_image(self.pan_x, self.pan_y, anchor="nw", image=self._bg_photo)

        # Grid colours
        def blend(op, br=0x7c, bg=0x7c, bb=0xff, dr=0x0e, dg=0x0e, db=0x12):
            return (f"#{int(dr+(br-dr)*op):02x}"
                    f"{int(dg+(bg-dg)*op):02x}"
                    f"{int(db+(bb-db)*op):02x}")

        minor = blend(self.grid_opacity * 0.35)
        major = blend(self.grid_opacity * 0.70)
        label = blend(self.grid_opacity * 0.50)

        if step >= 4:
            ox, oy = self.pan_x % step, self.pan_y % step
            x = ox
            while x < w:
                c.create_line(x, 0, x, h, fill=minor, width=1); x += step
            y = oy
            while y < h:
                c.create_line(0, y, w, y, fill=minor, width=1); y += step

        if major_step >= 8:
            ox, oy = self.pan_x % major_step, self.pan_y % major_step
            x = ox
            while x < w:
                c.create_line(x, 0, x, h, fill=major, width=1)
                c.create_text(x, 10, text=str(round((x-self.pan_x)/step)),
                              fill=label, font=("Courier", 8), anchor="n")
                x += major_step
            y = oy
            while y < h:
                c.create_line(0, y, w, y, fill=major, width=1)
                c.create_text(8, y, text=str(round((y-self.pan_y)/step)),
                              fill=label, font=("Courier", 8), anchor="w")
                y += major_step

        # Sample network
        if self.show_network and not self._bg_image:
            for a_id, b_id in SAMPLE_EDGES:
                a, b = NODE_MAP[a_id], NODE_MAP[b_id]
                ax, ay = self.world_to_screen(a["x"], a["y"])
                bx, by = self.world_to_screen(b["x"], b["y"])
                c.create_line(ax, ay, bx, by, fill="#444444", width=1, dash=(6, 3))
            for n in SAMPLE_NODES:
                sx, sy = self.world_to_screen(n["x"], n["y"])
                ro, ri = 16*gz, 9*gz
                c.create_oval(sx-ro,sy-ro,sx+ro,sy+ro, fill="", outline=n["color"], width=1)
                c.create_oval(sx-ri,sy-ri,sx+ri,sy+ri, fill=n["color"], outline="")
                c.create_text(sx, sy, text=n["id"], fill="white",
                              font=("Courier", max(8, int(10*gz)), "bold"))

        # Placed edges
        for (ia, ib) in self.placed_edges:
            na, nb = self._node_by_id(ia), self._node_by_id(ib)
            if na and nb:
                ax, ay = self.world_to_screen(na["px"], na["py"])
                bx, by = self.world_to_screen(nb["px"], nb["py"])
                ashape = (max(6,10*gz), max(8,12*gz), max(3,4*gz))
                c.create_line(ax, ay, bx, by, fill=EDGE_CLR,
                              width=max(1,int(2*gz)), arrow=tk.LAST, arrowshape=ashape)
                c.create_text((ax+bx)/2, (ay+by)/2 - 9,
                              text=f"{na['name']}→{nb['name']}",
                              fill=EDGE_CLR, font=("Courier", max(7,int(8*gz))))

        # Placed nodes
        for nd in self.placed_nodes:
            sx, sy  = self.world_to_screen(nd["px"], nd["py"])
            color   = PYWR_COLORS.get(nd["type"], NODE_CLR)
            is_sel  = (nd["id"] == self._selected_id)
            is_esrc = (self.edge_mode and self._edge_src == nd["id"])
            ro, ri  = 14*gz, 5*gz

            if is_sel:
                # Selection glow
                c.create_oval(sx-ro-4, sy-ro-4, sx+ro+4, sy+ro+4,
                              outline=SEL_CLR, width=2, fill="", dash=(4,3))
            if is_esrc:
                c.create_oval(sx-ro-4, sy-ro-4, sx+ro+4, sy+ro+4,
                              outline=SEL_CLR, width=3, fill="")

            c.create_oval(sx-ro, sy-ro, sx+ro, sy+ro,
                          outline=color, width=2 if not is_sel else 3, fill=BG)
            c.create_oval(sx-ri, sy-ri, sx+ri, sy+ri, fill=color, outline="")

            # Label
            n_params = len(nd.get("params", {}))
            param_hint = f" +{n_params}p" if n_params else ""
            label = f"{nd['name']} [{nd['type'][:3]}]{param_hint}  ({nd['col']},{nd['row']})"
            c.create_text(sx + 17*gz, sy - 12*gz, text=label,
                          fill=SEL_CLR if is_sel else color,
                          font=("Courier", max(7, int(9*gz))), anchor="w")

        # Hover crosshair
        if self.grid_locked and self._hover_coord and not self.edge_mode:
            hx, hy = self._hover_screen
            c.create_line(hx, 0, hx, h, fill=NODE_CLR, width=1, dash=(3, 5))
            c.create_line(0, hy, w, hy, fill=NODE_CLR, width=1, dash=(3, 5))
            coord = self._hover_coord
            txt = f"col:{coord['col']}  row:{coord['row']}"
            c.create_rectangle(hx+14, hy-28, hx+14+len(txt)*7+12, hy-8,
                               fill=BG, outline=ACCENT)
            c.create_text(hx+20, hy-18, text=txt, fill=NODE_CLR,
                          font=("Courier", 9), anchor="w")

        # Calibration hint
        if not self.grid_locked:
            hint = "Scroll to calibrate grid scale  →  then click  Lock Grid"
            tw, cx = len(hint)*7, w//2
            c.create_rectangle(cx-tw//2-12, 14, cx+tw//2+12, 40, fill=BG, outline=ACCENT)
            c.create_text(cx, 27, text=hint, fill=ACCENT, font=("Courier", 10))

        # Status bar
        mode  = "View Zoom" if self.grid_locked else "Grid Scale"
        emode = "  │  EDGE MODE: click source → target  (Esc=cancel)" if self.edge_mode else ""
        sel   = f"  │  Selected: {self._node_by_id(self._selected_id)['name']}" if self._selected_id else ""
        self.status_lbl.config(
            text=(f"Grid: {egs:.1f}px/unit   Zoom: {self.global_zoom:.2f}×   "
                  f"Nodes: {len(self.placed_nodes)}   Edges: {len(self.placed_edges)}"
                  f"{sel}   Scroll={mode}   Mid-Drag=Pan   Right-Click=Remove{emode}")
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Event Handlers
    # ══════════════════════════════════════════════════════════════════════════

    def _on_click(self, event):
        if not self.grid_locked:
            return
        if self.edge_mode:
            self._handle_edge_click(event)
            return

        # Click near existing node → select it
        idx, _ = self._nearest_placed_node(event.x, event.y, threshold=20)
        if idx >= 0:
            self._selected_id = self.placed_nodes[idx]["id"]
            self._refresh_props()
            self._switch_to_props()
        else:
            # Empty canvas → place new node, then open its properties
            self._place_node(event)
            self._selected_id = self.placed_nodes[-1]["id"]
            self._refresh_props()
            self._switch_to_props()
        self.redraw()

    def _place_node(self, event):
        coord = self.screen_to_grid(event.x, event.y)
        ntype = self._new_node_type.get()
        node  = {
            "id":     self.node_counter,
            "name":   f"N{self.node_counter}",
            "type":   ntype,
            "col":    coord["col"],
            "row":    coord["row"],
            "px":     coord["px"],
            "py":     coord["py"],
            "params": dict(TYPE_DEFAULTS.get(ntype, {})),   # pre-fill defaults
        }
        self.placed_nodes.append(node)
        self.node_counter += 1
        self._refresh_export()

    def _handle_edge_click(self, event):
        idx, _ = self._nearest_placed_node(event.x, event.y)
        if idx < 0:
            return
        clicked_id = self.placed_nodes[idx]["id"]
        if self._edge_src is None:
            self._edge_src = clicked_id
        else:
            if self._edge_src != clicked_id:
                pair     = (self._edge_src, clicked_id)
                pair_rev = (clicked_id, self._edge_src)
                if pair not in self.placed_edges and pair_rev not in self.placed_edges:
                    self.placed_edges.append(pair)
                    self._refresh_export()
            self._edge_src = None
        self.redraw()

    def _on_right_click(self, event):
        idx, d_node = self._nearest_placed_node(event.x, event.y, threshold=30)
        best_e, best_ed = -1, float("inf")
        for i, (ia, ib) in enumerate(self.placed_edges):
            na, nb = self._node_by_id(ia), self._node_by_id(ib)
            if na and nb:
                ax, ay = self.world_to_screen(na["px"], na["py"])
                bx, by = self.world_to_screen(nb["px"], nb["py"])
                d = self._point_to_segment(event.x, event.y, ax, ay, bx, by)
                if d < best_ed:
                    best_ed, best_e = d, i

        if idx >= 0 and d_node <= best_ed:
            removed_id = self.placed_nodes.pop(idx)["id"]
            self.placed_edges = [(a,b) for (a,b) in self.placed_edges
                                 if a != removed_id and b != removed_id]
            if self._edge_src == removed_id:
                self._edge_src = None
            if self._selected_id == removed_id:
                self._selected_id = None
                self._refresh_props()
        elif best_e >= 0 and best_ed < 15:
            self.placed_edges.pop(best_e)

        self.redraw()
        self._refresh_export()

    def _on_motion(self, event):
        if self.grid_locked and not self.edge_mode:
            self._hover_coord  = self.screen_to_grid(event.x, event.y)
            self._hover_screen = (event.x, event.y)
            self.canvas.config(cursor="crosshair")
        else:
            self._hover_coord = None
            self.canvas.config(cursor="hand2" if self.grid_locked else "arrow")
        self.redraw()

    def _on_leave(self, event):
        self._hover_coord = None
        self.redraw()

    def _on_escape(self, event):
        if self.edge_mode and self._edge_src is not None:
            self._edge_src = None
        elif self._selected_id is not None:
            self._deselect()
        self.redraw()

    # Pan
    def _on_pan_start(self, event):
        self._pan_dragging = True
        self._pan_start_x, self._pan_start_y = event.x, event.y
        self._pan_start_ox, self._pan_start_oy = self.pan_x, self.pan_y
        self.canvas.config(cursor="fleur")

    def _on_pan_motion(self, event):
        if not self._pan_dragging:
            return
        self.pan_x = self._pan_start_ox + (event.x - self._pan_start_x)
        self.pan_y = self._pan_start_oy + (event.y - self._pan_start_y)
        self.redraw()

    def _on_pan_end(self, event):
        self._pan_dragging = False
        self.canvas.config(cursor="crosshair" if self.grid_locked else "arrow")

    # Scroll
    def _on_scroll_mac(self, event):
        self._do_scroll(1.04 if event.delta > 0 else 0.96, event)

    def _on_scroll_win(self, event):
        self._do_scroll(1.08 if event.delta > 0 else 0.92, event)

    def _do_scroll(self, factor, event):
        if not self.grid_locked:
            self.grid_zoom = max(MIN_GRID_ZOOM, min(MAX_GRID_ZOOM, self.grid_zoom * factor))
            self.grid_zoom_lbl.config(text=f"{self.grid_zoom:.2f}×")
        else:
            old = self.global_zoom
            self.global_zoom = max(MIN_GLOBAL_ZOOM, min(MAX_GLOBAL_ZOOM, old * factor))
            scale = self.global_zoom / old
            self.pan_x = event.x - scale * (event.x - self.pan_x)
            self.pan_y = event.y - scale * (event.y - self.pan_y)
            self.global_zoom_lbl.config(text=f"{self.global_zoom:.2f}×")
        self.redraw()

    # Toolbar actions
    def _grid_zoom_in(self):
        if self.grid_locked: return
        self.grid_zoom = min(MAX_GRID_ZOOM, self.grid_zoom * 1.2)
        self.grid_zoom_lbl.config(text=f"{self.grid_zoom:.2f}×"); self.redraw()

    def _grid_zoom_out(self):
        if self.grid_locked: return
        self.grid_zoom = max(MIN_GRID_ZOOM, self.grid_zoom / 1.2)
        self.grid_zoom_lbl.config(text=f"{self.grid_zoom:.2f}×"); self.redraw()

    def _global_zoom_in(self):
        self.global_zoom = min(MAX_GLOBAL_ZOOM, self.global_zoom * 1.2)
        self.global_zoom_lbl.config(text=f"{self.global_zoom:.2f}×"); self.redraw()

    def _global_zoom_out(self):
        self.global_zoom = max(MIN_GLOBAL_ZOOM, self.global_zoom / 1.2)
        self.global_zoom_lbl.config(text=f"{self.global_zoom:.2f}×"); self.redraw()

    def _reset_view(self):
        self.global_zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.global_zoom_lbl.config(text="1.00×"); self.redraw()

    def _toggle_lock(self):
        self.grid_locked = not self.grid_locked
        if self.grid_locked:
            self.lock_btn.config(text="⚡ Grid Locked", bg=ACCENT, fg=BG)
            self.grid_frame.pack_forget()
            self.post_lock_frame.pack(side=tk.LEFT, padx=4)
            self.canvas.config(cursor="crosshair")
        else:
            self.lock_btn.config(text="🔓 Lock Grid", bg="#2a2a35", fg=TEXT_CLR)
            self.post_lock_frame.pack_forget()
            self.grid_frame.pack(side=tk.LEFT, padx=4,
                                 before=self.lock_btn.master.winfo_children()[3])
            self.canvas.config(cursor="arrow")
            self.edge_mode = False; self._edge_src = None
        self.redraw()

    def _toggle_edge_mode(self):
        self.edge_mode = not self.edge_mode
        self._edge_src = None
        self.edge_btn.config(bg=EDGE_CLR if self.edge_mode else "#2a2a35",
                             fg=BG      if self.edge_mode else TEXT_CLR)
        self.redraw()

    def _undo_node(self):
        if self.placed_nodes:
            removed_id = self.placed_nodes.pop()["id"]
            self.placed_edges = [(a,b) for (a,b) in self.placed_edges
                                 if a != removed_id and b != removed_id]
            if self._selected_id == removed_id:
                self._selected_id = None; self._refresh_props()
            self.redraw(); self._refresh_export()

    def _clear_nodes(self):
        self.placed_nodes.clear(); self.placed_edges.clear()
        self.node_counter = 1; self._edge_src = None
        self._selected_id = None
        self._refresh_props(); self.redraw(); self._refresh_export()

    def _on_opacity(self, val):
        self.grid_opacity = float(val)
        self.opacity_lbl.config(text=f"{int(self.grid_opacity * 100)}%"); self.redraw()

    def _on_toggle_network(self):
        self.show_network = self.net_var.get(); self.redraw()

    # ══════════════════════════════════════════════════════════════════════════
    # Export Tab
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_export(self):
        for w in self.export_tab.winfo_children():
            w.destroy()

        tk.Label(self.export_tab, text="EXPORT — PyWR", bg=PANEL_BG, fg=NODE_CLR,
                 font=("Courier", 11, "bold"), anchor="w"
                 ).pack(fill=tk.X, padx=10, pady=(10, 2))
        tk.Label(self.export_tab,
                 text=f"{len(self.placed_nodes)} nodes   {len(self.placed_edges)} edges",
                 bg=PANEL_BG, fg=DIM_CLR, font=("Courier", 9), anchor="w"
                 ).pack(fill=tk.X, padx=10, pady=(0, 8))

        if not self.placed_nodes:
            tk.Label(self.export_tab, text="Place nodes first.",
                     bg=PANEL_BG, fg="#555555", font=("Courier", 9)).pack(pady=30)
            return

        # Node table
        hdr = tk.Frame(self.export_tab, bg="#1e1e28")
        hdr.pack(fill=tk.X, padx=10)
        for col_name, cw in [("#",3),("Name",8),("Type",10),("Col",5),("Row",5),("P",2)]:
            tk.Label(hdr, text=col_name, bg="#1e1e28", fg=ACCENT,
                     font=("Courier", 9, "bold"), width=cw, anchor="w"
                     ).pack(side=tk.LEFT, padx=2, pady=3)

        rc = tk.Canvas(self.export_tab, bg=PANEL_BG, highlightthickness=0, height=140)
        sb = ttk.Scrollbar(self.export_tab, orient="vertical", command=rc.yview)
        sf = tk.Frame(rc, bg=PANEL_BG)
        sf.bind("<Configure>", lambda e: rc.configure(scrollregion=rc.bbox("all")))
        rc.create_window((0, 0), window=sf, anchor="nw")
        rc.configure(yscrollcommand=sb.set)

        for nd in self.placed_nodes:
            rf    = tk.Frame(sf, bg=PANEL_BG)
            rf.pack(fill=tk.X)
            color = PYWR_COLORS.get(nd["type"], NODE_CLR)
            n_p   = len(nd.get("params", {}))
            for val, cw in [(nd["id"],3),(nd["name"],8),(nd["type"],10),
                             (nd["col"],5),(nd["row"],5),(n_p,2)]:
                tk.Label(rf, text=str(val), bg=PANEL_BG, fg=color,
                         font=("Courier", 9), width=cw, anchor="w"
                         ).pack(side=tk.LEFT, padx=2, pady=1)

        rc.pack(fill=tk.BOTH, expand=False, padx=10)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Edges
        if self.placed_edges:
            tk.Label(self.export_tab, text="EDGES", bg=PANEL_BG, fg=EDGE_CLR,
                     font=("Courier", 9, "bold"), anchor="w"
                     ).pack(fill=tk.X, padx=10, pady=(6, 2))
            ef = tk.Frame(self.export_tab, bg=PANEL_BG, height=60)
            ef.pack(fill=tk.X, padx=10); ef.pack_propagate(False)
            for (ia, ib) in self.placed_edges:
                na, nb = self._node_by_id(ia), self._node_by_id(ib)
                if na and nb:
                    tk.Label(ef, text=f"  {na['name']}  →  {nb['name']}",
                             bg=PANEL_BG, fg=EDGE_CLR, font=("Courier", 9),
                             anchor="w").pack(fill=tk.X)

        # JSON preview
        tk.Label(self.export_tab, text="PyWR JSON preview", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9, "bold"), anchor="w"
                 ).pack(fill=tk.X, padx=10, pady=(8, 2))
        txt = tk.Text(self.export_tab, bg=BG, fg=TEXT_CLR,
                      font=("Courier", 9), height=8, wrap=tk.WORD,
                      relief="flat", bd=0, padx=8, pady=6)
        txt.pack(fill=tk.X, padx=10)
        txt.insert("1.0", json.dumps(self._get_pywr_json(), indent=2))
        txt.config(state="disabled")

        # Buttons
        btn_frame = tk.Frame(self.export_tab, bg=PANEL_BG)
        btn_frame.pack(fill=tk.X, padx=10, pady=8)
        for label, cmd, bg, fg in [
            ("Copy",     self._copy_json,      ACCENT,    BG),
            ("JSON",     self._save_json,       "#339af0", "white"),
            ("CSV",      self._save_csv,        "#51cf66", BG),
            ("PyWR JSON",self._save_pywr_json,  "#fcc419", BG),
        ]:
            tk.Button(btn_frame, text=label, command=cmd, bg=bg, fg=fg,
                      font=("Courier", 9, "bold"), relief="flat",
                      padx=4, pady=5, cursor="hand2"
                      ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

    # ── Export data builders ─────────────────────────────────────────────────

    def _get_export_data(self):
        return [
            {"id": n["id"], "name": n["name"], "type": n["type"],
             "grid": {"col": n["col"], "row": n["row"]},
             "pixel": {"x": n["px"], "y": n["py"]},
             "params": n.get("params", {})}
            for n in self.placed_nodes
        ]

    def _get_pywr_json(self):
        nodes = []
        for n in self.placed_nodes:
            entry = {"name": n["name"], "type": n["type"],
                     "comment": f"grid col={n['col']} row={n['row']}"}
            for k, v in n.get("params", {}).items():
                if str(v).strip():
                    try:
                        entry[k] = float(v) if "." in str(v) else int(v)
                    except ValueError:
                        entry[k] = v
            nodes.append(entry)

        edges = [
            [self._node_by_id(a)["name"], self._node_by_id(b)["name"]]
            for (a, b) in self.placed_edges
            if self._node_by_id(a) and self._node_by_id(b)
        ]
        return {
            "metadata": {
                "title":           "Graph Overlay Model",
                "description":     "Generated by Graph Overlay Tool — PyWR Edition",
                "minimum_version": "0.1",
            },
            "timestepper": {"start": "2000-01-01", "end": "2000-12-31", "timestep": 1},
            "nodes":      nodes,
            "edges":      edges,
            "parameters": {},
            "recorders":  {},
        }

    def _copy_json(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(json.dumps(self._get_export_data(), indent=2))
        messagebox.showinfo("Copied", "Copied to clipboard!")

    def _save_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if path:
            with open(path, "w") as f:
                json.dump(self._get_export_data(), f, indent=2)
            messagebox.showinfo("Saved", f"Saved:\n{path}")

    def _save_csv(self):
        """Export nodes as CSV. Parameters become extra columns."""
        path = filedialog.asksaveasfilename(defaultextension=".csv",
            initialfile="nodes",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if not path:
            return
        # Gather all unique param keys across all nodes
        all_param_keys: list[str] = []
        for n in self.placed_nodes:
            for k in n.get("params", {}):
                if k not in all_param_keys:
                    all_param_keys.append(k)

        base_fields = ["id", "name", "type", "col", "row", "px", "py"]
        fieldnames  = base_fields + all_param_keys

        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for n in self.placed_nodes:
                row = {k: n[k] for k in base_fields}
                row.update(n.get("params", {}))
                writer.writerow(row)
        messagebox.showinfo("Saved", f"CSV saved:\n{path}")

    def _save_pywr_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
            initialfile="pywr_model",
            filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if path:
            with open(path, "w") as f:
                json.dump(self._get_pywr_json(), f, indent=2)
            messagebox.showinfo("Saved", f"PyWR model saved:\n{path}")


def main():
    root = tk.Tk()
    if platform.system() == "Windows":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            root.update()
            from ctypes import windll, c_int, byref
            windll.dwmapi.DwmSetWindowAttribute(
                windll.user32.GetParent(root.winfo_id()), 20, byref(c_int(1)), 4)
        except Exception:
            pass
    GraphOverlayApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
