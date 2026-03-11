#!/usr/bin/env python3
"""
Graph Overlay Tool — PyWR Edition
==================================
Workflow:
  Phase 1 – Load an image (optional) and calibrate grid scale.
  Phase 2 – Lock the grid. Click canvas to place a node — the Properties
            panel opens automatically. Click an existing node or edge to
            edit its properties. Draw directed edges, split nodes, export.

Controls:
  Scroll Wheel        → Grid zoom (before lock) / View zoom (after lock)
  Left Click          → Place node / Select node or edge
  Middle-Drag         → Pan
  Alt+Drag            → Pan (no middle button)
  Right-Click         → Remove nearest node or edge
  Escape              → Deselect / cancel edge drawing
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

SAMPLE_NODES = [
    {"id": "A", "x": 200, "y": 150, "color": "#ff6b6b"},
    {"id": "B", "x": 450, "y": 120, "color": "#51cf66"},
    {"id": "C", "x": 350, "y": 320, "color": "#339af0"},
    {"id": "D", "x": 580, "y": 300, "color": "#fcc419"},
    {"id": "E", "x": 150, "y": 380, "color": "#cc5de8"},
    {"id": "F", "x": 500, "y": 480, "color": "#ff922b"},
]
SAMPLE_EDGES = [
    ("A","B"),("A","C"),("B","D"),("C","D"),
    ("C","E"),("D","F"),("E","F"),("A","E"),
]
NODE_MAP = {n["id"]: n for n in SAMPLE_NODES}


class GraphOverlayApp:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Graph Overlay Tool — PyWR Edition")
        self.root.configure(bg=BG)
        self.root.geometry("1340x820")
        self.root.minsize(1000, 600)

        # ── Data ───────────────────────────────────────────────────────────
        self.placed_nodes: list[dict] = []
        # Edge dict: {id, src, dst, name}
        self.placed_edges: list[dict] = []
        self.node_counter = 1
        self.edge_counter = 1

        # ── View state ─────────────────────────────────────────────────────
        self.grid_zoom    = 1.0
        self.global_zoom  = 1.0
        self.grid_locked  = False
        self.pan_x        = 0.0
        self.pan_y        = 0.0
        self.grid_opacity = 0.45
        self.show_network = True

        # ── Interaction state ──────────────────────────────────────────────
        self.edge_mode    = False
        self._edge_src    = None        # node id of first click in edge mode

        # Selection — only one active at a time
        self._sel_node_id  = None       # selected node id
        self._sel_edge_id  = None       # selected edge id

        # Pan drag
        self._pan_dragging = False
        self._pan_start_x  = 0
        self._pan_start_y  = 0
        self._pan_start_ox = 0.0
        self._pan_start_oy = 0.0

        # Hover
        self._hover_coord  = None
        self._hover_screen = (0, 0)

        # Background image
        self._bg_image = None
        self._bg_photo = None

        # Live property vars (rebuilt on selection change)
        self._name_var   = None
        self._type_var   = None
        self._ename_var  = None         # edge name var
        self._param_vars: dict[str, tk.StringVar] = {}

        self._new_node_type = tk.StringVar(value="river")

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

        tk.Label(inner, text="Opacity", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(4, 4))
        self.opacity_var = tk.DoubleVar(value=self.grid_opacity)
        ttk.Scale(inner, from_=0.05, to=1.0, variable=self.opacity_var,
                  length=80, command=self._on_opacity).pack(side=tk.LEFT)
        self.opacity_lbl = tk.Label(inner, text="45%", width=4, bg=PANEL_BG,
                                    fg=DIM_CLR, font=("Courier", 9))
        self.opacity_lbl.pack(side=tk.LEFT)
        self._sep(inner)

        self.lock_btn = tk.Button(inner, text="🔓 Lock Grid",
                                  command=self._toggle_lock, **self._btn(wide=True))
        self.lock_btn.pack(side=tk.LEFT, padx=4)

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

        tk.Label(self.post_lock_frame, text="New Node", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Combobox(self.post_lock_frame, textvariable=self._new_node_type,
                     values=PYWR_NODE_TYPES, state="readonly", width=11,
                     font=("Courier", 9)).pack(side=tk.LEFT)
        self._sep(self.post_lock_frame)

        self.edge_btn = tk.Button(self.post_lock_frame, text="Draw Edge",
                                  command=self._toggle_edge_mode, **self._btn())
        self.edge_btn.pack(side=tk.LEFT, padx=2)
        self._sep(self.post_lock_frame)
        tk.Button(self.post_lock_frame, text="Undo", command=self._undo_node,
                  **self._btn(fg="#ff6b6b")).pack(side=tk.LEFT, padx=2)
        tk.Button(self.post_lock_frame, text="Clear All", command=self._clear_all,
                  **self._btn(fg="#ff6b6b")).pack(side=tk.LEFT, padx=2)

        right = tk.Frame(inner, bg=PANEL_BG)
        right.pack(side=tk.RIGHT)
        tk.Button(right, text="Export Panel", command=self._switch_to_export,
                  **self._btn(wide=True)).pack(side=tk.RIGHT, padx=(4, 0))
        self.net_var = tk.BooleanVar(value=True)
        tk.Checkbutton(right, text="Sample Net", variable=self.net_var,
                       bg=PANEL_BG, fg=DIM_CLR, selectcolor=BG,
                       activebackground=PANEL_BG, activeforeground=TEXT_CLR,
                       font=("Courier", 9), command=self._on_toggle_network
                       ).pack(side=tk.RIGHT, padx=8)

    def _build_main_area(self):
        self.main_frame = tk.Frame(self.root, bg=BG)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.main_frame, bg=BG, highlightthickness=0, cursor="arrow")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>",            self._on_click)
        self.canvas.bind("<Motion>",              self._on_motion)
        self.canvas.bind("<Button-2>",            self._on_pan_start)
        self.canvas.bind("<B2-Motion>",           self._on_pan_motion)
        self.canvas.bind("<ButtonRelease-2>",     self._on_pan_end)
        self.canvas.bind("<Alt-Button-1>",        self._on_pan_start)
        self.canvas.bind("<Alt-B1-Motion>",       self._on_pan_motion)
        self.canvas.bind("<Alt-ButtonRelease-1>", self._on_pan_end)
        self.canvas.bind("<Button-3>",            self._on_right_click)
        self.canvas.bind("<Leave>",               self._on_leave)
        self.canvas.bind("<Configure>",           lambda e: self.redraw())
        self.root.bind("<Escape>",                self._on_escape)

        if platform.system() == "Darwin":
            self.canvas.bind("<MouseWheel>", self._on_scroll_mac)
        else:
            self.canvas.bind("<MouseWheel>", self._on_scroll_win)
            self.canvas.bind("<Button-4>",   lambda e: self._do_scroll(1.08, e))
            self.canvas.bind("<Button-5>",   lambda e: self._do_scroll(0.92, e))

        # Right panel — always visible, two tabs
        self.right_panel = tk.Frame(self.main_frame, bg=PANEL_BG, width=350)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_panel.pack_propagate(False)

        style = ttk.Style()
        style.configure("Dark.TNotebook",      background=PANEL_BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",  background=BORDER_CLR, foreground=DIM_CLR,
                        font=("Courier", 9, "bold"), padding=[10, 4])
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", BG)])

        self.notebook = ttk.Notebook(self.right_panel, style="Dark.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.props_tab  = tk.Frame(self.notebook, bg=PANEL_BG)
        self.export_tab = tk.Frame(self.notebook, bg=PANEL_BG)
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
                    activeforeground="#fff", relief="flat", bd=0,
                    font=("Courier", 10, "bold"),
                    padx=12 if wide else 6, pady=2, cursor="hand2")

    def _sep(self, p):
        tk.Frame(p, width=1, height=22, bg=BORDER_CLR).pack(side=tk.LEFT, padx=6)

    def _hsep(self, parent=None):
        p = parent or self.props_tab
        tk.Frame(p, height=1, bg=BORDER_CLR).pack(fill=tk.X, padx=6, pady=4)

    def _field_label(self, text, parent=None):
        p = parent or self.props_tab
        tk.Label(p, text=text, bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 8), anchor="w").pack(fill=tk.X, padx=10, pady=(5, 1))

    @property
    def effective_grid_size(self):
        return INITIAL_GRID_SIZE * self.grid_zoom

    def screen_to_grid(self, sx, sy):
        gx, gy = (sx - self.pan_x) / self.global_zoom, (sy - self.pan_y) / self.global_zoom
        egs = self.effective_grid_size
        return {"col": round(gx/egs, 2), "row": round(gy/egs, 2),
                "px":  round(gx, 1),     "py":  round(gy, 1)}

    def world_to_screen(self, wx, wy):
        return wx * self.global_zoom + self.pan_x, wy * self.global_zoom + self.pan_y

    def _node_by_id(self, nid):
        for n in self.placed_nodes:
            if n["id"] == nid:
                return n
        return None

    def _edge_by_id(self, eid):
        for e in self.placed_edges:
            if e["id"] == eid:
                return e
        return None

    def _nearest_node(self, ex, ey, threshold=22):
        best_i, best_d = -1, float("inf")
        for i, nd in enumerate(self.placed_nodes):
            sx, sy = self.world_to_screen(nd["px"], nd["py"])
            d = math.hypot(ex - sx, ey - sy)
            if d < best_d:
                best_d, best_i = d, i
        if best_d < threshold * max(1.0, self.global_zoom) and best_i >= 0:
            return best_i, best_d
        return -1, float("inf")

    def _nearest_edge(self, ex, ey, threshold=10):
        best_i, best_d = -1, float("inf")
        for i, edge in enumerate(self.placed_edges):
            na, nb = self._node_by_id(edge["src"]), self._node_by_id(edge["dst"])
            if na and nb:
                ax, ay = self.world_to_screen(na["px"], na["py"])
                bx, by = self.world_to_screen(nb["px"], nb["py"])
                d = self._pt_seg(ex, ey, ax, ay, bx, by)
                if d < best_d:
                    best_d, best_i = d, i
        if best_d < threshold and best_i >= 0:
            return best_i, best_d
        return -1, float("inf")

    @staticmethod
    def _pt_seg(px, py, ax, ay, bx, by):
        dx, dy = bx-ax, by-ay
        if dx == dy == 0:
            return math.hypot(px-ax, py-ay)
        t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / (dx*dx+dy*dy)))
        return math.hypot(px-(ax+t*dx), py-(ay+t*dy))

    def _bind_scroll(self, widget):
        if platform.system() == "Darwin":
            widget.bind("<MouseWheel>",
                        lambda e: widget.yview_scroll(-1 if e.delta>0 else 1, "units"))
        else:
            widget.bind("<MouseWheel>",
                        lambda e: widget.yview_scroll(-1 if e.delta>0 else 1, "units"))
            widget.bind("<Button-4>", lambda e: widget.yview_scroll(-1, "units"))
            widget.bind("<Button-5>", lambda e: widget.yview_scroll(1,  "units"))

    def _deselect(self):
        self._sel_node_id = None
        self._sel_edge_id = None
        self._refresh_props()
        self.redraw()

    def _switch_to_export(self):
        self._refresh_export()
        self.notebook.select(1)

    def _switch_to_props(self):
        self.notebook.select(0)

    # ══════════════════════════════════════════════════════════════════════════
    # Properties Panel — dispatches to node or edge view
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_props(self):
        for w in self.props_tab.winfo_children():
            w.destroy()
        self._param_vars.clear()

        if self._sel_node_id is not None:
            nd = self._node_by_id(self._sel_node_id)
            if nd:
                self._build_node_props(nd)
                return
            self._sel_node_id = None

        if self._sel_edge_id is not None:
            edge = self._edge_by_id(self._sel_edge_id)
            if edge:
                self._build_edge_props(edge)
                return
            self._sel_edge_id = None

        # Nothing selected
        tk.Label(self.props_tab,
                 text="\n  Click a node or edge\n  to view / edit its\n  properties.",
                 bg=PANEL_BG, fg=DIM_CLR, font=("Courier", 10),
                 justify="left").pack(pady=50, padx=14, anchor="w")
        tk.Label(self.props_tab,
                 text="  Placing a new node opens\n  its properties automatically.",
                 bg=PANEL_BG, fg="#444455", font=("Courier", 9),
                 justify="left").pack(padx=14, anchor="w")

    # ── Node Properties ───────────────────────────────────────────────────────

    def _build_node_props(self, nd):
        color = PYWR_COLORS.get(nd["type"], NODE_CLR)

        # Coloured header bar
        hdr = tk.Frame(self.props_tab, bg=color)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"  NODE #{nd['id']}", bg=color, fg=BG,
                 font=("Courier", 11, "bold"), anchor="w", pady=6
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(hdr, text="✕", command=self._deselect,
                  bg=color, fg=BG, font=("Courier", 10, "bold"),
                  relief="flat", padx=8, cursor="hand2").pack(side=tk.RIGHT)

        tk.Label(self.props_tab,
                 text=f"  col={nd['col']}  row={nd['row']}",
                 bg=PANEL_BG, fg=DIM_CLR, font=("Courier", 8),
                 anchor="w").pack(fill=tk.X, pady=(4, 0))

        self._hsep()

        # Name
        self._field_label("Name")
        self._name_var = tk.StringVar(value=nd["name"])
        tk.Entry(self.props_tab, textvariable=self._name_var,
                 bg=ENTRY_BG, fg=TEXT_CLR, font=("Courier", 10),
                 relief="flat", insertbackground=TEXT_CLR
                 ).pack(fill=tk.X, padx=10, pady=(0, 4))
        self._name_var.trace_add("write", lambda *_: self._apply_node_name())

        # Type
        self._field_label("Type")
        self._type_var = tk.StringVar(value=nd["type"])
        ttk.Combobox(self.props_tab, textvariable=self._type_var,
                     values=PYWR_NODE_TYPES, state="readonly",
                     font=("Courier", 10)).pack(fill=tk.X, padx=10, pady=(0, 2))
        self._type_var.trace_add("write", lambda *_: self._apply_node_type())

        self._hsep()

        # Parameters header
        phdr = tk.Frame(self.props_tab, bg=PANEL_BG)
        phdr.pack(fill=tk.X, padx=10, pady=(2, 2))
        tk.Label(phdr, text="PARAMETERS", bg=PANEL_BG, fg=NODE_CLR,
                 font=("Courier", 9, "bold")).pack(side=tk.LEFT)
        tk.Button(phdr, text="↺ defaults", command=self._load_defaults,
                  bg=PANEL_BG, fg=DIM_CLR, font=("Courier", 8),
                  relief="flat", padx=4, cursor="hand2").pack(side=tk.RIGHT)

        # Scrollable param rows
        outer = tk.Frame(self.props_tab, bg=PANEL_BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=10)
        pcanvas = tk.Canvas(outer, bg=PANEL_BG, highlightthickness=0, height=200)
        psb = ttk.Scrollbar(outer, orient="vertical", command=pcanvas.yview)
        self._params_inner = tk.Frame(pcanvas, bg=PANEL_BG)
        self._params_inner.bind(
            "<Configure>",
            lambda e: pcanvas.configure(scrollregion=pcanvas.bbox("all")))
        pcanvas.create_window((0, 0), window=self._params_inner, anchor="nw")
        pcanvas.configure(yscrollcommand=psb.set)
        pcanvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        psb.pack(side=tk.RIGHT, fill=tk.Y)
        self._bind_scroll(pcanvas)
        self._rebuild_param_rows(nd)

        self._hsep()

        # Add custom param
        tk.Label(self.props_tab, text="Add parameter",
                 bg=PANEL_BG, fg=DIM_CLR, font=("Courier", 8), anchor="w"
                 ).pack(fill=tk.X, padx=10)
        add_row = tk.Frame(self.props_tab, bg=PANEL_BG)
        add_row.pack(fill=tk.X, padx=10, pady=(2, 4))
        self._new_key_var = tk.StringVar()
        self._new_val_var = tk.StringVar()
        tk.Entry(add_row, textvariable=self._new_key_var, bg=ENTRY_BG, fg=TEXT_CLR,
                 font=("Courier", 9), relief="flat", width=11,
                 insertbackground=TEXT_CLR).pack(side=tk.LEFT, padx=(0, 2))
        tk.Entry(add_row, textvariable=self._new_val_var, bg=ENTRY_BG, fg=NODE_CLR,
                 font=("Courier", 9), relief="flat", width=8,
                 insertbackground=NODE_CLR).pack(side=tk.LEFT, padx=(0, 2))
        tk.Button(add_row, text="+ Add", command=self._add_custom_param,
                  bg=ACCENT, fg=BG, font=("Courier", 9, "bold"), relief="flat",
                  padx=4, pady=1, cursor="hand2").pack(side=tk.LEFT)

        self._hsep()

        # Split node
        split_row = tk.Frame(self.props_tab, bg=PANEL_BG)
        split_row.pack(fill=tk.X, padx=10, pady=(0, 8))
        tk.Label(split_row, text="Split node into:", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 8)).pack(side=tk.LEFT)
        for count in (2, 3):
            tk.Button(split_row, text=f"×{count}",
                      command=lambda c=count: self._split_node(self._sel_node_id, c),
                      bg="#2a2a35", fg=EDGE_CLR, font=("Courier", 9, "bold"),
                      relief="flat", padx=6, pady=1, cursor="hand2"
                      ).pack(side=tk.LEFT, padx=2)

    def _rebuild_param_rows(self, nd):
        for w in self._params_inner.winfo_children():
            w.destroy()
        self._param_vars.clear()

        if not nd.get("params"):
            tk.Label(self._params_inner,
                     text="  No parameters.\n  Click ↺ defaults or add below.",
                     bg=PANEL_BG, fg="#444455", font=("Courier", 8),
                     justify="left").pack(anchor="w", pady=6)
            return

        for key, val in nd["params"].items():
            row = tk.Frame(self._params_inner, bg=PANEL_BG)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=key, bg=PANEL_BG, fg=TEXT_CLR,
                     font=("Courier", 9), width=15, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=str(val))
            self._param_vars[key] = var
            tk.Entry(row, textvariable=var, bg=ENTRY_BG, fg=NODE_CLR,
                     font=("Courier", 9), relief="flat", width=9,
                     insertbackground=NODE_CLR).pack(side=tk.LEFT, fill=tk.X,
                                                     expand=True, padx=2)
            def on_change(*_, k=key, v=var):
                n = self._node_by_id(self._sel_node_id)
                if n:
                    n["params"][k] = v.get()
            var.trace_add("write", on_change)

            def remove(k=key):
                n = self._node_by_id(self._sel_node_id)
                if n and k in n.get("params", {}):
                    del n["params"][k]
                self._rebuild_param_rows(n)
            tk.Button(row, text="✕", command=remove,
                      bg=PANEL_BG, fg="#554444", font=("Courier", 8),
                      relief="flat", padx=2, cursor="hand2").pack(side=tk.LEFT)

    def _apply_node_name(self):
        nd = self._node_by_id(self._sel_node_id)
        if nd and self._name_var:
            nd["name"] = self._name_var.get()
            self.redraw()

    def _apply_node_type(self):
        nd = self._node_by_id(self._sel_node_id)
        if nd and self._type_var:
            nd["type"] = self._type_var.get()
            self._new_node_type.set(nd["type"])
            self.redraw()

    def _load_defaults(self):
        nd = self._node_by_id(self._sel_node_id)
        if not nd:
            return
        defaults = TYPE_DEFAULTS.get(nd["type"], {})
        params   = nd.setdefault("params", {})
        for k, v in defaults.items():
            if k not in params:
                params[k] = v
        self._rebuild_param_rows(nd)

    def _add_custom_param(self):
        key = (self._new_key_var.get() if self._new_key_var else "").strip()
        val = (self._new_val_var.get() if self._new_val_var else "").strip()
        if not key:
            return
        nd = self._node_by_id(self._sel_node_id)
        if nd is None:
            return
        nd.setdefault("params", {})[key] = val
        self._new_key_var.set("")
        self._new_val_var.set("")
        self._rebuild_param_rows(nd)

    # ── Edge Properties ───────────────────────────────────────────────────────

    def _build_edge_props(self, edge):
        na = self._node_by_id(edge["src"])
        nb = self._node_by_id(edge["dst"])
        src_label = na["name"] if na else f"#{edge['src']}"
        dst_label = nb["name"] if nb else f"#{edge['dst']}"

        hdr = tk.Frame(self.props_tab, bg=EDGE_CLR)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text=f"  EDGE #{edge['id']}", bg=EDGE_CLR, fg=BG,
                 font=("Courier", 11, "bold"), anchor="w", pady=6
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(hdr, text="✕", command=self._deselect,
                  bg=EDGE_CLR, fg=BG, font=("Courier", 10, "bold"),
                  relief="flat", padx=8, cursor="hand2").pack(side=tk.RIGHT)

        self._hsep()

        # From / To (read-only info)
        for label, val in [("From", src_label), ("To", dst_label)]:
            row = tk.Frame(self.props_tab, bg=PANEL_BG)
            row.pack(fill=tk.X, padx=10, pady=1)
            tk.Label(row, text=label, bg=PANEL_BG, fg=DIM_CLR,
                     font=("Courier", 9), width=6, anchor="w").pack(side=tk.LEFT)
            tk.Label(row, text=val, bg=PANEL_BG, fg=TEXT_CLR,
                     font=("Courier", 10), anchor="w").pack(side=tk.LEFT)

        self._hsep()

        # Name
        self._field_label("Edge Name")
        self._ename_var = tk.StringVar(value=edge["name"])
        tk.Entry(self.props_tab, textvariable=self._ename_var,
                 bg=ENTRY_BG, fg=EDGE_CLR, font=("Courier", 10),
                 relief="flat", insertbackground=EDGE_CLR
                 ).pack(fill=tk.X, padx=10, pady=(0, 4))
        self._ename_var.trace_add("write", lambda *_: self._apply_edge_name())

        self._hsep()

        # Delete button
        tk.Button(self.props_tab, text="Delete This Edge",
                  command=self._delete_selected_edge,
                  bg="#2a2a35", fg="#ff6b6b", font=("Courier", 9, "bold"),
                  relief="flat", padx=8, pady=4, cursor="hand2"
                  ).pack(padx=10, pady=4, anchor="w")

    def _apply_edge_name(self):
        edge = self._edge_by_id(self._sel_edge_id)
        if edge and self._ename_var:
            edge["name"] = self._ename_var.get()
            self.redraw()

    def _delete_selected_edge(self):
        self.placed_edges = [e for e in self.placed_edges if e["id"] != self._sel_edge_id]
        self._sel_edge_id = None
        self._refresh_props()
        self._refresh_export()
        self.redraw()

    # ── Node Split ────────────────────────────────────────────────────────────

    def _split_node(self, node_id, count):
        """
        Split a node into `count` sibling nodes.
        The original keeps all its existing connections.
        New nodes are placed offset from the original, pre-named _b / _c.
        """
        nd = self._node_by_id(node_id)
        if nd is None:
            return

        original_name = nd["name"]
        # Rename the original to _a
        nd["name"] = f"{original_name}_a"

        # World-space offsets per sibling (in pixels)
        egs = self.effective_grid_size
        offsets = [(egs, 0), (egs * 2, 0), (0, egs)]   # _b, _c

        for i in range(1, count):
            dx, dy = offsets[i - 1]
            new_nd = {
                "id":     self.node_counter,
                "name":   f"{original_name}_{chr(97 + i)}",   # _b, _c
                "type":   nd["type"],
                "px":     round(nd["px"] + dx, 1),
                "py":     round(nd["py"] + dy, 1),
                "col":    round((nd["px"] + dx) / egs, 2),
                "row":    round((nd["py"] + dy) / egs, 2),
                "params": dict(nd.get("params", {})),
            }
            self.placed_nodes.append(new_nd)
            self.node_counter += 1

        # Select the renamed original so the panel updates
        self._sel_node_id = nd["id"]
        self._refresh_props()
        self._refresh_export()
        self.redraw()

    # ══════════════════════════════════════════════════════════════════════════
    # Image Loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_image(self):
        if not PIL_AVAILABLE:
            messagebox.showwarning("Pillow Not Installed", "pip install pillow")
            return
        path = filedialog.askopenfilename(
            title="Open Background Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("All", "*.*")])
        if not path:
            return
        try:
            self._bg_image = Image.open(path)
            self.net_var.set(False); self.show_network = False
            self.redraw()
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image:\n{e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Drawing
    # ══════════════════════════════════════════════════════════════════════════

    def redraw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
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

        # Grid
        def blend(op):
            br,bg2,bb, dr,dg,db = 0x7c,0x7c,0xff, 0x0e,0x0e,0x12
            return (f"#{int(dr+(br-dr)*op):02x}"
                    f"{int(dg+(bg2-dg)*op):02x}"
                    f"{int(db+(bb-db)*op):02x}")

        if step >= 4:
            ox, oy = self.pan_x % step, self.pan_y % step
            clr = blend(self.grid_opacity * 0.35)
            x = ox
            while x < w: c.create_line(x,0,x,h,fill=clr,width=1); x+=step
            y = oy
            while y < h: c.create_line(0,y,w,y,fill=clr,width=1); y+=step

        if major_step >= 8:
            ox, oy = self.pan_x % major_step, self.pan_y % major_step
            clr = blend(self.grid_opacity * 0.70)
            lbl = blend(self.grid_opacity * 0.50)
            x = ox
            while x < w:
                c.create_line(x,0,x,h,fill=clr,width=1)
                c.create_text(x,10,text=str(round((x-self.pan_x)/step)),
                              fill=lbl,font=("Courier",8),anchor="n")
                x += major_step
            y = oy
            while y < h:
                c.create_line(0,y,w,y,fill=clr,width=1)
                c.create_text(8,y,text=str(round((y-self.pan_y)/step)),
                              fill=lbl,font=("Courier",8),anchor="w")
                y += major_step

        # Sample network
        if self.show_network and not self._bg_image:
            for a_id, b_id in SAMPLE_EDGES:
                a, b = NODE_MAP[a_id], NODE_MAP[b_id]
                ax,ay = self.world_to_screen(a["x"],a["y"])
                bx,by = self.world_to_screen(b["x"],b["y"])
                c.create_line(ax,ay,bx,by,fill="#444444",width=1,dash=(6,3))
            for n in SAMPLE_NODES:
                sx,sy = self.world_to_screen(n["x"],n["y"])
                ro,ri = 16*gz,9*gz
                c.create_oval(sx-ro,sy-ro,sx+ro,sy+ro,fill="",outline=n["color"],width=1)
                c.create_oval(sx-ri,sy-ri,sx+ri,sy+ri,fill=n["color"],outline="")
                c.create_text(sx,sy,text=n["id"],fill="white",
                              font=("Courier",max(8,int(10*gz)),"bold"))

        # Placed edges
        for edge in self.placed_edges:
            na, nb = self._node_by_id(edge["src"]), self._node_by_id(edge["dst"])
            if not (na and nb):
                continue
            ax,ay = self.world_to_screen(na["px"],na["py"])
            bx,by = self.world_to_screen(nb["px"],nb["py"])
            is_sel_edge = (edge["id"] == self._sel_edge_id)
            ecolor  = SEL_CLR if is_sel_edge else EDGE_CLR
            ewidth  = max(1, int(3*gz)) if is_sel_edge else max(1, int(2*gz))
            ashape  = (max(6,10*gz), max(8,12*gz), max(3,4*gz))
            c.create_line(ax,ay,bx,by,fill=ecolor,width=ewidth,
                          arrow=tk.LAST,arrowshape=ashape)
            # Edge name label (centred on the line)
            mx, my = (ax+bx)/2, (ay+by)/2
            c.create_text(mx, my-10, text=edge["name"],
                          fill=ecolor, font=("Courier", max(7, int(8*gz)),
                                             "bold" if is_sel_edge else "normal"))

        # Placed nodes
        for nd in self.placed_nodes:
            sx,sy  = self.world_to_screen(nd["px"],nd["py"])
            color  = PYWR_COLORS.get(nd["type"], NODE_CLR)
            is_sel = (nd["id"] == self._sel_node_id)
            is_src = (self.edge_mode and self._edge_src == nd["id"])
            ro, ri = 14*gz, 5*gz

            if is_sel:
                c.create_oval(sx-ro-5,sy-ro-5,sx+ro+5,sy+ro+5,
                              outline=SEL_CLR,width=2,fill="",dash=(4,3))
            if is_src:
                c.create_oval(sx-ro-5,sy-ro-5,sx+ro+5,sy+ro+5,
                              outline=SEL_CLR,width=3,fill="")

            c.create_oval(sx-ro,sy-ro,sx+ro,sy+ro,
                          outline=color,width=3 if is_sel else 2,fill=BG)
            c.create_oval(sx-ri,sy-ri,sx+ri,sy+ri,fill=color,outline="")

            n_p   = len(nd.get("params", {}))
            phint = f" +{n_p}p" if n_p else ""
            label = f"{nd['name']} [{nd['type'][:3]}]{phint}  ({nd['col']},{nd['row']})"
            c.create_text(sx+17*gz, sy-12*gz, text=label,
                          fill=SEL_CLR if is_sel else color,
                          font=("Courier", max(7, int(9*gz))), anchor="w")

        # Hover crosshair
        if self.grid_locked and self._hover_coord and not self.edge_mode:
            hx,hy = self._hover_screen
            c.create_line(hx,0,hx,h,fill=NODE_CLR,width=1,dash=(3,5))
            c.create_line(0,hy,w,hy,fill=NODE_CLR,width=1,dash=(3,5))
            coord = self._hover_coord
            txt   = f"col:{coord['col']}  row:{coord['row']}"
            c.create_rectangle(hx+14,hy-28,hx+14+len(txt)*7+12,hy-8,
                               fill=BG,outline=ACCENT)
            c.create_text(hx+20,hy-18,text=txt,fill=NODE_CLR,
                          font=("Courier",9),anchor="w")

        # Calibration hint
        if not self.grid_locked:
            hint = "Scroll to calibrate grid scale  →  then click  Lock Grid"
            tw, cx = len(hint)*7, w//2
            c.create_rectangle(cx-tw//2-12,14,cx+tw//2+12,40,fill=BG,outline=ACCENT)
            c.create_text(cx,27,text=hint,fill=ACCENT,font=("Courier",10))

        mode  = "View Zoom" if self.grid_locked else "Grid Scale"
        emode = "  │  EDGE MODE: click source → target  (Esc=cancel)" if self.edge_mode else ""
        sel   = ""
        if self._sel_node_id:
            nd = self._node_by_id(self._sel_node_id)
            if nd: sel = f"  │  Node: {nd['name']}"
        elif self._sel_edge_id:
            e = self._edge_by_id(self._sel_edge_id)
            if e: sel = f"  │  Edge: {e['name']}"
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
            self._handle_edge_click(event); return

        # 1. Check for nearby node
        idx, d_node = self._nearest_node(event.x, event.y, threshold=22)
        if idx >= 0:
            self._sel_node_id = self.placed_nodes[idx]["id"]
            self._sel_edge_id = None
            self._refresh_props(); self._switch_to_props()
            self.redraw(); return

        # 2. Check for nearby edge
        eidx, d_edge = self._nearest_edge(event.x, event.y, threshold=10)
        if eidx >= 0:
            self._sel_edge_id = self.placed_edges[eidx]["id"]
            self._sel_node_id = None
            self._refresh_props(); self._switch_to_props()
            self.redraw(); return

        # 3. Empty canvas — place new node
        self._sel_node_id = None; self._sel_edge_id = None
        self._place_node(event)
        self._sel_node_id = self.placed_nodes[-1]["id"]
        self._refresh_props(); self._switch_to_props()
        self.redraw()

    def _place_node(self, event):
        coord = self.screen_to_grid(event.x, event.y)
        ntype = self._new_node_type.get()
        self.placed_nodes.append({
            "id":     self.node_counter,
            "name":   f"N{self.node_counter}",
            "type":   ntype,
            "col":    coord["col"],
            "row":    coord["row"],
            "px":     coord["px"],
            "py":     coord["py"],
            "params": dict(TYPE_DEFAULTS.get(ntype, {})),
        })
        self.node_counter += 1
        self._refresh_export()

    def _handle_edge_click(self, event):
        idx, _ = self._nearest_node(event.x, event.y)
        if idx < 0:
            return
        cid = self.placed_nodes[idx]["id"]
        if self._edge_src is None:
            self._edge_src = cid
        else:
            if self._edge_src != cid:
                # Check not duplicate
                existing = {(e["src"], e["dst"]) for e in self.placed_edges}
                if (self._edge_src, cid) not in existing and (cid, self._edge_src) not in existing:
                    self.placed_edges.append({
                        "id":  self.edge_counter,
                        "src": self._edge_src,
                        "dst": cid,
                        "name": f"E{self.edge_counter}",
                    })
                    self.edge_counter += 1
                    self._refresh_export()
            self._edge_src = None
        self.redraw()

    def _on_right_click(self, event):
        idx, d_node = self._nearest_node(event.x, event.y, threshold=30)
        eidx, d_edge = self._nearest_edge(event.x, event.y, threshold=12)

        if idx >= 0 and d_node * self.global_zoom <= d_edge:
            removed_id = self.placed_nodes.pop(idx)["id"]
            self.placed_edges = [e for e in self.placed_edges
                                 if e["src"] != removed_id and e["dst"] != removed_id]
            if self._edge_src == removed_id: self._edge_src = None
            if self._sel_node_id == removed_id:
                self._sel_node_id = None; self._refresh_props()
        elif eidx >= 0:
            removed_eid = self.placed_edges.pop(eidx)["id"]
            if self._sel_edge_id == removed_eid:
                self._sel_edge_id = None; self._refresh_props()

        self.redraw(); self._refresh_export()

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
        self._hover_coord = None; self.redraw()

    def _on_escape(self, event):
        if self.edge_mode and self._edge_src is not None:
            self._edge_src = None
        else:
            self._deselect()
        self.redraw()

    def _on_pan_start(self, event):
        self._pan_dragging = True
        self._pan_start_x, self._pan_start_y = event.x, event.y
        self._pan_start_ox, self._pan_start_oy = self.pan_x, self.pan_y
        self.canvas.config(cursor="fleur")

    def _on_pan_motion(self, event):
        if not self._pan_dragging: return
        self.pan_x = self._pan_start_ox + (event.x - self._pan_start_x)
        self.pan_y = self._pan_start_oy + (event.y - self._pan_start_y)
        self.redraw()

    def _on_pan_end(self, event):
        self._pan_dragging = False
        self.canvas.config(cursor="crosshair" if self.grid_locked else "arrow")

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
            self.pan_x = event.x - scale*(event.x - self.pan_x)
            self.pan_y = event.y - scale*(event.y - self.pan_y)
            self.global_zoom_lbl.config(text=f"{self.global_zoom:.2f}×")
        self.redraw()

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
        self.global_zoom = 1.0; self.pan_x = self.pan_y = 0.0
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
        self.edge_mode = not self.edge_mode; self._edge_src = None
        self.edge_btn.config(bg=EDGE_CLR if self.edge_mode else "#2a2a35",
                             fg=BG      if self.edge_mode else TEXT_CLR)
        self.redraw()

    def _undo_node(self):
        if not self.placed_nodes: return
        removed_id = self.placed_nodes.pop()["id"]
        self.placed_edges = [e for e in self.placed_edges
                             if e["src"] != removed_id and e["dst"] != removed_id]
        if self._sel_node_id == removed_id:
            self._sel_node_id = None; self._refresh_props()
        self.redraw(); self._refresh_export()

    def _clear_all(self):
        self.placed_nodes.clear(); self.placed_edges.clear()
        self.node_counter = 1; self.edge_counter = 1
        self._edge_src = None; self._sel_node_id = None; self._sel_edge_id = None
        self._refresh_props(); self.redraw(); self._refresh_export()

    def _on_opacity(self, val):
        self.grid_opacity = float(val)
        self.opacity_lbl.config(text=f"{int(self.grid_opacity*100)}%"); self.redraw()

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
                 ).pack(fill=tk.X, padx=10, pady=(0, 6))

        if not self.placed_nodes:
            tk.Label(self.export_tab, text="Place nodes first.",
                     bg=PANEL_BG, fg="#555555", font=("Courier", 9)).pack(pady=30)
            return

        # Node table
        hdr = tk.Frame(self.export_tab, bg="#1e1e28")
        hdr.pack(fill=tk.X, padx=10)
        for cn, cw in [("#",3),("Name",8),("Type",10),("Col",5),("Row",5),("P",2)]:
            tk.Label(hdr, text=cn, bg="#1e1e28", fg=ACCENT,
                     font=("Courier", 9, "bold"), width=cw, anchor="w"
                     ).pack(side=tk.LEFT, padx=2, pady=3)

        rc = tk.Canvas(self.export_tab, bg=PANEL_BG, highlightthickness=0, height=120)
        sb = ttk.Scrollbar(self.export_tab, orient="vertical", command=rc.yview)
        sf = tk.Frame(rc, bg=PANEL_BG)
        sf.bind("<Configure>", lambda e: rc.configure(scrollregion=rc.bbox("all")))
        rc.create_window((0,0), window=sf, anchor="nw")
        rc.configure(yscrollcommand=sb.set)
        for nd in self.placed_nodes:
            rf = tk.Frame(sf, bg=PANEL_BG); rf.pack(fill=tk.X)
            color = PYWR_COLORS.get(nd["type"], NODE_CLR)
            for val, cw in [(nd["id"],3),(nd["name"],8),(nd["type"],10),
                             (nd["col"],5),(nd["row"],5),(len(nd.get("params",{})),2)]:
                tk.Label(rf, text=str(val), bg=PANEL_BG, fg=color,
                         font=("Courier",9), width=cw, anchor="w"
                         ).pack(side=tk.LEFT, padx=2, pady=1)
        rc.pack(fill=tk.X, padx=10); sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Edge table
        if self.placed_edges:
            tk.Label(self.export_tab, text="EDGES", bg=PANEL_BG, fg=EDGE_CLR,
                     font=("Courier", 9, "bold"), anchor="w"
                     ).pack(fill=tk.X, padx=10, pady=(6,2))
            ehdr = tk.Frame(self.export_tab, bg="#1e1e28")
            ehdr.pack(fill=tk.X, padx=10)
            for cn, cw in [("Name",10),("From",9),("To",9)]:
                tk.Label(ehdr, text=cn, bg="#1e1e28", fg=ACCENT,
                         font=("Courier",9,"bold"), width=cw, anchor="w"
                         ).pack(side=tk.LEFT, padx=2, pady=2)
            for edge in self.placed_edges:
                na = self._node_by_id(edge["src"]); nb = self._node_by_id(edge["dst"])
                ef = tk.Frame(self.export_tab, bg=PANEL_BG); ef.pack(fill=tk.X, padx=10)
                for val, cw in [(edge["name"],10),
                                 (na["name"] if na else "?", 9),
                                 (nb["name"] if nb else "?", 9)]:
                    tk.Label(ef, text=str(val), bg=PANEL_BG, fg=EDGE_CLR,
                             font=("Courier",9), width=cw, anchor="w"
                             ).pack(side=tk.LEFT, padx=2, pady=1)

        # PyWR JSON preview
        tk.Label(self.export_tab, text="PyWR JSON preview", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier",9,"bold"), anchor="w"
                 ).pack(fill=tk.X, padx=10, pady=(8,2))
        txt = tk.Text(self.export_tab, bg=BG, fg=TEXT_CLR, font=("Courier",9),
                      height=7, wrap=tk.WORD, relief="flat", bd=0, padx=8, pady=6)
        txt.pack(fill=tk.X, padx=10)
        txt.insert("1.0", json.dumps(self._get_pywr_json(), indent=2))
        txt.config(state="disabled")

        # Buttons
        bf = tk.Frame(self.export_tab, bg=PANEL_BG)
        bf.pack(fill=tk.X, padx=10, pady=8)
        for label, cmd, bg, fg in [
            ("Copy",      self._copy_json,     ACCENT,    BG),
            ("JSON",      self._save_json,      "#339af0", "white"),
            ("CSV",       self._save_csv,       "#51cf66", BG),
            ("PyWR JSON", self._save_pywr_json, "#fcc419", BG),
        ]:
            tk.Button(bf, text=label, command=cmd, bg=bg, fg=fg,
                      font=("Courier",9,"bold"), relief="flat",
                      padx=4, pady=5, cursor="hand2"
                      ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

    # ── Export builders ───────────────────────────────────────────────────────

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

        edges = []
        for edge in self.placed_edges:
            na, nb = self._node_by_id(edge["src"]), self._node_by_id(edge["dst"])
            if na and nb:
                edges.append([na["name"], nb["name"]])

        return {
            "metadata": {"title": "Graph Overlay Model",
                         "description": "Generated by Graph Overlay Tool — PyWR Edition",
                         "minimum_version": "0.1"},
            "timestepper": {"start":"2000-01-01","end":"2000-12-31","timestep":1},
            "nodes": nodes, "edges": edges,
            "parameters": {}, "recorders": {},
        }

    def _copy_json(self):
        data = [{"id":n["id"],"name":n["name"],"type":n["type"],
                 "grid":{"col":n["col"],"row":n["row"]},
                 "pixel":{"x":n["px"],"y":n["py"]},
                 "params":n.get("params",{})} for n in self.placed_nodes]
        self.root.clipboard_clear()
        self.root.clipboard_append(json.dumps(data, indent=2))
        messagebox.showinfo("Copied", "Copied to clipboard!")

    def _save_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("JSON","*.json"),("All","*.*")])
        if not path: return
        data = [{"id":n["id"],"name":n["name"],"type":n["type"],
                 "grid":{"col":n["col"],"row":n["row"]},
                 "pixel":{"x":n["px"],"y":n["py"]},
                 "params":n.get("params",{})} for n in self.placed_nodes]
        edges = [{"name":e["name"],"src":self._node_by_id(e["src"])["name"],
                  "dst":self._node_by_id(e["dst"])["name"]}
                 for e in self.placed_edges
                 if self._node_by_id(e["src"]) and self._node_by_id(e["dst"])]
        with open(path,"w") as f:
            json.dump({"nodes":data,"edges":edges}, f, indent=2)
        messagebox.showinfo("Saved", f"Saved:\n{path}")

    def _save_csv(self):
        """Nodes CSV. Each unique parameter key becomes its own column."""
        path = filedialog.asksaveasfilename(defaultextension=".csv",
            initialfile="nodes", filetypes=[("CSV","*.csv"),("All","*.*")])
        if not path: return

        all_param_keys: list[str] = []
        for n in self.placed_nodes:
            for k in n.get("params", {}):
                if k not in all_param_keys:
                    all_param_keys.append(k)

        base = ["id","name","type","col","row","px","py"]
        with open(path,"w",newline="") as f:
            w = csv.DictWriter(f, fieldnames=base+all_param_keys, extrasaction="ignore")
            w.writeheader()
            for n in self.placed_nodes:
                row = {k: n[k] for k in base}
                row.update(n.get("params", {}))
                w.writerow(row)

        # Also write edges CSV alongside
        epath = path.replace(".csv","_edges.csv")
        with open(epath,"w",newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id","name","src","dst"])
            w.writeheader()
            for e in self.placed_edges:
                na, nb = self._node_by_id(e["src"]), self._node_by_id(e["dst"])
                w.writerow({"id":e["id"],"name":e["name"],
                            "src":na["name"] if na else e["src"],
                            "dst":nb["name"] if nb else e["dst"]})
        messagebox.showinfo("Saved", f"Nodes → {path}\nEdges → {epath}")

    def _save_pywr_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
            initialfile="pywr_model", filetypes=[("JSON","*.json"),("All","*.*")])
        if path:
            with open(path,"w") as f:
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
