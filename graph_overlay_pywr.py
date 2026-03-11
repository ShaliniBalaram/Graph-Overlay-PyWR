#!/usr/bin/env python3
"""
Graph Overlay Tool — PyWR Edition
==================================
A cross-platform desktop app for overlaying a transparent, zoomable
graph-paper grid on a network diagram, placing typed nodes, drawing
directed edges, and exporting for PyWR water resource models.

Workflow:
  Phase 1 – Load an image (optional) and calibrate grid scale with scroll wheel.
  Phase 2 – Lock the grid, select a node type, click to place nodes,
            draw edges, rename nodes by double-clicking, then export.

Controls:
  Scroll Wheel        → Grid zoom (before lock) / View zoom (after lock)
  Left Click          → Place node  /  Select node in edge mode
  Double-Click        → Rename node
  Middle-Drag         → Pan
  Alt+Drag            → Pan (alternative — no middle button)
  Right-Click         → Remove nearest node or edge
  Escape              → Cancel edge selection
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import json
import csv
import math
import platform
import sys
import os

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

# PyWR node types and their display colors
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
    """Main application — PyWR Edition."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Graph Overlay Tool — PyWR Edition")
        self.root.configure(bg=BG)
        self.root.geometry("1200x780")
        self.root.minsize(900, 550)

        # ── State ──────────────────────────────────────────────────────────
        self.grid_zoom    = 1.0
        self.global_zoom  = 1.0
        self.grid_locked  = False
        self.pan_x        = 0.0
        self.pan_y        = 0.0
        self.grid_opacity = 0.45
        self.show_network = True

        self.placed_nodes: list[dict]  = []
        self.placed_edges: list[tuple] = []   # list of (id_a, id_b)
        self.node_counter = 1

        self.edge_mode = False    # are we in edge-drawing mode?
        self._edge_src = None     # id of first selected node in edge mode

        # Background image
        self._bg_image = None     # PIL Image
        self._bg_photo = None     # ImageTk (must be kept alive)

        # Pan drag
        self._pan_dragging = False
        self._pan_start_x  = 0
        self._pan_start_y  = 0
        self._pan_start_ox = 0.0
        self._pan_start_oy = 0.0

        # Hover crosshair
        self._hover_coord  = None
        self._hover_screen = (0, 0)

        self.export_visible = False

        # Current node type for new placements
        self._node_type_var = tk.StringVar(value="river")

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
                  **self._btn_opts()).pack(side=tk.LEFT, padx=2)

        self._sep(inner)

        # Grid scale controls
        self.grid_frame = tk.Frame(inner, bg=PANEL_BG)
        self.grid_frame.pack(side=tk.LEFT, padx=4)
        tk.Label(self.grid_frame, text="Grid Scale", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(self.grid_frame, text="−", command=self._grid_zoom_out,
                  **self._btn_opts()).pack(side=tk.LEFT)
        self.grid_zoom_lbl = tk.Label(self.grid_frame, text="1.00×", width=6,
                                      bg=PANEL_BG, fg=TEXT_CLR, font=("Courier", 10))
        self.grid_zoom_lbl.pack(side=tk.LEFT)
        tk.Button(self.grid_frame, text="+", command=self._grid_zoom_in,
                  **self._btn_opts()).pack(side=tk.LEFT)

        self._sep(inner)

        # Opacity slider
        tk.Label(inner, text="Opacity", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(4, 4))
        self.opacity_var = tk.DoubleVar(value=self.grid_opacity)
        ttk.Scale(inner, from_=0.05, to=1.0, variable=self.opacity_var,
                  length=80, command=self._on_opacity).pack(side=tk.LEFT)
        self.opacity_lbl = tk.Label(inner, text="45%", width=4, bg=PANEL_BG,
                                    fg=DIM_CLR, font=("Courier", 9))
        self.opacity_lbl.pack(side=tk.LEFT)

        self._sep(inner)

        # Lock grid button
        self.lock_btn = tk.Button(inner, text="🔓 Lock Grid",
                                  command=self._toggle_lock, **self._btn_opts(wide=True))
        self.lock_btn.pack(side=tk.LEFT, padx=4)

        # ── Post-lock controls (hidden until grid is locked) ──
        self.post_lock_frame = tk.Frame(inner, bg=PANEL_BG)

        self._sep(self.post_lock_frame)
        tk.Label(self.post_lock_frame, text="View Zoom", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(4, 4))
        tk.Button(self.post_lock_frame, text="−", command=self._global_zoom_out,
                  **self._btn_opts()).pack(side=tk.LEFT)
        self.global_zoom_lbl = tk.Label(self.post_lock_frame, text="1.00×", width=6,
                                        bg=PANEL_BG, fg=TEXT_CLR, font=("Courier", 10))
        self.global_zoom_lbl.pack(side=tk.LEFT)
        tk.Button(self.post_lock_frame, text="+", command=self._global_zoom_in,
                  **self._btn_opts()).pack(side=tk.LEFT)
        tk.Button(self.post_lock_frame, text="Reset", command=self._reset_view,
                  **self._btn_opts()).pack(side=tk.LEFT, padx=(4, 0))

        self._sep(self.post_lock_frame)

        # Node type dropdown
        tk.Label(self.post_lock_frame, text="Node Type", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9)).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Combobox(self.post_lock_frame, textvariable=self._node_type_var,
                     values=PYWR_NODE_TYPES, state="readonly", width=12,
                     font=("Courier", 9)).pack(side=tk.LEFT)

        self._sep(self.post_lock_frame)

        # Edge mode toggle
        self.edge_btn = tk.Button(self.post_lock_frame, text="Draw Edge",
                                  command=self._toggle_edge_mode, **self._btn_opts())
        self.edge_btn.pack(side=tk.LEFT, padx=2)

        self._sep(self.post_lock_frame)

        tk.Button(self.post_lock_frame, text="Undo", command=self._undo_node,
                  **self._btn_opts(fg="#ff6b6b")).pack(side=tk.LEFT, padx=2)
        tk.Button(self.post_lock_frame, text="Clear", command=self._clear_nodes,
                  **self._btn_opts(fg="#ff6b6b")).pack(side=tk.LEFT, padx=2)

        # Right-side controls
        right = tk.Frame(inner, bg=PANEL_BG)
        right.pack(side=tk.RIGHT)

        self.export_btn = tk.Button(right, text="Export Positions",
                                    command=self._toggle_export, **self._btn_opts(wide=True))
        self.export_btn.pack(side=tk.RIGHT, padx=(4, 0))

        self.net_var = tk.BooleanVar(value=True)
        tk.Checkbutton(right, text="Sample Network", variable=self.net_var,
                       bg=PANEL_BG, fg=DIM_CLR, selectcolor=BG,
                       activebackground=PANEL_BG, activeforeground=TEXT_CLR,
                       font=("Courier", 9), command=self._on_toggle_network
                       ).pack(side=tk.RIGHT, padx=8)

    def _build_main_area(self):
        self.main_frame = tk.Frame(self.root, bg=BG)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.main_frame, bg=BG, highlightthickness=0, cursor="arrow")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Event bindings
        self.canvas.bind("<Button-1>",          self._on_click)
        self.canvas.bind("<Double-Button-1>",   self._on_double_click)
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

        self.export_panel = tk.Frame(self.main_frame, bg=PANEL_BG, width=330)
        self.export_text  = None

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
    def _btn_opts(fg=TEXT_CLR, wide=False):
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
        return {
            "col": round(gx / egs, 2),
            "row": round(gy / egs, 2),
            "px":  round(gx, 1),
            "py":  round(gy, 1),
        }

    def world_to_screen(self, wx, wy):
        return (wx * self.global_zoom + self.pan_x,
                wy * self.global_zoom + self.pan_y)

    def _node_by_id(self, node_id):
        for n in self.placed_nodes:
            if n["id"] == node_id:
                return n
        return None

    def _nearest_placed_node(self, ex, ey, threshold=30):
        best_i, best_d = -1, float("inf")
        for i, nd in enumerate(self.placed_nodes):
            sx, sy = self.world_to_screen(nd["px"], nd["py"])
            d = math.hypot(ex - sx, ey - sy)
            if d < best_d:
                best_d, best_i = d, i
        if best_d < threshold * self.global_zoom and best_i >= 0:
            return best_i, best_d
        return -1, float("inf")

    @staticmethod
    def _point_to_segment(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    # ══════════════════════════════════════════════════════════════════════════
    # Image Loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_image(self):
        if not PIL_AVAILABLE:
            messagebox.showwarning(
                "Pillow Not Installed",
                "Install Pillow to load background images:\n\n  pip install pillow")
            return
        path = filedialog.askopenfilename(
            title="Open Background Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff"),
                       ("All files", "*.*")])
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

        # ── Background image ──
        if self._bg_image:
            iw = max(1, int(self._bg_image.width  * gz))
            ih = max(1, int(self._bg_image.height * gz))
            resized        = self._bg_image.resize((iw, ih), Image.LANCZOS)
            self._bg_photo = ImageTk.PhotoImage(resized)
            c.create_image(self.pan_x, self.pan_y, anchor="nw", image=self._bg_photo)

        # ── Grid color blending ──
        base_r, base_g, base_b = 0x7c, 0x7c, 0xff
        bg_r,   bg_g,   bg_b   = 0x0e, 0x0e, 0x12

        def blend(op):
            r = int(bg_r + (base_r - bg_r) * op)
            g = int(bg_g + (base_g - bg_g) * op)
            b = int(bg_b + (base_b - bg_b) * op)
            return f"#{r:02x}{g:02x}{b:02x}"

        minor_color = blend(self.grid_opacity * 0.35)
        major_color = blend(self.grid_opacity * 0.70)
        label_color = blend(self.grid_opacity * 0.50)

        # Minor grid lines
        if step >= 4:
            ox, oy = self.pan_x % step, self.pan_y % step
            x = ox
            while x < w:
                c.create_line(x, 0, x, h, fill=minor_color, width=1)
                x += step
            y = oy
            while y < h:
                c.create_line(0, y, w, y, fill=minor_color, width=1)
                y += step

        # Major grid lines + axis labels
        if major_step >= 8:
            ox, oy = self.pan_x % major_step, self.pan_y % major_step
            x = ox
            while x < w:
                c.create_line(x, 0, x, h, fill=major_color, width=1)
                col_idx = round((x - self.pan_x) / step)
                c.create_text(x, 10, text=str(col_idx), fill=label_color,
                              font=("Courier", 8), anchor="n")
                x += major_step
            y = oy
            while y < h:
                c.create_line(0, y, w, y, fill=major_color, width=1)
                row_idx = round((y - self.pan_y) / step)
                c.create_text(8, y, text=str(row_idx), fill=label_color,
                              font=("Courier", 8), anchor="w")
                y += major_step

        # ── Sample network ──
        if self.show_network and not self._bg_image:
            for a_id, b_id in SAMPLE_EDGES:
                a = NODE_MAP[a_id]
                b = NODE_MAP[b_id]
                ax, ay = self.world_to_screen(a["x"], a["y"])
                bx, by = self.world_to_screen(b["x"], b["y"])
                c.create_line(ax, ay, bx, by, fill="#444444", width=1, dash=(6, 3))
            for n in SAMPLE_NODES:
                sx, sy = self.world_to_screen(n["x"], n["y"])
                ro, ri = 16 * gz, 9 * gz
                c.create_oval(sx - ro, sy - ro, sx + ro, sy + ro,
                              fill="", outline=n["color"], width=1)
                c.create_oval(sx - ri, sy - ri, sx + ri, sy + ri,
                              fill=n["color"], outline="")
                c.create_text(sx, sy, text=n["id"], fill="white",
                              font=("Courier", max(8, int(10 * gz)), "bold"))

        # ── Placed edges (directed arrows) ──
        for (ia, ib) in self.placed_edges:
            na = self._node_by_id(ia)
            nb = self._node_by_id(ib)
            if na and nb:
                ax, ay = self.world_to_screen(na["px"], na["py"])
                bx, by = self.world_to_screen(nb["px"], nb["py"])
                arrow_shape = (max(6, 10 * gz), max(8, 12 * gz), max(3, 4 * gz))
                c.create_line(ax, ay, bx, by, fill=EDGE_CLR,
                              width=max(1, int(2 * gz)),
                              arrow=tk.LAST, arrowshape=arrow_shape)
                mx, my = (ax + bx) / 2, (ay + by) / 2
                c.create_text(mx, my - 9, text=f"{na['name']}→{nb['name']}",
                              fill=EDGE_CLR, font=("Courier", max(7, int(8 * gz))))

        # ── Placed nodes ──
        for nd in self.placed_nodes:
            sx, sy  = self.world_to_screen(nd["px"], nd["py"])
            color   = PYWR_COLORS.get(nd["type"], NODE_CLR)
            is_sel  = (self.edge_mode and self._edge_src == nd["id"])
            ro, ri  = 14 * gz, 5 * gz
            outline = SEL_CLR if is_sel else color
            width   = 3 if is_sel else 2
            c.create_oval(sx - ro, sy - ro, sx + ro, sy + ro,
                          outline=outline, width=width, fill=BG)
            c.create_oval(sx - ri, sy - ri, sx + ri, sy + ri,
                          fill=color, outline="")
            label = f"{nd['name']} [{nd['type'][:3]}]  ({nd['col']}, {nd['row']})"
            c.create_text(sx + 17 * gz, sy - 12 * gz, text=label,
                          fill=color, font=("Courier", max(7, int(9 * gz))), anchor="w")

        # ── Hover crosshair + tooltip ──
        if self.grid_locked and self._hover_coord and not self.edge_mode:
            hx, hy = self._hover_screen
            c.create_line(hx, 0, hx, h, fill=NODE_CLR, width=1, dash=(3, 5))
            c.create_line(0, hy, w, hy, fill=NODE_CLR, width=1, dash=(3, 5))
            coord = self._hover_coord
            txt = f"col:{coord['col']}  row:{coord['row']}"
            c.create_rectangle(hx + 14, hy - 28, hx + 14 + len(txt) * 7 + 12, hy - 8,
                               fill=BG, outline=ACCENT, width=1)
            c.create_text(hx + 20, hy - 18, text=txt, fill=NODE_CLR,
                          font=("Courier", 9), anchor="w")

        # ── Calibration hint ──
        if not self.grid_locked:
            hint = "Scroll to calibrate grid scale  →  then click  Lock Grid"
            tw = len(hint) * 7
            cx = w // 2
            c.create_rectangle(cx - tw // 2 - 12, 14, cx + tw // 2 + 12, 40,
                               fill=BG, outline=ACCENT, width=1)
            c.create_text(cx, 27, text=hint, fill=ACCENT, font=("Courier", 10))

        # ── Status bar ──
        mode  = "View Zoom" if self.grid_locked else "Grid Scale"
        emode = ("  │  EDGE MODE: click source then target node  (Esc = cancel)"
                 if self.edge_mode else "")
        self.status_lbl.config(
            text=(f"Grid: {egs:.1f}px/unit   Zoom: {self.global_zoom:.2f}×   "
                  f"Nodes: {len(self.placed_nodes)}   Edges: {len(self.placed_edges)}   "
                  f"Scroll = {mode}   Mid-Drag/Alt+Drag = Pan   Right-Click = Remove"
                  f"{emode}")
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Event Handlers
    # ══════════════════════════════════════════════════════════════════════════

    def _on_click(self, event):
        if not self.grid_locked:
            return
        if self.edge_mode:
            self._handle_edge_click(event)
        else:
            self._place_node(event)

    def _place_node(self, event):
        coord = self.screen_to_grid(event.x, event.y)
        ntype = self._node_type_var.get()
        node  = {
            "id":   self.node_counter,
            "name": f"N{self.node_counter}",
            "type": ntype,
            "col":  coord["col"],
            "row":  coord["row"],
            "px":   coord["px"],
            "py":   coord["py"],
        }
        self.placed_nodes.append(node)
        self.node_counter += 1
        self.redraw()
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

    def _on_double_click(self, event):
        if not self.grid_locked or self.edge_mode:
            return
        idx, _ = self._nearest_placed_node(event.x, event.y)
        if idx < 0:
            return
        nd       = self.placed_nodes[idx]
        new_name = simpledialog.askstring(
            "Rename Node",
            f"New name for node '{nd['name']}':",
            initialvalue=nd["name"],
            parent=self.root)
        if new_name and new_name.strip():
            nd["name"] = new_name.strip()
            self.redraw()
            self._refresh_export()

    def _on_right_click(self, event):
        if not self.placed_nodes and not self.placed_edges:
            return
        # Find nearest node
        idx, d_node = self._nearest_placed_node(event.x, event.y, threshold=30)
        # Find nearest edge
        best_e, best_ed = -1, float("inf")
        for i, (ia, ib) in enumerate(self.placed_edges):
            na = self._node_by_id(ia)
            nb = self._node_by_id(ib)
            if na and nb:
                ax, ay = self.world_to_screen(na["px"], na["py"])
                bx, by = self.world_to_screen(nb["px"], nb["py"])
                d = self._point_to_segment(event.x, event.y, ax, ay, bx, by)
                if d < best_ed:
                    best_ed, best_e = d, i

        if idx >= 0 and d_node <= best_ed:
            # Remove node and its connected edges
            removed_id = self.placed_nodes.pop(idx)["id"]
            self.placed_edges = [
                (a, b) for (a, b) in self.placed_edges
                if a != removed_id and b != removed_id
            ]
            if self._edge_src == removed_id:
                self._edge_src = None
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
            self.redraw()

    # Pan
    def _on_pan_start(self, event):
        self._pan_dragging = True
        self._pan_start_x  = event.x
        self._pan_start_y  = event.y
        self._pan_start_ox = self.pan_x
        self._pan_start_oy = self.pan_y
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
            scale   = self.global_zoom / old
            self.pan_x = event.x - scale * (event.x - self.pan_x)
            self.pan_y = event.y - scale * (event.y - self.pan_y)
            self.global_zoom_lbl.config(text=f"{self.global_zoom:.2f}×")
        self.redraw()

    # Toolbar actions
    def _grid_zoom_in(self):
        if self.grid_locked:
            return
        self.grid_zoom = min(MAX_GRID_ZOOM, self.grid_zoom * 1.2)
        self.grid_zoom_lbl.config(text=f"{self.grid_zoom:.2f}×")
        self.redraw()

    def _grid_zoom_out(self):
        if self.grid_locked:
            return
        self.grid_zoom = max(MIN_GRID_ZOOM, self.grid_zoom / 1.2)
        self.grid_zoom_lbl.config(text=f"{self.grid_zoom:.2f}×")
        self.redraw()

    def _global_zoom_in(self):
        self.global_zoom = min(MAX_GLOBAL_ZOOM, self.global_zoom * 1.2)
        self.global_zoom_lbl.config(text=f"{self.global_zoom:.2f}×")
        self.redraw()

    def _global_zoom_out(self):
        self.global_zoom = max(MIN_GLOBAL_ZOOM, self.global_zoom / 1.2)
        self.global_zoom_lbl.config(text=f"{self.global_zoom:.2f}×")
        self.redraw()

    def _reset_view(self):
        self.global_zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.global_zoom_lbl.config(text="1.00×")
        self.redraw()

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
            self.edge_mode = False
            self._edge_src = None
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
            self.placed_edges = [
                (a, b) for (a, b) in self.placed_edges
                if a != removed_id and b != removed_id
            ]
            self.redraw()
            self._refresh_export()

    def _clear_nodes(self):
        self.placed_nodes.clear()
        self.placed_edges.clear()
        self.node_counter = 1
        self._edge_src    = None
        self.redraw()
        self._refresh_export()

    def _on_opacity(self, val):
        self.grid_opacity = float(val)
        self.opacity_lbl.config(text=f"{int(self.grid_opacity * 100)}%")
        self.redraw()

    def _on_toggle_network(self):
        self.show_network = self.net_var.get()
        self.redraw()

    # ══════════════════════════════════════════════════════════════════════════
    # Export Panel
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_export(self):
        self.export_visible = not self.export_visible
        if self.export_visible:
            self.export_panel.pack(side=tk.RIGHT, fill=tk.Y)
            self._build_export_content()
            self.export_btn.config(bg="#339af0", fg="white")
        else:
            self.export_panel.pack_forget()
            self.export_btn.config(bg="#2a2a35", fg=TEXT_CLR)

    def _build_export_content(self):
        for w in self.export_panel.winfo_children():
            w.destroy()

        tk.Label(self.export_panel, text="EXPORT — PyWR EDITION", bg=PANEL_BG,
                 fg=NODE_CLR, font=("Courier", 11, "bold"), anchor="w"
                 ).pack(fill=tk.X, padx=10, pady=(10, 2))
        tk.Label(self.export_panel,
                 text=(f"Grid unit = {self.effective_grid_size:.1f}px  |  "
                       f"{len(self.placed_nodes)} nodes  {len(self.placed_edges)} edges"),
                 bg=PANEL_BG, fg=DIM_CLR, font=("Courier", 9), anchor="w"
                 ).pack(fill=tk.X, padx=10, pady=(0, 8))

        if not self.placed_nodes:
            tk.Label(self.export_panel, text="Place nodes on the canvas first.",
                     bg=PANEL_BG, fg="#555555", font=("Courier", 9)).pack(pady=30)
            return

        # ── Node table ──
        hdr = tk.Frame(self.export_panel, bg="#1e1e28")
        hdr.pack(fill=tk.X, padx=10)
        for col_name, cw in [("#", 3), ("Name", 8), ("Type", 10), ("Col", 6), ("Row", 6)]:
            tk.Label(hdr, text=col_name, bg="#1e1e28", fg=ACCENT,
                     font=("Courier", 9, "bold"), width=cw, anchor="w"
                     ).pack(side=tk.LEFT, padx=2, pady=3)

        row_canvas = tk.Canvas(self.export_panel, bg=PANEL_BG, highlightthickness=0, height=160)
        sb = ttk.Scrollbar(self.export_panel, orient="vertical", command=row_canvas.yview)
        sf = tk.Frame(row_canvas, bg=PANEL_BG)
        sf.bind("<Configure>", lambda e: row_canvas.configure(scrollregion=row_canvas.bbox("all")))
        row_canvas.create_window((0, 0), window=sf, anchor="nw")
        row_canvas.configure(yscrollcommand=sb.set)

        for nd in self.placed_nodes:
            rf    = tk.Frame(sf, bg=PANEL_BG)
            rf.pack(fill=tk.X)
            color = PYWR_COLORS.get(nd["type"], NODE_CLR)
            for val, cw in [(nd["id"], 3), (nd["name"], 8), (nd["type"], 10),
                             (nd["col"], 6), (nd["row"], 6)]:
                tk.Label(rf, text=str(val), bg=PANEL_BG, fg=color,
                         font=("Courier", 9), width=cw, anchor="w"
                         ).pack(side=tk.LEFT, padx=2, pady=1)

        row_canvas.pack(fill=tk.BOTH, expand=True, padx=10)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Edge list ──
        if self.placed_edges:
            tk.Label(self.export_panel, text="EDGES", bg=PANEL_BG, fg=EDGE_CLR,
                     font=("Courier", 9, "bold"), anchor="w"
                     ).pack(fill=tk.X, padx=10, pady=(6, 2))
            ef = tk.Frame(self.export_panel, bg=PANEL_BG, height=70)
            ef.pack(fill=tk.X, padx=10)
            ef.pack_propagate(False)
            for (ia, ib) in self.placed_edges:
                na = self._node_by_id(ia)
                nb = self._node_by_id(ib)
                if na and nb:
                    tk.Label(ef, text=f"  {na['name']}  →  {nb['name']}",
                             bg=PANEL_BG, fg=EDGE_CLR, font=("Courier", 9),
                             anchor="w").pack(fill=tk.X)

        # ── PyWR JSON preview ──
        tk.Label(self.export_panel, text="PyWR JSON preview", bg=PANEL_BG, fg=DIM_CLR,
                 font=("Courier", 9, "bold"), anchor="w"
                 ).pack(fill=tk.X, padx=10, pady=(8, 2))
        self.export_text = tk.Text(self.export_panel, bg=BG, fg=TEXT_CLR,
                                   font=("Courier", 9), height=7, wrap=tk.WORD,
                                   relief="flat", bd=0, padx=8, pady=6)
        self.export_text.pack(fill=tk.X, padx=10)
        self._update_json_display()

        # ── Export buttons ──
        btn_frame = tk.Frame(self.export_panel, bg=PANEL_BG)
        btn_frame.pack(fill=tk.X, padx=10, pady=8)
        for label, cmd, bg, fg in [
            ("Copy JSON", self._copy_json,      ACCENT,    BG),
            ("Save JSON", self._save_json,       "#339af0", "white"),
            ("Save CSV",  self._save_csv,        "#51cf66", BG),
            ("PyWR JSON", self._save_pywr_json,  "#fcc419", BG),
        ]:
            tk.Button(btn_frame, text=label, command=cmd, bg=bg, fg=fg,
                      font=("Courier", 9, "bold"), relief="flat",
                      padx=4, pady=4, cursor="hand2"
                      ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)

    def _get_export_data(self):
        """Flat list of nodes with both grid and pixel coords."""
        return [
            {"id": n["id"], "name": n["name"], "type": n["type"],
             "grid": {"col": n["col"], "row": n["row"]},
             "pixel": {"x": n["px"], "y": n["py"]}}
            for n in self.placed_nodes
        ]

    def _get_pywr_json(self):
        """Build a PyWR-compatible model skeleton."""
        nodes = [
            {
                "name": n["name"],
                "type": n["type"],
                "comment": f"grid col={n['col']} row={n['row']}",
            }
            for n in self.placed_nodes
        ]
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
            "timestepper": {
                "start":    "2000-01-01",
                "end":      "2000-12-31",
                "timestep": 1,
            },
            "nodes":      nodes,
            "edges":      edges,
            "parameters": {},
            "recorders":  {},
        }

    def _update_json_display(self):
        if self.export_text:
            self.export_text.delete("1.0", tk.END)
            self.export_text.insert("1.0", json.dumps(self._get_pywr_json(), indent=2))

    def _refresh_export(self):
        if self.export_visible:
            self._build_export_content()

    def _copy_json(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(json.dumps(self._get_export_data(), indent=2))
        messagebox.showinfo("Copied", "Node positions JSON copied to clipboard!")

    def _save_json(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path:
            with open(path, "w") as f:
                json.dump(self._get_export_data(), f, indent=2)
            messagebox.showinfo("Saved", f"Saved to:\n{path}")

    def _save_csv(self):
        """Export nodes as CSV — id, name, type, col, row, px, py."""
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile="nodes",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["id", "name", "type", "col", "row", "px", "py"])
            writer.writeheader()
            for n in self.placed_nodes:
                writer.writerow({k: n[k] for k in ["id", "name", "type", "col", "row", "px", "py"]})
        messagebox.showinfo("Saved", f"CSV saved to:\n{path}")

    def _save_pywr_json(self):
        """Export a PyWR-compatible model JSON skeleton."""
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile="pywr_model",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path:
            with open(path, "w") as f:
                json.dump(self._get_pywr_json(), f, indent=2)
            messagebox.showinfo("Saved", f"PyWR model saved to:\n{path}")


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
                windll.user32.GetParent(root.winfo_id()),
                20, byref(c_int(1)), 4)
        except Exception:
            pass

    app = GraphOverlayApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
