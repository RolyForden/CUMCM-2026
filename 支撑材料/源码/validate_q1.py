"""Independent validation, sensitivity, and robustness checks for C-Q1.

This script intentionally does not import the production ``core`` package.  It
reads the frozen CSV and official attachment directly, reconstructs all
identities, and solves an explicit-state mutually-exclusive MILP as an
alternative formulation.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import openpyxl
import pandas as pd
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, lil_matrix


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DISPATCH = PROJECT_ROOT / "outputs/q1_scheme_a/q1_dispatch.csv"
DEFAULT_RAW = PROJECT_ROOT / "data/raw/official/附件1.xlsm"
DEFAULT_WORKBOOK = PROJECT_ROOT / "outputs/q1_scheme_a/result1.xlsm"
DEFAULT_PAPER_TABLES = PROJECT_ROOT / "outputs/q1_scheme_a/q1_paper_tables.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/q1_validation"
DEFAULT_FIGURE_DIR = PROJECT_ROOT / "figures"

DT = 1.0 / 6.0
REQUIRED_COLUMNS = {
    "slot", "interval_start", "interval_end", "price", "load",
    "pv_available", "pv_used", "pv_curtail", "grid_contract",
    "grid_delivered", "grid_unused", "grid_emergency", "charge",
    "discharge", "soc_start", "soc_end", "normal_cost",
    "emergency_cost",
}


def load_dispatch(path: str | Path, expected_rows: int = 144) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")
    if len(frame) != expected_rows:
        raise ValueError(f"CSV rows {len(frame)} != {expected_rows}")
    slots = frame["slot"].astype(int).tolist()
    if slots != list(range(expected_rows)):
        raise ValueError("slot values must be unique, ordered, and contiguous")
    numeric = frame.select_dtypes(include=[np.number]).to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("CSV contains NaN or Inf")
    starts = pd.to_datetime(frame["interval_start"], errors="raise")
    ends = pd.to_datetime(frame["interval_end"], errors="raise")
    if not ((ends - starts) == pd.Timedelta(minutes=10)).all():
        raise ValueError("not every CSV interval is 10 minutes")
    if not (ends.iloc[:-1].reset_index(drop=True) == starts.iloc[1:].reset_index(drop=True)).all():
        raise ValueError("CSV intervals are not contiguous")
    return frame


def read_attachment1(path: str | Path) -> pd.DataFrame:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Sheet1 (2)"]
    rows = list(ws.iter_rows(min_row=2, max_row=145, min_col=1, max_col=4, values_only=True))
    wb.close()
    if len(rows) != 144:
        raise ValueError("attachment 1 does not contain 144 rows")
    frame = pd.DataFrame(rows, columns=["source_label", "raw_price", "raw_load_kw", "raw_pv_kw"])
    for column in ("raw_price", "raw_load_kw", "raw_pv_kw"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame[["raw_price", "raw_load_kw", "raw_pv_kw"]].isna().any().any():
        raise ValueError("attachment 1 contains missing numeric values")
    return frame


def _max_relative_error(actual: np.ndarray, expected: np.ndarray, threshold: float = 1e-12) -> float:
    mask = np.abs(expected) > threshold
    if not np.any(mask):
        return 0.0
    return float(np.max(np.abs(actual[mask] - expected[mask]) / np.abs(expected[mask])))


def independent_csv_audit(dispatch: pd.DataFrame, raw: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    if len(dispatch) != len(raw):
        raise ValueError("raw and CSV lengths differ")
    check = dispatch.copy()
    check["raw_price"] = raw["raw_price"].to_numpy(dtype=float)
    check["raw_load_kwh"] = raw["raw_load_kw"].to_numpy(dtype=float) * DT
    check["raw_pv_kwh"] = raw["raw_pv_kw"].to_numpy(dtype=float) * DT
    check["price_abs_error"] = np.abs(check["price"] - check["raw_price"])
    check["load_abs_error"] = np.abs(check["load"] - check["raw_load_kwh"])
    check["pv_abs_error"] = np.abs(check["pv_available"] - check["raw_pv_kwh"])
    check["balance_recomputed"] = (
        check["grid_delivered"] + check["pv_used"] + check["discharge"]
        - check["load"] - check["charge"]
    )
    check["soc_end_recomputed"] = check["soc_start"] + 0.9 * check["charge"] - check["discharge"] / 0.9
    check["soc_abs_error"] = np.abs(check["soc_end"] - check["soc_end_recomputed"])
    check["normal_cost_recomputed"] = check["price"] * check["grid_delivered"]
    check["cost_abs_error"] = np.abs(check["normal_cost"] - check["normal_cost_recomputed"])
    check["pv_identity_error"] = np.abs(check["pv_used"] + check["pv_curtail"] - check["pv_available"])

    soc_chain = np.abs(
        dispatch["soc_end"].to_numpy(dtype=float)[:-1]
        - dispatch["soc_start"].to_numpy(dtype=float)[1:]
    )
    total_cost_recomputed = float(check["normal_cost_recomputed"].sum() + check["emergency_cost"].sum())
    summary = {
        "rows": int(len(check)),
        "missing_values": int(dispatch.isna().sum().sum()),
        "duplicate_slots": int(dispatch["slot"].duplicated().sum()),
        "raw_price_max_abs_error": float(check["price_abs_error"].max()),
        "raw_load_max_abs_error_kwh": float(check["load_abs_error"].max()),
        "raw_pv_max_abs_error_kwh": float(check["pv_abs_error"].max()),
        "raw_load_max_relative_error": _max_relative_error(check["load"].to_numpy(), check["raw_load_kwh"].to_numpy()),
        "raw_pv_max_relative_error": _max_relative_error(check["pv_available"].to_numpy(), check["raw_pv_kwh"].to_numpy()),
        "energy_balance_max_abs_error_kwh": float(np.abs(check["balance_recomputed"]).max()),
        "soc_transition_max_abs_error_kwh": float(check["soc_abs_error"].max()),
        "soc_chain_max_abs_error_kwh": float(np.max(soc_chain)),
        "pv_identity_max_abs_error_kwh": float(check["pv_identity_error"].max()),
        "cost_row_max_abs_error_yuan": float(check["cost_abs_error"].max()),
        "cost_total_recomputed_yuan": total_cost_recomputed,
        "grid_total_recomputed_kwh": float(check["grid_delivered"].sum()),
        "soc_min_kwh": float(min(check["soc_start"].min(), check["soc_end"].min())),
        "soc_max_kwh": float(max(check["soc_start"].max(), check["soc_end"].max())),
        "soc_e0_kwh": float(check.iloc[0]["soc_start"]),
        "soc_e143_kwh": float(check.iloc[142]["soc_end"]),
        "soc_e144_kwh": float(check.iloc[143]["soc_end"]),
        "simultaneous_charge_discharge_slots": int(((check["charge"] > 1e-7) & (check["discharge"] > 1e-7)).sum()),
        "soc_bound_violations": int(((check[["soc_start", "soc_end"]] < 1200 - 1e-7) | (check[["soc_start", "soc_end"]] > 10800 + 1e-7)).sum().sum()),
        "power_bound_violations": int(((check[["charge", "discharge"]] < -1e-9) | (check[["charge", "discharge"]] > 5000 * DT + 1e-7)).sum().sum()),
        "q1_semantic_violations": int(
            (np.abs(check["grid_contract"] - check["grid_delivered"]) > 1e-7).sum()
            + (np.abs(check["grid_unused"]) > 1e-9).sum()
            + (np.abs(check["grid_emergency"]) > 1e-9).sum()
        ),
    }

    net = check["load"] - check["pv_available"]
    typical = int((net - net.median()).abs().idxmin())
    selected = {
        0, 142, 143, typical, int(check["load"].idxmax()),
        int(check["price"].idxmax()), int(check["soc_end"].idxmin()),
        int(check["soc_end"].idxmax()),
    }
    selected.update(np.random.default_rng(20260912).choice(len(check), size=5, replace=False).tolist())
    sample_columns = [
        "slot", "interval_start", "interval_end", "price", "load", "pv_available",
        "grid_delivered", "charge", "discharge", "soc_start", "soc_end",
        "balance_recomputed", "soc_abs_error", "cost_abs_error",
    ]
    samples = check.loc[sorted(selected), sample_columns].copy()
    return summary, check, samples


def solve_explicit_milp(
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    eta_charge: float = 0.9,
    eta_discharge: float = 0.9,
    soc_min: float = 1200.0,
    soc_max: float = 10800.0,
    energy_limit: float = 5000.0 / 6.0,
    soc0: float = 6000.0,
    mutual_exclusion: bool = True,
) -> dict:
    price = np.asarray(price, dtype=float)
    load = np.asarray(load, dtype=float)
    pv = np.asarray(pv, dtype=float)
    n = len(price)
    if load.shape != (n,) or pv.shape != (n,):
        raise ValueError("price, load, and pv must have equal one-dimensional shapes")

    g0, v0, c0, d0, e0, z0 = 0, n, 2 * n, 3 * n, 4 * n, 5 * n + 1
    nv = 6 * n + 1
    objective = np.zeros(nv)
    objective[g0:g0 + n] = price

    lower = np.zeros(nv)
    upper = np.full(nv, np.inf)
    upper[v0:v0 + n] = pv
    upper[c0:c0 + n] = energy_limit
    upper[d0:d0 + n] = energy_limit
    lower[e0:e0 + n + 1] = soc_min
    upper[e0:e0 + n + 1] = soc_max
    upper[z0:z0 + n] = 1.0
    integrality = np.zeros(nv, dtype=int)
    if mutual_exclusion:
        integrality[z0:z0 + n] = 1

    aeq = lil_matrix((2 * n + 2, nv))
    beq = np.zeros(2 * n + 2)
    for t in range(n):
        aeq[t, g0 + t] = 1.0
        aeq[t, v0 + t] = 1.0
        aeq[t, c0 + t] = -1.0
        aeq[t, d0 + t] = 1.0
        beq[t] = load[t]
        row = n + t
        aeq[row, e0 + t + 1] = 1.0
        aeq[row, e0 + t] = -1.0
        aeq[row, c0 + t] = -eta_charge
        aeq[row, d0 + t] = 1.0 / eta_discharge
    aeq[2 * n, e0] = 1.0
    beq[2 * n] = soc0
    aeq[2 * n + 1, e0 + n] = 1.0
    beq[2 * n + 1] = soc0

    aub = lil_matrix((2 * n, nv))
    bub = np.zeros(2 * n)
    for t in range(n):
        aub[2 * t, c0 + t] = 1.0
        aub[2 * t, z0 + t] = -energy_limit
        aub[2 * t + 1, d0 + t] = 1.0
        aub[2 * t + 1, z0 + t] = energy_limit
        bub[2 * t + 1] = energy_limit

    constraints = [
        LinearConstraint(csr_matrix(aeq), beq, beq),
        LinearConstraint(csr_matrix(aub), np.full(2 * n, -np.inf), bub),
    ]
    primary = milp(
        objective,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints,
        options={"mip_rel_gap": 1e-10, "time_limit": 120.0},
    )
    if not primary.success:
        return {"success": False, "status": int(primary.status), "message": primary.message}

    throughput = np.zeros(nv)
    throughput[c0:c0 + n] = 1.0
    throughput[d0:d0 + n] = 1.0
    cost_limit = LinearConstraint(csr_matrix(objective.reshape(1, -1)), -np.inf, float(primary.fun) + 1e-7)
    secondary = milp(
        throughput,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints + [cost_limit],
        options={"mip_rel_gap": 1e-10, "time_limit": 120.0},
    )
    result = secondary if secondary.success else primary
    x = result.x
    grid = x[g0:g0 + n]
    pv_used = x[v0:v0 + n]
    charge = x[c0:c0 + n]
    discharge = x[d0:d0 + n]
    soc = x[e0:e0 + n + 1]
    return {
        "success": True,
        "status": int(result.status),
        "message": result.message,
        "primary_cost": float(primary.fun),
        "cost": float(np.dot(price, grid)),
        "grid": grid,
        "pv_used": pv_used,
        "pv_curtail": pv - pv_used,
        "charge": charge,
        "discharge": discharge,
        "soc": soc,
        "throughput": float(charge.sum() + discharge.sum()),
    }


def no_storage_cost(price: np.ndarray, load: np.ndarray, pv: np.ndarray) -> tuple[float, float]:
    grid = np.maximum(load - pv, 0.0)
    return float(np.dot(price, grid)), float(grid.sum())


def parameter_sensitivity(price: np.ndarray, load: np.ndarray, pv: np.ndarray) -> pd.DataFrame:
    scenarios = [
        ("base", "base", 1.0, dict()),
        ("soc0", "1200 kWh", 1200.0, {"soc0": 1200.0}),
        ("soc0", "6000 kWh", 6000.0, {"soc0": 6000.0}),
        ("soc0", "10800 kWh", 10800.0, {"soc0": 10800.0}),
        ("efficiency", "eta=0.855 (-5%)", 0.855, {"eta_charge": 0.855, "eta_discharge": 0.855}),
        ("efficiency", "eta=0.900", 0.9, {"eta_charge": 0.9, "eta_discharge": 0.9}),
        ("efficiency", "eta=sqrt(0.9)", math.sqrt(0.9), {"eta_charge": math.sqrt(0.9), "eta_discharge": math.sqrt(0.9)}),
        ("efficiency", "eta=0.945 (+5%)", 0.945, {"eta_charge": 0.945, "eta_discharge": 0.945}),
        ("power", "4000 kW (-20%)", 4000.0, {"energy_limit": 4000.0 * DT}),
        ("power", "5000 kW", 5000.0, {"energy_limit": 5000.0 * DT}),
        ("power", "6000 kW (+20%)", 6000.0, {"energy_limit": 6000.0 * DT}),
    ]
    baseline_cost, _ = no_storage_cost(price, load, pv)
    rows = []
    for group, label, value, kwargs in scenarios:
        result = solve_explicit_milp(price, load, pv, **kwargs)
        if not result["success"]:
            raise RuntimeError(f"sensitivity scenario failed: {label}: {result['message']}")
        rows.append(
            {
                "group": group,
                "scenario": label,
                "value": value,
                "cost_yuan": result["cost"],
                "grid_total_kwh": float(result["grid"].sum()),
                "charge_total_kwh": float(result["charge"].sum()),
                "discharge_total_kwh": float(result["discharge"].sum()),
                "soc_min_kwh": float(result["soc"].min()),
                "soc_max_kwh": float(result["soc"].max()),
                "saving_vs_no_storage_pct": 100.0 * (baseline_cost - result["cost"]) / baseline_cost,
            }
        )
    frame = pd.DataFrame(rows)
    base_cost = float(frame.loc[frame["scenario"] == "base", "cost_yuan"].iloc[0])
    frame["cost_change_vs_base_pct"] = 100.0 * (frame["cost_yuan"] - base_cost) / base_cost
    return frame


def _ar1_noise(rng: np.random.Generator, n: int, sigma: float, rho: float = 0.85) -> np.ndarray:
    innovations = rng.normal(0.0, sigma * math.sqrt(1.0 - rho * rho), n)
    out = np.zeros(n)
    out[0] = rng.normal(0.0, sigma)
    for i in range(1, n):
        out[i] = rho * out[i - 1] + innovations[i]
    return np.clip(out, -2.0 * sigma, 2.0 * sigma)


def robustness_stress(price: np.ndarray, load: np.ndarray, pv: np.ndarray, trials: int = 20) -> pd.DataFrame:
    rows = []
    for level in (0.01, 0.03, 0.05):
        for seed_offset in range(trials):
            seed = 20260912 + seed_offset + int(level * 10000)
            rng = np.random.default_rng(seed)
            load_test = np.maximum(load * (1.0 + _ar1_noise(rng, len(load), level)), 0.0)
            pv_test = np.maximum(pv * (1.0 + _ar1_noise(rng, len(pv), level)), 0.0)
            result = solve_explicit_milp(price, load_test, pv_test, mutual_exclusion=False)
            if not result["success"]:
                raise RuntimeError(f"robustness trial failed: level={level}, seed={seed}")
            baseline_cost, baseline_grid = no_storage_cost(price, load_test, pv_test)
            rows.append(
                {
                    "noise_level_pct": 100.0 * level,
                    "seed": seed,
                    "cost_yuan": result["cost"],
                    "grid_total_kwh": float(result["grid"].sum()),
                    "no_storage_cost_yuan": baseline_cost,
                    "no_storage_grid_kwh": baseline_grid,
                    "saving_vs_no_storage_pct": 100.0 * (baseline_cost - result["cost"]) / baseline_cost,
                    "soc_min_kwh": float(result["soc"].min()),
                    "soc_max_kwh": float(result["soc"].max()),
                    "simultaneous_slots": int(np.sum((result["charge"] > 1e-7) & (result["discharge"] > 1e-7))),
                }
            )
    return pd.DataFrame(rows)


def verify_exports(dispatch: pd.DataFrame, workbook_path: Path, paper_tables_path: Path) -> dict:
    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True, keep_vba=True)
    ws = wb["计划购电量"]
    workbook_grid = np.array([float(ws.cell(row=i + 2, column=2).value) for i in range(144)])
    wb.close()
    paper = json.loads(paper_tables_path.read_text(encoding="utf-8"))
    grid = dispatch["grid_delivered"].to_numpy(dtype=float)
    selected = {"10:00-10:10": 59, "12:00-12:10": 71, "14:00-14:10": 83,
                "16:00-16:10": 95, "18:00-18:10": 107, "20:00-20:10": 119}
    table1_errors = [abs(float(paper["table1"][name]) - grid[k]) for name, k in selected.items()]
    block_errors = []
    for i, block in enumerate(paper["table2"]["blocks"]):
        block_errors.append(abs(float(block["charge"]) - float(dispatch["charge"].iloc[i * 24:(i + 1) * 24].sum())))
        block_errors.append(abs(float(block["discharge"]) - float(dispatch["discharge"].iloc[i * 24:(i + 1) * 24].sum())))
    return {
        "workbook_grid_max_abs_error_kwh": float(np.max(np.abs(workbook_grid - grid))),
        "paper_table1_max_abs_error": float(max(table1_errors)),
        "paper_total_grid_abs_error_kwh": abs(float(paper["table1"]["全天购电量"]) - float(grid.sum())),
        "paper_total_cost_abs_error_yuan": abs(float(paper["table1"]["全天购电费"]) - float(dispatch["normal_cost"].sum())),
        "paper_block_max_abs_error_kwh": float(max(block_errors)),
        "paper_soc_0000_abs_error_kwh": abs(float(paper["table2"]["soc_0000"]) - float(dispatch.iloc[0]["soc_start"])),
        "paper_soc_2400_abs_error_kwh": abs(float(paper["table2"]["soc_2400"]) - float(dispatch.iloc[142]["soc_end"])),
    }


def make_figures(dispatch: pd.DataFrame, alt: dict, sensitivity: pd.DataFrame, robustness: pd.DataFrame, figure_dir: Path) -> list[str]:
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from core.figure_style import configure_chinese_font

    configure_chinese_font()
    figure_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    grid_main = dispatch["grid_delivered"].to_numpy(dtype=float)
    soc_main = np.r_[dispatch.iloc[0]["soc_start"], dispatch["soc_end"].to_numpy(dtype=float)]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
    axes[0].scatter(grid_main, alt["grid"], s=14, alpha=0.7)
    bound = max(float(grid_main.max()), float(alt["grid"].max()))
    axes[0].plot([0, bound], [0, bound], "k--", linewidth=1)
    axes[0].set(xlabel="计划LP购电量（kWh）", ylabel="显式互斥MILP购电量（kWh）", title="逐槽购电量对比")
    axes[1].plot(soc_main, label="主LP", linewidth=1.8)
    axes[1].plot(alt["soc"], "--", label="显式互斥MILP", linewidth=1.4)
    axes[1].axhline(1200, color="grey", linewidth=0.8)
    axes[1].axhline(10800, color="grey", linewidth=0.8)
    axes[1].set(xlabel="时步索引", ylabel="储电量（kWh）", title="储电量轨迹")
    axes[1].legend(frameon=False)
    path = figure_dir / "q1_alternative_validation.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    paths.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
    plot_data = sensitivity[sensitivity["scenario"] != "base"]
    axes[0].barh(plot_data["scenario"], plot_data["cost_change_vs_base_pct"])
    axes[0].axvline(0, color="black", linewidth=0.8)
    axes[0].set(xlabel="费用相对基准变化（%）", title="参数敏感性")
    groups = [g["cost_yuan"].to_numpy() for _, g in robustness.groupby("noise_level_pct")]
    labels = [f"{level:g}%" for level in sorted(robustness["noise_level_pct"].unique())]
    axes[1].boxplot(groups, tick_labels=labels, showmeans=True)
    axes[1].set(xlabel="负荷与光伏相关扰动幅度", ylabel="最优费用（元）", title="输入稳健性")
    path = figure_dir / "q1_sensitivity_robustness.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    paths.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dispatch", type=Path, default=DEFAULT_DISPATCH)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--paper-tables", type=Path, default=DEFAULT_PAPER_TABLES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    parser.add_argument("--robustness-trials", type=int, default=20)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    dispatch = load_dispatch(args.dispatch)
    raw = read_attachment1(args.raw)
    independent, full_check, samples = independent_csv_audit(dispatch, raw)
    exports = verify_exports(dispatch, args.workbook, args.paper_tables)
    price = dispatch["price"].to_numpy(dtype=float)
    load = dispatch["load"].to_numpy(dtype=float)
    pv = dispatch["pv_available"].to_numpy(dtype=float)
    alt = solve_explicit_milp(price, load, pv)
    if not alt["success"]:
        raise RuntimeError(f"alternative MILP failed: {alt['message']}")
    main_grid = dispatch["grid_delivered"].to_numpy(dtype=float)
    main_soc = np.r_[dispatch.iloc[0]["soc_start"], dispatch["soc_end"].to_numpy(dtype=float)]
    main_cost = float(dispatch["normal_cost"].sum())
    alternative_summary = {
        "method": "explicit SOC MILP with binary charge/discharge exclusion",
        "cost_yuan": alt["cost"],
        "cost_abs_difference_yuan": abs(alt["cost"] - main_cost),
        "cost_relative_difference": abs(alt["cost"] - main_cost) / main_cost,
        "grid_mae_kwh": float(np.mean(np.abs(alt["grid"] - main_grid))),
        "grid_rmse_kwh": float(np.sqrt(np.mean((alt["grid"] - main_grid) ** 2))),
        "grid_max_abs_difference_kwh": float(np.max(np.abs(alt["grid"] - main_grid))),
        "grid_pearson": float(np.corrcoef(main_grid, alt["grid"])[0, 1]),
        "soc_max_abs_difference_kwh": float(np.max(np.abs(alt["soc"] - main_soc))),
        "simultaneous_charge_discharge_slots": int(np.sum((alt["charge"] > 1e-7) & (alt["discharge"] > 1e-7))),
        "terminal_soc_abs_error_kwh": abs(float(alt["soc"][-1]) - 6000.0),
    }
    baseline_cost, baseline_grid = no_storage_cost(price, load, pv)
    baseline = {
        "cost_yuan": baseline_cost,
        "grid_total_kwh": baseline_grid,
        "saving_yuan": baseline_cost - main_cost,
        "saving_pct": 100.0 * (baseline_cost - main_cost) / baseline_cost,
    }
    sensitivity = parameter_sensitivity(price, load, pv)
    robustness = robustness_stress(price, load, pv, trials=args.robustness_trials)

    full_check.to_csv(args.output_dir / "q1_independent_recheck.csv", index=False, encoding="utf-8-sig")
    samples.to_csv(args.output_dir / "q1_sample_recheck.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        {
            "slot": dispatch["slot"],
            "main_grid_kwh": main_grid,
            "alternative_grid_kwh": alt["grid"],
            "grid_abs_difference_kwh": np.abs(main_grid - alt["grid"]),
            "main_soc_end_kwh": dispatch["soc_end"],
            "alternative_soc_end_kwh": alt["soc"][1:],
        }
    ).to_csv(args.output_dir / "q1_alternative_comparison.csv", index=False, encoding="utf-8-sig")
    sensitivity.to_csv(args.output_dir / "q1_sensitivity.csv", index=False, encoding="utf-8-sig")
    robustness.to_csv(args.output_dir / "q1_robustness.csv", index=False, encoding="utf-8-sig")
    figures = make_figures(dispatch, alt, sensitivity, robustness, args.figure_dir)

    robustness_summary = []
    for level, group in robustness.groupby("noise_level_pct"):
        robustness_summary.append(
            {
                "noise_level_pct": float(level),
                "trials": int(len(group)),
                "cost_mean_yuan": float(group["cost_yuan"].mean()),
                "cost_std_yuan": float(group["cost_yuan"].std(ddof=1)),
                "cost_min_yuan": float(group["cost_yuan"].min()),
                "cost_max_yuan": float(group["cost_yuan"].max()),
                "saving_vs_no_storage_min_pct": float(group["saving_vs_no_storage_pct"].min()),
                "saving_vs_no_storage_max_pct": float(group["saving_vs_no_storage_pct"].max()),
                "simultaneous_slots_max": int(group["simultaneous_slots"].max()),
            }
        )
    summary = {
        "status": "PASS",
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "pandas": pd.__version__},
        "scope": "D003 scheme A; validation does not alter the production model or CSV",
        "traditional_kfold": "not applicable: Q1 is deterministic optimization with no fitted predictor or estimated parameter",
        "independent_csv_audit": independent,
        "export_consistency": exports,
        "alternative_method": alternative_summary,
        "no_storage_baseline": baseline,
        "sensitivity": sensitivity.to_dict(orient="records"),
        "robustness": robustness_summary,
        "figures": figures,
    }
    hard_values = [
        independent["missing_values"], independent["duplicate_slots"], independent["soc_bound_violations"],
        independent["power_bound_violations"], independent["q1_semantic_violations"],
        independent["simultaneous_charge_discharge_slots"],
    ]
    tolerances_ok = (
        max(hard_values) == 0
        and independent["raw_price_max_abs_error"] < 1e-12
        and independent["raw_load_max_abs_error_kwh"] < 1e-9
        and independent["raw_pv_max_abs_error_kwh"] < 1e-9
        and independent["energy_balance_max_abs_error_kwh"] < 1e-9
        and independent["soc_transition_max_abs_error_kwh"] < 1e-9
        and independent["soc_chain_max_abs_error_kwh"] < 1e-9
        and max(exports.values()) < 1e-9
        and alternative_summary["cost_abs_difference_yuan"] < 1e-4
        and alternative_summary["terminal_soc_abs_error_kwh"] < 1e-6
    )
    summary["status"] = "PASS" if tolerances_ok else "FAIL"
    (args.output_dir / "q1_validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": summary["status"],
        "main_cost_yuan": main_cost,
        "alternative_cost_yuan": alt["cost"],
        "alternative_cost_abs_difference_yuan": alternative_summary["cost_abs_difference_yuan"],
        "no_storage_saving_pct": baseline["saving_pct"],
        "output": str((args.output_dir / "q1_validation_summary.json").relative_to(PROJECT_ROOT)),
    }, ensure_ascii=False, indent=2))
    return 0 if tolerances_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
