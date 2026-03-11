#!/usr/bin/env python3
"""
GW Network Example — Graph Overlay PyWR Edition
================================================
This script builds a PyWR model from the exported JSON and runs it.

Network topology:
    Rainfall_Catchment  ─────────────────────────────────► River_Main
                                                                │
    GW_Base ────────► GW_Total (link) ──────────────────────────┘
    GW_Topup ──────► GW_Total
                                                            River_Main
                                                                │
                                                         River_Gauge_A (MRF)
                                                                │
                                                          Reservoir_A
                                                                │
                                                         River_Split_A
                                                        ┌───────┼───────┐
                                                  Demand_Urban  Demand_Irrigation  River_Outlet

Groundwater Abstraction:
  - GW_Base:  base-load groundwater abstraction  (always-on, lower cost)
  - GW_Topup: top-up groundwater abstraction     (available when needed, higher cost)
  - GW_Total: converging link — base + topup combined flow into the river

Usage:
    pip install pywr pandas
    python run_example.py

Author: Shalini B
"""

import json
import os

# ── Step 1: Build the PyWR model JSON programmatically ─────────────────────

HERE = os.path.dirname(os.path.abspath(__file__))

model = {
    "metadata": {
        "title": "GW Base-Topup-Total Example",
        "description": (
            "Groundwater divided into base abstraction, top-up abstraction, "
            "and total abstraction converging into the main river."
        ),
        "minimum_version": "0.1",
    },
    "timestepper": {
        "start": "2000-01-01",
        "end":   "2000-12-31",
        "timestep": 30,   # monthly steps (30-day approximation)
    },
    "nodes": [
        # ── Catchment inflow ────────────────────────────────────────────
        {
            "name": "Rainfall_Catchment",
            "type": "catchment",
            "position": {"schematic": [2.0, 1.0]},
            "flow": {
                "type":       "CSVParameter",
                "url":        "params.csv",
                "column":     "Rainfall_Flow",
                "index_col":  "Date",
                "parse_dates": True,
            },
        },
        # ── Groundwater base abstraction ────────────────────────────────
        {
            "name": "GW_Base",
            "type": "input",
            "position": {"schematic": [4.0, 3.0]},
            "max_flow": {
                "type":       "CSVParameter",
                "url":        "params.csv",
                "column":     "GW_Base_MaxFlow",
                "index_col":  "Date",
                "parse_dates": True,
            },
            "min_flow": 0.0,
            "cost": 1.0,    # low cost = preferred abstraction
        },
        # ── Groundwater top-up abstraction ──────────────────────────────
        {
            "name": "GW_Topup",
            "type": "input",
            "position": {"schematic": [6.0, 3.0]},
            "max_flow": {
                "type":       "CSVParameter",
                "url":        "params.csv",
                "column":     "GW_Topup_MaxFlow",
                "index_col":  "Date",
                "parse_dates": True,
            },
            "min_flow": 0.0,
            "cost": 5.0,    # higher cost = only used when base is not enough
        },
        # ── GW Total: converging link (base + topup → river) ────────────
        {
            "name": "GW_Total",
            "type": "link",
            "position": {"schematic": [5.0, 5.0]},
            "cost": 0.0,
            # No max_flow restriction — passes whatever flows in from Base + Topup
        },
        # ── Main river reach ─────────────────────────────────────────────
        {
            "name": "River_Main",
            "type": "river",
            "position": {"schematic": [8.0, 1.0]},
            "cost": 0.0,
        },
        # ── Gauging station with minimum residual flow ───────────────────
        {
            "name": "River_Gauge_A",
            "type": "rivergauge",
            "position": {"schematic": [8.0, 3.0]},
            "mrf":      10.0,         # 10 Ml/d minimum residual flow
            "mrf_cost": -500.0,       # penalty for violating MRF
            "cost":     0.0,
        },
        # ── Reservoir ────────────────────────────────────────────────────
        {
            "name": "Reservoir_A",
            "type": "reservoir",
            "position": {"schematic": [10.0, 3.0]},
            "max_volume":      500.0,
            "min_volume":       50.0,
            "initial_volume":  350.0,
            "cost": 0.0,
        },
        # ── Flow split: 60% demand, 40% onward ──────────────────────────
        {
            "name": "River_Split_A",
            "type": "riversplit",
            "position": {"schematic": [10.0, 6.0]},
            "factors": [0.6, 0.3, 0.1],   # Urban : Irrigation : Outlet
            "slot_names": ["urban_slot", "irrigation_slot", "outlet_slot"],
        },
        # ── Urban demand ─────────────────────────────────────────────────
        {
            "name": "Demand_Urban",
            "type": "output",
            "position": {"schematic": [12.0, 5.0]},
            "max_flow": {
                "type":       "CSVParameter",
                "url":        "params.csv",
                "column":     "Urban_Demand",
                "index_col":  "Date",
                "parse_dates": True,
            },
            "cost": -200.0,
        },
        # ── Irrigation demand ─────────────────────────────────────────────
        {
            "name": "Demand_Irrigation",
            "type": "output",
            "position": {"schematic": [12.0, 7.0]},
            "max_flow": {
                "type":       "CSVParameter",
                "url":        "params.csv",
                "column":     "Irrigation_Demand",
                "index_col":  "Date",
                "parse_dates": True,
            },
            "cost": -100.0,
        },
        # ── River outlet (terminal sink) ──────────────────────────────────
        {
            "name": "River_Outlet",
            "type": "output",
            "position": {"schematic": [14.0, 3.0]},
            "cost": -500.0,   # high benefit = always pass through if possible
        },
    ],
    "edges": [
        # Catchment → River_Main
        ["Rainfall_Catchment", "River_Main"],
        # GW base and top-up → GW_Total
        ["GW_Base",   "GW_Total"],
        ["GW_Topup",  "GW_Total"],
        # GW_Total → River_Main
        ["GW_Total",  "River_Main"],
        # River chain
        ["River_Main",    "River_Gauge_A"],
        ["River_Gauge_A", "Reservoir_A"],
        ["Reservoir_A",   "River_Split_A"],
        # Split outputs
        ["River_Split_A", "Demand_Urban",      "urban_slot"],
        ["River_Split_A", "Demand_Irrigation", "irrigation_slot"],
        ["River_Split_A", "River_Outlet",      "outlet_slot"],
    ],
    "parameters": {},
    "recorders": {
        "GW_Base_flow": {
            "type":  "NumpyArrayNodeRecorder",
            "node":  "GW_Base",
        },
        "GW_Topup_flow": {
            "type":  "NumpyArrayNodeRecorder",
            "node":  "GW_Topup",
        },
        "GW_Total_flow": {
            "type":  "NumpyArrayNodeRecorder",
            "node":  "GW_Total",
        },
        "Urban_supply": {
            "type":  "NumpyArrayNodeRecorder",
            "node":  "Demand_Urban",
        },
        "Irrigation_supply": {
            "type":  "NumpyArrayNodeRecorder",
            "node":  "Demand_Irrigation",
        },
        "Reservoir_volume": {
            "type":  "NumpyArrayStorageRecorder",
            "node":  "Reservoir_A",
        },
    },
}

# ── Save the JSON model ─────────────────────────────────────────────────────

json_path = os.path.join(HERE, "pywr_model.json")
with open(json_path, "w") as f:
    json.dump(model, f, indent=2)
print(f"Model JSON written to: {json_path}")

# ── Step 2: Run the model (requires pywr) ───────────────────────────────────

try:
    import pandas as pd
    from pywr.model import Model

    print("\nLoading PyWR model...")
    m = Model.load(json_path, path=HERE)   # path= tells PyWR where to find params.csv

    print("Running simulation (2000-01-01 to 2000-12-31, monthly steps)...")
    m.run()

    print("\n── Results ────────────────────────────────────────────────────────")

    def get_flow(recorder_name):
        rec = m.recorders[recorder_name]
        return rec.data.flatten()

    dates = pd.date_range("2000-01-01", periods=12, freq="30D")

    results = pd.DataFrame({
        "GW_Base_Ml_d":        get_flow("GW_Base_flow"),
        "GW_Topup_Ml_d":       get_flow("GW_Topup_flow"),
        "GW_Total_Ml_d":       get_flow("GW_Total_flow"),
        "Urban_Supply_Ml_d":   get_flow("Urban_supply"),
        "Irrig_Supply_Ml_d":   get_flow("Irrigation_supply"),
        "Reservoir_Vol_Ml":    m.recorders["Reservoir_volume"].data.flatten(),
    }, index=dates)

    print(results.to_string())

    results_path = os.path.join(HERE, "results.csv")
    results.to_csv(results_path)
    print(f"\nResults saved to: {results_path}")

except ImportError:
    print(
        "\nPyWR is not installed — model JSON has been written successfully.\n"
        "To run the simulation:\n"
        "    pip install pywr\n"
        "    python run_example.py"
    )
except Exception as e:
    print(f"\nError running model: {e}")
    print("Model JSON is valid — check PyWR installation and params.csv path.")
