#!/usr/bin/env python3
r"""
Analyze Age of Information (AoI) from DoS host CSV logs.

Run from project root:
    python .\Fix\Graphs\Script\analyze_dos_aoi.py

Optional threshold override:
    python .\Fix\Graphs\Script\analyze_dos_aoi.py --threshold 3

From cycle 14 and first 50 cycle_id values:
    python .\Fix\Graphs\Script\analyze_dos_aoi.py --start-cycle 14 --limit-cycles 50

Outputs:
- Graphs/Join/dos/dos_aoi_cycle_classification.csv
- Graphs/Join/dos/dos_aoi_iteration_summary.csv
- Graphs/Join/dos/dos_aoi_scenario_summary.csv
"""
import argparse
import csv
import statistics
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
GRAPHS_DIR = SCRIPT_DIR.parent
DEFAULT_HOST_CSV_DIR = GRAPHS_DIR / "Data" / "DoS" / "host_csv"
DEFAULT_OUTPUT_DIR = GRAPHS_DIR / "Join" / "dos"

SCENARIOS = ["dos_light", "dos_heavy"]
DEFAULT_THRESHOLD_S = 3.0

CYCLE_COLUMNS = [
    "scenario",
    "iteration",
    "cycle_id",
    "ts_sent",
    "ts_received",
    "aoi_s",
    "status",
]

ITERATION_COLUMNS = [
    "scenario",
    "iteration",
    "threshold_s",
    "total_cycle_id",
    "received_count",
    "fresh_count",
    "stale_count",
    "missing_count",
    "aoi_mean_s",
    "aoi_std_dev_s",
    "fresh_pct",
    "stale_pct",
    "missing_pct",
]

SCENARIO_COLUMNS = [
    "scenario",
    "threshold_s",
    "iteration_count",
    "total_cycle_id_sum",
    "received_count_sum",
    "fresh_count_sum",
    "stale_count_sum",
    "missing_count_sum",
    "aoi_mean_s_mean",
    "aoi_mean_s_std_dev",
    "aoi_std_dev_s_mean",
    "aoi_std_dev_s_std_dev",
    "fresh_pct_mean",
    "fresh_pct_std_dev",
    "stale_pct_mean",
    "stale_pct_std_dev",
    "missing_pct_mean",
    "missing_pct_std_dev",
]

HEADER_LABELS = {
    "scenario": "scenario (-)",
    "iteration": "iteration (-)",
    "cycle_id": "cycle_id (-)",
    "ts_sent": "ts_sent (epoch_s)",
    "ts_received": "ts_received (epoch_s)",
    "aoi_s": "aoi (s)",
    "status": "status (-)",
    "threshold_s": "threshold (s)",
    "total_cycle_id": "total_cycle_id (count)",
    "received_count": "received_count (count)",
    "fresh_count": "fresh_count (count)",
    "stale_count": "stale_count (count)",
    "missing_count": "missing_count (count)",
    "aoi_mean_s": "aoi_mean (s)",
    "aoi_std_dev_s": "aoi_std_dev (s)",
    "fresh_pct": "fresh_pct (%)",
    "stale_pct": "stale_pct (%)",
    "missing_pct": "missing_pct (%)",
    "iteration_count": "iteration_count (count)",
    "total_cycle_id_sum": "total_cycle_id_sum (count)",
    "received_count_sum": "received_count_sum (count)",
    "fresh_count_sum": "fresh_count_sum (count)",
    "stale_count_sum": "stale_count_sum (count)",
    "missing_count_sum": "missing_count_sum (count)",
    "aoi_mean_s_mean": "aoi_mean_mean (s)",
    "aoi_mean_s_std_dev": "aoi_mean_std_dev (s)",
    "aoi_std_dev_s_mean": "aoi_std_dev_mean (s)",
    "aoi_std_dev_s_std_dev": "aoi_std_dev_std_dev (s)",
    "fresh_pct_mean": "fresh_pct_mean (%)",
    "fresh_pct_std_dev": "fresh_pct_std_dev (%)",
    "stale_pct_mean": "stale_pct_mean (%)",
    "stale_pct_std_dev": "stale_pct_std_dev (%)",
    "missing_pct_mean": "missing_pct_mean (%)",
    "missing_pct_std_dev": "missing_pct_std_dev (%)",
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


def read_cycle_timestamps(path, ts_column):
    """
    Return one timestamp per cycle_id.

    H1 and H4 data_plane logs contain one row per bus for each cycle_id.
    The timestamp is identical for those bus rows in normal output, but min()
    keeps the aggregation deterministic if small differences appear.
    """
    timestamps = {}
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cycle_raw = (row.get("cycle_id", "") or "").strip()
            ts_raw = (row.get(ts_column, "") or "").strip()
            if not cycle_raw or not ts_raw:
                continue
            try:
                cycle_id = int(cycle_raw)
                ts_value = float(ts_raw)
            except ValueError:
                continue
            timestamps[cycle_id] = min(timestamps.get(cycle_id, ts_value), ts_value)
    return timestamps


def read_cycle_timestamp_lists(path, ts_column):
    timestamps = {}
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cycle_raw = (row.get("cycle_id", "") or "").strip()
            ts_raw = (row.get(ts_column, "") or "").strip()
            if not cycle_raw or not ts_raw:
                continue
            try:
                cycle_id = int(cycle_raw)
                ts_value = float(ts_raw)
            except ValueError:
                continue
            timestamps.setdefault(cycle_id, []).append(ts_value)

    for cycle_id in timestamps:
        timestamps[cycle_id] = sorted(set(timestamps[cycle_id]))
    return timestamps


def first_received_at_or_after(received_by_cycle, cycle_id, ts_sent):
    for ts_received in received_by_cycle.get(cycle_id, []):
        if ts_received >= ts_sent:
            return ts_received
    return None


def iteration_sort_key(path):
    name = path.name
    try:
        return int(name.split("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def selected_cycle_ids(cycle_ids, start_cycle=None, limit_cycles=None):
    selected = sorted(cycle_ids)
    if start_cycle is not None:
        selected = [cycle_id for cycle_id in selected if cycle_id >= start_cycle]
    if limit_cycles is not None:
        selected = selected[:limit_cycles]
    return selected


def analyze_iteration(
    scenario,
    iteration_dir,
    threshold_s,
    start_cycle=None,
    limit_cycles=None,
):
    h1_path = iteration_dir / "data_plane" / "h1.csv"
    h4_path = iteration_dir / "data_plane" / "h4.csv"
    if not h1_path.exists():
        return [], None, f"missing {h1_path}"
    if not h4_path.exists():
        return [], None, f"missing {h4_path}"

    h1_sent = read_cycle_timestamps(h1_path, "ts_sent")
    h4_received = read_cycle_timestamp_lists(h4_path, "ts_received")
    if not h1_sent:
        return [], None, f"no cycle_id rows in {h1_path}"

    iteration = iteration_dir.name
    cycle_rows = []
    aoi_values = []
    counts = {"Fresh": 0, "Stale": 0, "Missing": 0}

    cycle_ids = selected_cycle_ids(h1_sent.keys(), start_cycle, limit_cycles)
    if not cycle_ids:
        return [], None, f"no selected cycle_id rows in {h1_path}"

    for cycle_id in cycle_ids:
        ts_sent = h1_sent[cycle_id]
        ts_received = first_received_at_or_after(h4_received, cycle_id, ts_sent)

        if ts_received is None:
            status = "Missing"
            aoi = ""
        else:
            aoi_value = ts_received - ts_sent
            status = "Fresh" if aoi_value <= threshold_s else "Stale"
            aoi_values.append(aoi_value)
            aoi = fmt_float(aoi_value)

        counts[status] += 1
        cycle_rows.append(
            {
                "scenario": scenario,
                "iteration": iteration,
                "cycle_id": cycle_id,
                "ts_sent": fmt_float(ts_sent),
                "ts_received": "" if ts_received is None else fmt_float(ts_received),
                "aoi_s": aoi,
                "status": status,
            }
        )

    total = len(cycle_ids)
    received = counts["Fresh"] + counts["Stale"]
    iteration_summary = {
        "scenario": scenario,
        "iteration": iteration,
        "threshold_s": fmt_float(threshold_s, digits=3),
        "total_cycle_id": total,
        "received_count": received,
        "fresh_count": counts["Fresh"],
        "stale_count": counts["Stale"],
        "missing_count": counts["Missing"],
        "aoi_mean_s": fmt_float(mean(aoi_values)),
        "aoi_std_dev_s": fmt_float(std_dev(aoi_values)),
        "fresh_pct": fmt_float(counts["Fresh"] / total * 100),
        "stale_pct": fmt_float(counts["Stale"] / total * 100),
        "missing_pct": fmt_float(counts["Missing"] / total * 100),
    }
    return cycle_rows, iteration_summary, None


def summarize_scenario(scenario, iteration_summaries, threshold_s):
    rows = [row for row in iteration_summaries if row["scenario"] == scenario]
    if not rows:
        return None

    def values(column):
        return [float(row[column]) for row in rows]

    def int_sum(column):
        return sum(int(row[column]) for row in rows)

    return {
        "scenario": scenario,
        "threshold_s": fmt_float(threshold_s, digits=3),
        "iteration_count": len(rows),
        "total_cycle_id_sum": int_sum("total_cycle_id"),
        "received_count_sum": int_sum("received_count"),
        "fresh_count_sum": int_sum("fresh_count"),
        "stale_count_sum": int_sum("stale_count"),
        "missing_count_sum": int_sum("missing_count"),
        "aoi_mean_s_mean": fmt_float(mean(values("aoi_mean_s"))),
        "aoi_mean_s_std_dev": fmt_float(std_dev(values("aoi_mean_s"))),
        "aoi_std_dev_s_mean": fmt_float(mean(values("aoi_std_dev_s"))),
        "aoi_std_dev_s_std_dev": fmt_float(std_dev(values("aoi_std_dev_s"))),
        "fresh_pct_mean": fmt_float(mean(values("fresh_pct"))),
        "fresh_pct_std_dev": fmt_float(std_dev(values("fresh_pct"))),
        "stale_pct_mean": fmt_float(mean(values("stale_pct"))),
        "stale_pct_std_dev": fmt_float(std_dev(values("stale_pct"))),
        "missing_pct_mean": fmt_float(mean(values("missing_pct"))),
        "missing_pct_std_dev": fmt_float(std_dev(values("missing_pct"))),
    }


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [display_header(column) for column in columns]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({display_header(column): row.get(column, "") for column in columns})


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze AoI synchronization from DoS H1/H4 host CSV logs."
    )
    parser.add_argument(
        "--host-csv-dir",
        type=Path,
        default=DEFAULT_HOST_CSV_DIR,
        help="DoS host_csv folder containing dos_light and dos_heavy.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder for AoI output CSV files.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD_S,
        help="Fresh/Stale AoI threshold in seconds.",
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
    host_csv_dir = args.host_csv_dir.resolve()
    output_dir = args.output_dir.resolve()
    threshold_s = float(args.threshold)

    if not host_csv_dir.exists():
        raise SystemExit(f"Input folder not found: {host_csv_dir}")

    all_cycle_rows = []
    iteration_summaries = []
    warnings = []

    for scenario in SCENARIOS:
        scenario_dir = host_csv_dir / scenario
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
            cycle_rows, summary, warning = analyze_iteration(
                scenario,
                iteration_dir,
                threshold_s,
                start_cycle=args.start_cycle,
                limit_cycles=args.limit_cycles,
            )
            all_cycle_rows.extend(cycle_rows)
            if summary is not None:
                iteration_summaries.append(summary)
            if warning:
                warnings.append(warning)

    scenario_summaries = [
        row
        for scenario in SCENARIOS
        if (row := summarize_scenario(scenario, iteration_summaries, threshold_s))
    ]

    if not iteration_summaries:
        raise SystemExit(f"No valid DoS iteration data found in {host_csv_dir}")

    cycle_path = output_dir / "dos_aoi_cycle_classification.csv"
    iteration_path = output_dir / "dos_aoi_iteration_summary.csv"
    scenario_path = output_dir / "dos_aoi_scenario_summary.csv"

    write_csv(cycle_path, CYCLE_COLUMNS, all_cycle_rows)
    write_csv(iteration_path, ITERATION_COLUMNS, iteration_summaries)
    write_csv(scenario_path, SCENARIO_COLUMNS, scenario_summaries)

    print(f"Wrote {cycle_path}")
    print(f"Wrote {iteration_path}")
    print(f"Wrote {scenario_path}")
    for warning in warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
