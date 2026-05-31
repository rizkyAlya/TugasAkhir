#!/usr/bin/env python3
r"""
Analyze DT voltage drift and false control actions from Graphs/Data host CSV logs.

Run from project root:
    python .\Fix\Graphs\Script\analyze_dt_drift_control.py

DoS only:
    python .\Fix\Graphs\Script\analyze_dt_drift_control.py --scenarios baseline dos_light dos_heavy

MITM only:
    python .\Fix\Graphs\Script\analyze_dt_drift_control.py --scenarios baseline mitm

Outputs:
- Graphs/Join/dt_drift_detail.csv
- Graphs/Join/dt_drift_iteration_summary.csv
- Graphs/Join/dt_drift_scenario_summary.csv
- Graphs/Join/false_control_detail.csv
- Graphs/Join/false_control_iteration_summary.csv
- Graphs/Join/false_control_scenario_summary.csv

Assumption for false control action:
    A DT control action is false when H4 breaker_DT differs from the field
    breaker_actual in H1 for the same origin_cycle and bus.
"""
import argparse
import csv
import statistics
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
GRAPHS_DIR = SCRIPT_DIR.parent
DEFAULT_DATA_DIR = GRAPHS_DIR / "Data"
DEFAULT_OUTPUT_DIR = GRAPHS_DIR / "Join"

SCENARIO_PATHS = [
    ("baseline", Path("Baseline") / "host_csv"),
    ("dos_light", Path("DoS") / "host_csv" / "dos_light"),
    ("dos_heavy", Path("DoS") / "host_csv" / "dos_heavy"),
    ("mitm", Path("MITM") / "host_csv"),
]

DRIFT_DETAIL_COLUMNS = [
    "scenario",
    "iteration",
    "cycle_id",
    "bus",
    "v_field_pu",
    "v_dt_pu",
    "drift_signed_pu",
    "drift_abs_pu",
    "drift_pct",
]

DRIFT_ITERATION_COLUMNS = [
    "scenario",
    "iteration",
    "matched_points",
    "missing_h4_points",
    "drift_abs_mean_pu",
    "drift_abs_std_dev_pu",
    "drift_abs_max_pu",
    "drift_pct_mean",
    "drift_pct_std_dev",
]

DRIFT_SCENARIO_COLUMNS = [
    "scenario",
    "iteration_count",
    "matched_points_sum",
    "missing_h4_points_sum",
    "drift_abs_mean_pu_mean",
    "drift_abs_mean_pu_std_dev",
    "drift_abs_std_dev_pu_mean",
    "drift_abs_std_dev_pu_std_dev",
    "drift_abs_max_pu_max",
    "drift_pct_mean_mean",
    "drift_pct_mean_std_dev",
]

CONTROL_DETAIL_COLUMNS = [
    "scenario",
    "iteration",
    "cmd_id",
    "origin_cycle",
    "bus",
    "field_breaker_actual",
    "dt_breaker_cmd",
    "false_control_action",
]

CONTROL_ITERATION_COLUMNS = [
    "scenario",
    "iteration",
    "matched_decisions",
    "false_control_count",
    "missing_field_decision_count",
    "decision_error_rate_pct",
]

CONTROL_SCENARIO_COLUMNS = [
    "scenario",
    "iteration_count",
    "matched_decisions_sum",
    "false_control_count_sum",
    "missing_field_decision_count_sum",
    "decision_error_rate_pct_mean",
    "decision_error_rate_pct_std_dev",
]

HEADER_LABELS = {
    "scenario": "scenario (-)",
    "iteration": "iteration (-)",
    "cycle_id": "cycle_id (-)",
    "origin_cycle": "origin_cycle (-)",
    "cmd_id": "cmd_id (-)",
    "bus": "bus (-)",
    "v_field_pu": "v_field (pu)",
    "v_dt_pu": "v_dt (pu)",
    "drift_signed_pu": "drift_signed (pu)",
    "drift_abs_pu": "drift_abs (pu)",
    "drift_pct": "drift (%)",
    "matched_points": "matched_points (count)",
    "missing_h4_points": "missing_h4_points (count)",
    "drift_abs_mean_pu": "drift_abs_mean (pu)",
    "drift_abs_std_dev_pu": "drift_abs_std_dev (pu)",
    "drift_abs_max_pu": "drift_abs_max (pu)",
    "drift_pct_mean": "drift_mean (%)",
    "drift_pct_std_dev": "drift_std_dev (%)",
    "iteration_count": "iteration_count (count)",
    "matched_points_sum": "matched_points_sum (count)",
    "missing_h4_points_sum": "missing_h4_points_sum (count)",
    "drift_abs_mean_pu_mean": "drift_abs_mean_mean (pu)",
    "drift_abs_mean_pu_std_dev": "drift_abs_mean_std_dev (pu)",
    "drift_abs_std_dev_pu_mean": "drift_abs_std_dev_mean (pu)",
    "drift_abs_std_dev_pu_std_dev": "drift_abs_std_dev_std_dev (pu)",
    "drift_abs_max_pu_max": "drift_abs_max_max (pu)",
    "drift_pct_mean_mean": "drift_mean_mean (%)",
    "drift_pct_mean_std_dev": "drift_mean_std_dev (%)",
    "field_breaker_actual": "field_breaker_actual (-)",
    "dt_breaker_cmd": "dt_breaker_cmd (-)",
    "false_control_action": "false_control_action (-)",
    "matched_decisions": "matched_decisions (count)",
    "false_control_count": "false_control_count (count)",
    "missing_field_decision_count": "missing_field_decision_count (count)",
    "decision_error_rate_pct": "decision_error_rate (%)",
    "matched_decisions_sum": "matched_decisions_sum (count)",
    "false_control_count_sum": "false_control_count_sum (count)",
    "missing_field_decision_count_sum": "missing_field_decision_count_sum (count)",
    "decision_error_rate_pct_mean": "decision_error_rate_mean (%)",
    "decision_error_rate_pct_std_dev": "decision_error_rate_std_dev (%)",
}


def display_header(column):
    return HEADER_LABELS.get(column, column)


def fmt_float(value, digits=6):
    if value == "":
        return ""
    return f"{float(value):.{digits}f}"


def mean(values):
    return statistics.fmean(values) if values else 0.0


def std_dev(values):
    return statistics.stdev(values) if len(values) > 1 else 0.0


def iteration_sort_key(path):
    try:
        return int(path.name.split("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def selected_cycle_ids(cycle_ids, start_cycle=None, limit_cycles=None):
    selected = sorted(cycle_ids)
    if start_cycle is not None:
        selected = [cycle_id for cycle_id in selected if cycle_id >= start_cycle]
    if limit_cycles is not None:
        selected = selected[:limit_cycles]
    return selected


def read_h1_data(path):
    rows = {}
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cycle_id = int(row["cycle_id"])
                bus = int(row["bus"])
                v_sent = float(row["V_sent"])
                breaker_actual = int(row["breaker_actual"])
            except (KeyError, ValueError):
                continue
            rows[(cycle_id, bus)] = {
                "v_sent": v_sent,
                "breaker_actual": breaker_actual,
            }
    return rows


def read_h4_data(path):
    rows = {}
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cycle_id = int(row["cycle_id"])
                bus = int(row["bus"])
                v_dt = float(row["V_DT"])
            except (KeyError, ValueError):
                continue
            rows[(cycle_id, bus)] = {"v_dt": v_dt}
    return rows


def read_h4_control(path):
    rows = {}
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                origin_cycle = int(row["origin_cycle"])
                bus = int(row["bus"])
                cmd_id = int(row["cmd_id"])
                breaker_dt = int(row["breaker_DT"])
            except (KeyError, ValueError):
                continue
            rows[(origin_cycle, bus)] = {
                "cmd_id": cmd_id,
                "breaker_dt": breaker_dt,
            }
    return rows


def analyze_drift(scenario, iteration_dir, h1_rows, h4_rows, start_cycle, limit_cycles):
    h1_cycle_ids = {cycle_id for cycle_id, _bus in h1_rows}
    cycle_ids = selected_cycle_ids(h1_cycle_ids, start_cycle, limit_cycles)
    detail_rows = []
    drift_abs_values = []
    drift_pct_values = []
    missing_h4 = 0

    for cycle_id in cycle_ids:
        for bus in range(1, 6):
            h1 = h1_rows.get((cycle_id, bus))
            if h1 is None:
                continue
            h4 = h4_rows.get((cycle_id, bus))
            if h4 is None:
                missing_h4 += 1
                continue

            v_field = h1["v_sent"]
            v_dt = h4["v_dt"]
            drift_signed = v_dt - v_field
            drift_abs = abs(drift_signed)
            drift_pct = drift_abs / abs(v_field) * 100 if abs(v_field) > 1e-12 else 0.0

            drift_abs_values.append(drift_abs)
            drift_pct_values.append(drift_pct)
            detail_rows.append(
                {
                    "scenario": scenario,
                    "iteration": iteration_dir.name,
                    "cycle_id": cycle_id,
                    "bus": bus,
                    "v_field_pu": fmt_float(v_field),
                    "v_dt_pu": fmt_float(v_dt),
                    "drift_signed_pu": fmt_float(drift_signed),
                    "drift_abs_pu": fmt_float(drift_abs),
                    "drift_pct": fmt_float(drift_pct),
                }
            )

    summary = {
        "scenario": scenario,
        "iteration": iteration_dir.name,
        "matched_points": len(drift_abs_values),
        "missing_h4_points": missing_h4,
        "drift_abs_mean_pu": fmt_float(mean(drift_abs_values)),
        "drift_abs_std_dev_pu": fmt_float(std_dev(drift_abs_values)),
        "drift_abs_max_pu": fmt_float(max(drift_abs_values) if drift_abs_values else 0.0),
        "drift_pct_mean": fmt_float(mean(drift_pct_values)),
        "drift_pct_std_dev": fmt_float(std_dev(drift_pct_values)),
    }
    return detail_rows, summary


def analyze_control(scenario, iteration_dir, h1_rows, h4_control_rows, start_cycle, limit_cycles):
    h1_cycle_ids = {cycle_id for cycle_id, _bus in h1_rows}
    cycle_ids = set(selected_cycle_ids(h1_cycle_ids, start_cycle, limit_cycles))
    detail_rows = []
    false_count = 0
    matched_decisions = 0
    missing_field = 0

    for (origin_cycle, bus), ctrl in sorted(h4_control_rows.items()):
        if origin_cycle not in cycle_ids:
            continue

        h1 = h1_rows.get((origin_cycle, bus))
        if h1 is None:
            missing_field += 1
            continue

        matched_decisions += 1
        field_actual = h1["breaker_actual"]
        dt_cmd = ctrl["breaker_dt"]
        is_false = int(dt_cmd != field_actual)
        false_count += is_false
        detail_rows.append(
            {
                "scenario": scenario,
                "iteration": iteration_dir.name,
                "cmd_id": ctrl["cmd_id"],
                "origin_cycle": origin_cycle,
                "bus": bus,
                "field_breaker_actual": field_actual,
                "dt_breaker_cmd": dt_cmd,
                "false_control_action": is_false,
            }
        )

    error_rate = false_count / matched_decisions * 100 if matched_decisions else 0.0
    summary = {
        "scenario": scenario,
        "iteration": iteration_dir.name,
        "matched_decisions": matched_decisions,
        "false_control_count": false_count,
        "missing_field_decision_count": missing_field,
        "decision_error_rate_pct": fmt_float(error_rate),
    }
    return detail_rows, summary


def summarize_drift_scenario(scenario, rows):
    items = [row for row in rows if row["scenario"] == scenario]
    if not items:
        return None

    def values(column):
        return [float(row[column]) for row in items]

    return {
        "scenario": scenario,
        "iteration_count": len(items),
        "matched_points_sum": sum(int(row["matched_points"]) for row in items),
        "missing_h4_points_sum": sum(int(row["missing_h4_points"]) for row in items),
        "drift_abs_mean_pu_mean": fmt_float(mean(values("drift_abs_mean_pu"))),
        "drift_abs_mean_pu_std_dev": fmt_float(std_dev(values("drift_abs_mean_pu"))),
        "drift_abs_std_dev_pu_mean": fmt_float(mean(values("drift_abs_std_dev_pu"))),
        "drift_abs_std_dev_pu_std_dev": fmt_float(std_dev(values("drift_abs_std_dev_pu"))),
        "drift_abs_max_pu_max": fmt_float(max(values("drift_abs_max_pu"))),
        "drift_pct_mean_mean": fmt_float(mean(values("drift_pct_mean"))),
        "drift_pct_mean_std_dev": fmt_float(std_dev(values("drift_pct_mean"))),
    }


def summarize_control_scenario(scenario, rows):
    items = [row for row in rows if row["scenario"] == scenario]
    if not items:
        return None

    rates = [float(row["decision_error_rate_pct"]) for row in items]
    return {
        "scenario": scenario,
        "iteration_count": len(items),
        "matched_decisions_sum": sum(int(row["matched_decisions"]) for row in items),
        "false_control_count_sum": sum(int(row["false_control_count"]) for row in items),
        "missing_field_decision_count_sum": sum(
            int(row["missing_field_decision_count"]) for row in items
        ),
        "decision_error_rate_pct_mean": fmt_float(mean(rates)),
        "decision_error_rate_pct_std_dev": fmt_float(std_dev(rates)),
    }


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [display_header(column) for column in columns]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({display_header(column): row.get(column, "") for column in columns})


def default_output_dir_for_scenarios(scenarios):
    selected = set(scenarios)
    has_dos = bool(selected & {"dos_light", "dos_heavy"})
    has_mitm = "mitm" in selected
    if has_dos and not has_mitm:
        return DEFAULT_OUTPUT_DIR / "dos"
    if has_mitm and not has_dos:
        return DEFAULT_OUTPUT_DIR / "mitm"
    return DEFAULT_OUTPUT_DIR


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze DT voltage drift and false control actions."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Graphs/Data folder containing Baseline, DoS, and MITM.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder for output CSV files.",
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=[scenario for scenario, _rel_path in SCENARIO_PATHS],
        default=[scenario for scenario, _rel_path in SCENARIO_PATHS],
        help="Scenarios to analyze.",
    )
    parser.add_argument(
        "--start-cycle",
        type=int,
        default=None,
        help="Only analyze cycle_id values greater than or equal to this value.",
    )
    parser.add_argument(
        "--limit-cycles",
        type=int,
        default=None,
        help="Analyze only the first N selected cycle_id values per iteration.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    data_dir = args.data_dir.resolve()
    output_dir = (
        default_output_dir_for_scenarios(args.scenarios)
        if args.output_dir == DEFAULT_OUTPUT_DIR
        else args.output_dir
    ).resolve()
    selected_scenarios = set(args.scenarios)

    drift_detail_rows = []
    drift_iteration_rows = []
    control_detail_rows = []
    control_iteration_rows = []
    warnings = []

    for scenario, rel_path in SCENARIO_PATHS:
        if scenario not in selected_scenarios:
            continue
        scenario_dir = data_dir / rel_path
        if not scenario_dir.exists():
            warnings.append(f"missing scenario folder: {scenario_dir}")
            continue

        iteration_dirs = sorted(
            [path for path in scenario_dir.glob("iteration_*") if path.is_dir()],
            key=iteration_sort_key,
        )
        for iteration_dir in iteration_dirs:
            if iteration_sort_key(iteration_dir) <= 0:
                continue

            h1_data_path = iteration_dir / "data_plane" / "h1.csv"
            h4_data_path = iteration_dir / "data_plane" / "h4.csv"
            h4_control_path = iteration_dir / "control_plane" / "h4.csv"
            if not h1_data_path.exists() or not h4_data_path.exists():
                warnings.append(f"missing drift input in {iteration_dir}")
                continue
            if not h4_control_path.exists():
                warnings.append(f"missing control input in {iteration_dir}")
                continue

            h1_rows = read_h1_data(h1_data_path)
            h4_rows = read_h4_data(h4_data_path)
            h4_control_rows = read_h4_control(h4_control_path)

            detail, summary = analyze_drift(
                scenario,
                iteration_dir,
                h1_rows,
                h4_rows,
                args.start_cycle,
                args.limit_cycles,
            )
            drift_detail_rows.extend(detail)
            drift_iteration_rows.append(summary)

            control_detail, control_summary = analyze_control(
                scenario,
                iteration_dir,
                h1_rows,
                h4_control_rows,
                args.start_cycle,
                args.limit_cycles,
            )
            control_detail_rows.extend(control_detail)
            control_iteration_rows.append(control_summary)

    scenario_order = [scenario for scenario, _rel_path in SCENARIO_PATHS if scenario in selected_scenarios]
    drift_scenario_rows = [
        row
        for scenario in scenario_order
        if (row := summarize_drift_scenario(scenario, drift_iteration_rows))
    ]
    control_scenario_rows = [
        row
        for scenario in scenario_order
        if (row := summarize_control_scenario(scenario, control_iteration_rows))
    ]

    write_csv(output_dir / "dt_drift_detail.csv", DRIFT_DETAIL_COLUMNS, drift_detail_rows)
    write_csv(
        output_dir / "dt_drift_iteration_summary.csv",
        DRIFT_ITERATION_COLUMNS,
        drift_iteration_rows,
    )
    write_csv(
        output_dir / "dt_drift_scenario_summary.csv",
        DRIFT_SCENARIO_COLUMNS,
        drift_scenario_rows,
    )
    write_csv(output_dir / "false_control_detail.csv", CONTROL_DETAIL_COLUMNS, control_detail_rows)
    write_csv(
        output_dir / "false_control_iteration_summary.csv",
        CONTROL_ITERATION_COLUMNS,
        control_iteration_rows,
    )
    write_csv(
        output_dir / "false_control_scenario_summary.csv",
        CONTROL_SCENARIO_COLUMNS,
        control_scenario_rows,
    )

    print(f"Wrote outputs to {output_dir}")
    for warning in warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
