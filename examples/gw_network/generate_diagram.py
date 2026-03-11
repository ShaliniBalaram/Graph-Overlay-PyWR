#!/usr/bin/env python3
"""
Generates network_diagram.png — a schematic of the GW base/topup/total network.

This image can be loaded as a background in Graph Overlay Tool (Load Image button)
so you can trace the network on top of it.

Usage:
    pip install pillow
    python generate_diagram.py
"""
import math
import os
from PIL import Image, ImageDraw

# ── Canvas ──────────────────────────────────────────────────────────────────

W, H = 1500, 620
BG        = "#1e1e2e"
GRID_CLR  = "#2a2a3e"
TEXT_CLR  = "#e0e0e0"
DIM_CLR   = "#888899"
EDGE_CLR  = "#ff922b"

# ── Node type colours ────────────────────────────────────────────────────────

TYPE_COLORS = {
    "catchment":  "#51cf66",
    "input":      "#2f9e44",
    "link":       "#fcc419",
    "river":      "#339af0",
    "rivergauge": "#cc5de8",
    "reservoir":  "#74c0fc",
    "riversplit": "#f783ac",
    "output":     "#ff922b",
}

# ── Node definitions (x, y = centre on the image) ────────────────────────────

NODES = {
    "Rainfall_Catchment": {
        "type": "catchment", "x":  110, "y":  100,
        "label": "Rainfall\nCatchment",
    },
    "GW_Base": {
        "type": "input",    "x":  270, "y":  270,
        "label": "GW_Base\n(Base Abstraction)",
    },
    "GW_Topup": {
        "type": "input",    "x":  270, "y":  420,
        "label": "GW_Topup\n(Top-up Abstraction)",
    },
    "GW_Total": {
        "type": "link",     "x":  440, "y":  340,
        "label": "GW_Total\n(Converging Link)",
    },
    "River_Main": {
        "type": "river",    "x":  580, "y":  100,
        "label": "River_Main",
    },
    "River_Gauge_A": {
        "type": "rivergauge", "x": 750, "y": 100,
        "label": "River_Gauge_A\n(MRF = 10 Ml/d)",
    },
    "Reservoir_A": {
        "type": "reservoir", "x": 940, "y": 100,
        "label": "Reservoir_A\n(500 Ml)",
    },
    "River_Split_A": {
        "type": "riversplit", "x": 1100, "y": 290,
        "label": "River_Split_A\n(60 / 30 / 10 %)",
    },
    "River_Outlet": {
        "type": "output",   "x": 1350, "y": 100,
        "label": "River_Outlet",
    },
    "Demand_Urban": {
        "type": "output",   "x": 1350, "y": 270,
        "label": "Demand_Urban",
    },
    "Demand_Irrigation": {
        "type": "output",   "x": 1350, "y": 430,
        "label": "Demand_Irrigation",
    },
}

EDGES = [
    ("Rainfall_Catchment", "River_Main"),
    ("GW_Base",            "GW_Total"),
    ("GW_Topup",           "GW_Total"),
    ("GW_Total",           "River_Main"),
    ("River_Main",         "River_Gauge_A"),
    ("River_Gauge_A",      "Reservoir_A"),
    ("Reservoir_A",        "River_Split_A"),
    ("River_Split_A",      "River_Outlet"),
    ("River_Split_A",      "Demand_Urban"),
    ("River_Split_A",      "Demand_Irrigation"),
]

NODE_R = 26   # node circle radius

# ── Helpers ──────────────────────────────────────────────────────────────────

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def darken(h, f=0.55):
    r, g, b = hex_to_rgb(h)
    return (int(r * f), int(g * f), int(b * f))

def arrow_endpoints(src, dst, r=NODE_R + 4):
    """Return (x1,y1,x2,y2) shortened by r at each end."""
    dx, dy = dst[0] - src[0], dst[1] - src[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return src[0], src[1], dst[0], dst[1]
    ux, uy = dx / length, dy / length
    x1 = src[0] + ux * r
    y1 = src[1] + uy * r
    x2 = dst[0] - ux * (r + 6)
    y2 = dst[1] - uy * (r + 6)
    return x1, y1, x2, y2

def draw_arrow(draw, x1, y1, x2, y2, color, width=2):
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    # Arrowhead
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    size = 12
    px, py = -uy * size * 0.5, ux * size * 0.5
    pts = [
        (x2, y2),
        (x2 - ux * size + px, y2 - uy * size + py),
        (x2 - ux * size - px, y2 - uy * size - py),
    ]
    draw.polygon(pts, fill=color)

def draw_node(draw, node, r=NODE_R):
    x, y    = node["x"], node["y"]
    ntype   = node["type"]
    color   = hex_to_rgb(TYPE_COLORS.get(ntype, "#888888"))
    dark    = darken(TYPE_COLORS.get(ntype, "#888888"))
    outline = tuple(min(255, c + 60) for c in color)

    if ntype in ("catchment", "input"):
        # Triangle
        pts = [(x, y - r), (x - r, y + r * 0.8), (x + r, y + r * 0.8)]
        draw.polygon(pts, fill=dark, outline=outline)
        inner = [(x, y - r * 0.5), (x - r * 0.5, y + r * 0.4), (x + r * 0.5, y + r * 0.4)]
        draw.polygon(inner, fill=color)
    elif ntype in ("reservoir", "storage"):
        # Rectangle
        draw.rectangle([x - r * 1.4, y - r * 0.8, x + r * 1.4, y + r * 0.8],
                       fill=dark, outline=outline, width=2)
        draw.rectangle([x - r, y - r * 0.5, x + r, y + r * 0.5], fill=color)
    elif ntype == "output":
        # Diamond
        pts = [(x, y - r), (x + r, y), (x, y + r), (x - r, y)]
        draw.polygon(pts, fill=dark, outline=outline)
        inner = [(x, y - r * 0.5), (x + r * 0.5, y), (x, y + r * 0.5), (x - r * 0.5, y)]
        draw.polygon(inner, fill=color)
    elif ntype == "link":
        # Square
        draw.rectangle([x - r, y - r, x + r, y + r], fill=dark, outline=outline, width=2)
        inner_r = int(r * 0.55)
        draw.rectangle([x - inner_r, y - inner_r, x + inner_r, y + inner_r], fill=color)
    else:
        # Circle (river, rivergauge, riversplit)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=dark, outline=outline, width=2)
        inner_r = int(r * 0.55)
        draw.ellipse([x - inner_r, y - inner_r, x + inner_r, y + inner_r], fill=color)

def draw_label(draw, node):
    from PIL import ImageFont
    x, y  = node["x"], node["y"]
    lines = node["label"].split("\n")
    # Position label below node
    ty = y + NODE_R + 8
    for i, line in enumerate(lines):
        # Estimate text width (~7px per char at size 14)
        tw = len(line) * 7
        tx = x - tw // 2
        # Shadow
        draw.text((tx + 1, ty + i * 16 + 1), line, fill=(0, 0, 0, 180))
        draw.text((tx,     ty + i * 16),     line, fill=hex_to_rgb(TEXT_CLR))

# ── Draw ─────────────────────────────────────────────────────────────────────

def draw_grid(draw):
    step = 50
    for x in range(0, W, step):
        draw.line([(x, 0), (x, H)], fill=GRID_CLR, width=1)
    for y in range(0, H, step):
        draw.line([(0, y), (W, y)], fill=GRID_CLR, width=1)

def main():
    img  = Image.new("RGB", (W, H), hex_to_rgb(BG))
    draw = ImageDraw.Draw(img, "RGBA")

    draw_grid(draw)

    # Title
    draw.text((W // 2 - 200, 14),
              "GW Base / Top-up / Total  —  Example Network",
              fill=hex_to_rgb("#aaaacc"))

    # Draw edges first (under nodes)
    for src_name, dst_name in EDGES:
        src = NODES[src_name]
        dst = NODES[dst_name]
        x1, y1, x2, y2 = arrow_endpoints(
            (src["x"], src["y"]), (dst["x"], dst["y"]))
        draw_arrow(draw, x1, y1, x2, y2,
                   color=hex_to_rgb(EDGE_CLR), width=2)

    # Draw nodes
    for node in NODES.values():
        draw_node(draw, node)

    # Draw labels
    for node in NODES.values():
        draw_label(draw, node)

    # Legend
    lx, ly = 20, H - 160
    draw.text((lx, ly - 18), "NODE TYPES", fill=hex_to_rgb("#aaaacc"))
    legend_items = [
        ("catchment / input", "#51cf66"),
        ("river",             "#339af0"),
        ("link",              "#fcc419"),
        ("rivergauge",        "#cc5de8"),
        ("reservoir",         "#74c0fc"),
        ("riversplit",        "#f783ac"),
        ("output",            "#ff922b"),
    ]
    for i, (label, color) in enumerate(legend_items):
        cx = lx + 8
        cy = ly + i * 20 + 8
        draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6],
                     fill=hex_to_rgb(color))
        draw.text((cx + 12, cy - 7), label,
                  fill=hex_to_rgb(DIM_CLR))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "network_diagram.png")
    img.save(out)
    print(f"Diagram saved: {out}")
    print("Load this image in Graph Overlay Tool via the 'Load Image' button.")

if __name__ == "__main__":
    main()
