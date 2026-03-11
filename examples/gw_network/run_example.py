#!/usr/bin/env python3
"""
GW Network Example — Run Script
================================
Runs the complete PyWR simulation for the GW base/topup/total example.

This script:
  1. Generates the network diagram image  (network_diagram.png)
  2. Loads pywr_model.json
  3. Runs the simulation
  4. Saves results to results.csv and prints a summary

Usage:
    pip install pywr pandas pillow
    python run_example.py

Files in this folder:
    network_diagram.png   ← Background image for Graph Overlay Tool
    pywr_model.json       ← Complete PyWR model (open in pywr-editor)
    params.csv            ← Monthly input/output time-series
    nodes.csv             ← Node positions (import into Graph Overlay Tool)
    nodes_edges.csv       ← Edge definitions
    session.goverlap      ← Load Session in Graph Overlay Tool to see full network
    results.csv           ← Created after running this script

Author: Shalini B
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


# ── Step 1: Generate diagram image ──────────────────────────────────────────

print("=" * 60)
print("  GW Network Example")
print("=" * 60)

diagram_path = os.path.join(HERE, "network_diagram.png")
if not os.path.exists(diagram_path):
    print("\n[1/3] Generating network diagram...")
    try:
        import generate_diagram
        generate_diagram.main()
    except Exception as e:
        print(f"      Could not generate diagram: {e}")
else:
    print(f"\n[1/3] Network diagram already exists: network_diagram.png")

print(f"      Load it in Graph Overlay Tool → Load Image button")


# ── Step 2: Run PyWR simulation ──────────────────────────────────────────────

print("\n[2/3] Running PyWR simulation...")

model_path = os.path.join(HERE, "pywr_model.json")

try:
    import pandas as pd
    from pywr.model import Model

    model = Model.load(model_path, path=HERE)
    model.run()

    print("      Simulation complete.")

    # ── Step 3: Collect and save results ────────────────────────────────────

    print("\n[3/3] Collecting results...")

    def node_flow(name):
        return model.recorders[name].data.flatten()

    def node_vol(name):
        return model.recorders[name].data.flatten()

    import numpy as np

    dates = pd.date_range("2000-01-01", periods=12, freq="30D")

    gw_base  = node_flow("GW_Base_flow")
    gw_topup = node_flow("GW_Topup_flow")
    gw_total = node_flow("GW_Total_flow")
    urban    = node_flow("Urban_supply")
    irrig    = node_flow("Irrigation_supply")
    res_vol  = node_vol("Reservoir_volume")
    gauge    = node_flow("Gauge_flow")

    results = pd.DataFrame({
        "GW_Base_Ml_d":       gw_base,
        "GW_Topup_Ml_d":      gw_topup,
        "GW_Total_Ml_d":      gw_total,
        "Gauge_Flow_Ml_d":    gauge,
        "Reservoir_Vol_Ml":   res_vol,
        "Urban_Supply_Ml_d":  urban,
        "Irrig_Supply_Ml_d":  irrig,
    }, index=dates)
    results.index.name = "Date"

    results_path = os.path.join(HERE, "results.csv")
    results.to_csv(results_path)

    # ── Print summary ────────────────────────────────────────────────────────

    print("\n── Annual Summary ──────────────────────────────────────────────")
    print(f"  Total GW Base abstracted  : {gw_base.sum():>8.1f}  Ml")
    print(f"  Total GW Top-up abstracted: {gw_topup.sum():>8.1f}  Ml")
    print(f"  Total GW (combined)       : {gw_total.sum():>8.1f}  Ml")
    print(f"  Total Urban supply        : {urban.sum():>8.1f}  Ml")
    print(f"  Total Irrigation supply   : {irrig.sum():>8.1f}  Ml")
    print(f"  Reservoir end volume      : {res_vol[-1]:>8.1f}  Ml")
    print(f"\n── Monthly Results ─────────────────────────────────────────────")
    print(results.to_string())
    print(f"\n  Results saved to: results.csv")

    # ── Demand satisfaction check ────────────────────────────────────────────
    urban_demand  = pd.read_csv(os.path.join(HERE, "params.csv"),
                                index_col="Date", parse_dates=True)["Urban_Demand"]
    irrig_demand  = pd.read_csv(os.path.join(HERE, "params.csv"),
                                index_col="Date", parse_dates=True)["Irrigation_Demand"]

    urban_unmet = max(0, urban_demand.sum() - urban.sum())
    irrig_unmet = max(0, irrig_demand.sum() - irrig.sum())

    print(f"\n── Demand Satisfaction ─────────────────────────────────────────")
    if urban_unmet < 0.1:
        print("  Urban demand    : FULLY MET")
    else:
        print(f"  Urban demand    : {urban_unmet:.1f} Ml UNMET")
    if irrig_unmet < 0.1:
        print("  Irrigation demand: FULLY MET")
    else:
        print(f"  Irrigation demand: {irrig_unmet:.1f} Ml UNMET")

except ImportError as e:
    print(f"\n  PyWR or pandas not installed: {e}")
    print("  Install with:  pip install pywr pandas")
    print("\n  The pywr_model.json is ready — open it in pywr-editor directly.")

except Exception as e:
    print(f"\n  Error running model: {e}")
    print("  Check that params.csv is in the same folder as pywr_model.json.")

print("\n" + "=" * 60)
print("  Files in this example:")
print(f"    network_diagram.png  — load as background in Graph Overlay Tool")
print(f"    pywr_model.json      — open directly in pywr-editor")
print(f"    params.csv           — input/output time-series")
print(f"    session.goverlap     — load in Graph Overlay Tool (Load Session)")
print(f"    nodes.csv            — import nodes into Graph Overlay Tool")
print(f"    results.csv          — simulation output (after running)")
print("=" * 60)
