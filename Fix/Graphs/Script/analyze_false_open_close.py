#!/usr/bin/env python3
# Klasifikasi error breaker_DT MITM terhadap keputusan baseline.
# 1 berarti breaker CLOSED, 0 berarti OPEN; matching dilakukan per iterasi,
# origin_cycle, dan bus untuk membedakan false_open dan false_close.
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
GRAPHS_DIR = SCRIPT_DIR.parent
DEFAULT_DATA_DIR = GRAPHS_DIR / "Data"
DEFAULT_OUTPUT_DIR = GRAPHS_DIR / "Join" / "mitm"
# Baseline menjadi referensi keputusan normal, MITM menjadi skenario serangan.
DEFAULT_REFERENCE_SCENARIO = "baseline"
DEFAULT_ATTACK_SCENARIO = "mitm"

DETAIL_COLUMNS = [
    "comparison",
    "iteration",
    "origin_cycle",
    "bus",
    "baseline_cmd_id",
    "mitm_cmd_id",
    "baseline_breaker_dt",
    "mitm_breaker_dt",
    "false_control_action",
    "control_error_type",
]

ITERATION_COLUMNS = [
    "comparison",
    "iteration",
    "matched_decisions",
    "missing_baseline_decisions",
    "correct_count",
    "false_control_count",
    "false_open_count",
    "false_close_count",
    "false_open_pct_of_false",
    "false_close_pct_of_false",
    "decision_error_rate_pct",
]

SUMMARY_COLUMNS = [
    "comparison",
    "iteration_count",
    "matched_decisions",
    "missing_baseline_decisions",
    "correct_count",
    "false_control_count",
    "false_open_count",
    "false_close_count",
    "false_open_pct_of_false",
    "false_close_pct_of_false",
    "decision_error_rate_pct",
]

HEADER_LABELS = {
    "comparison": "comparison (-)",
    "iteration": "iteration (-)",
    "origin_cycle": "origin_cycle (-)",
    "bus": "bus (-)",
    "baseline_cmd_id": "baseline_cmd_id (-)",
    "mitm_cmd_id": "mitm_cmd_id (-)",
    "baseline_breaker_dt": "baseline_breaker_DT (-)",
    "mitm_breaker_dt": "mitm_breaker_DT (-)",
    "false_control_action": "false_control_action (-)",
    "control_error_type": "control_error_type (-)",
    "iteration_count": "iteration_count (count)",
    "matched_decisions": "matched_decisions (count)",
    "missing_baseline_decisions": "missing_baseline_decisions (count)",
    "correct_count": "correct_count (count)",
    "false_control_count": "false_control_count (count)",
    "false_open_count": "false_open_count (count)",
    "false_close_count": "false_close_count (count)",
    "false_open_pct_of_false": "false_open_pct_of_false (%)",
    "false_close_pct_of_false": "false_close_pct_of_false (%)",
    "decision_error_rate_pct": "decision_error_rate (%)",
}


def fmt_float(value, digits=6):
    """Format angka float untuk persentase output."""
    return f"{float(value):.{digits}f}"


def iteration_sort_key(path):
    """Urutkan folder iteration_N secara numerik."""
    try:
        return int(path.name.split("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def classify_control_error(reference_breaker_dt, attack_breaker_dt):
    """Klasifikasikan keputusan MITM sebagai correct, false_open, atau false_close."""
    if reference_breaker_dt == attack_breaker_dt:
        return "correct"
    if reference_breaker_dt == 1 and attack_breaker_dt == 0:
        return "false_open"
    if reference_breaker_dt == 0 and attack_breaker_dt == 1:
        return "false_close"
    return "unknown"


def read_h4_control(path):
    """Baca keputusan breaker_DT dari h4 control_plane."""
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


def selected_cycle_ids(cycle_ids, start_cycle=None, limit_cycles=None):
    """Pilih origin_cycle berdasarkan start dan limit dari argumen CLI."""
    selected = sorted(cycle_ids)
    if start_cycle is not None:
        selected = [cycle_id for cycle_id in selected if cycle_id >= start_cycle]
    if limit_cycles is not None:
        selected = selected[:limit_cycles]
    return set(selected)


def analyze_iteration(
    comparison,
    iteration_name,
    baseline_rows,
    mitm_rows,
    start_cycle=None,
    limit_cycles=None,
):
    """Cocokkan keputusan baseline dan MITM untuk satu iterasi."""
    mitm_cycle_ids = {origin_cycle for origin_cycle, _bus in mitm_rows}
    cycle_ids = selected_cycle_ids(mitm_cycle_ids, start_cycle, limit_cycles)

    detail_rows = []
    missing_baseline = 0

    for (origin_cycle, bus), mitm_row in sorted(mitm_rows.items()):
        if origin_cycle not in cycle_ids:
            continue

        baseline_row = baseline_rows.get((origin_cycle, bus))
        if baseline_row is None:
            missing_baseline += 1
            continue

        error_type = classify_control_error(
            baseline_row["breaker_dt"],
            mitm_row["breaker_dt"],
        )
        detail_rows.append(
            {
                "comparison": comparison,
                "iteration": iteration_name,
                "origin_cycle": origin_cycle,
                "bus": bus,
                "baseline_cmd_id": baseline_row["cmd_id"],
                "mitm_cmd_id": mitm_row["cmd_id"],
                "baseline_breaker_dt": baseline_row["breaker_dt"],
                "mitm_breaker_dt": mitm_row["breaker_dt"],
                "false_control_action": int(error_type != "correct"),
                "control_error_type": error_type,
            }
        )

    return detail_rows, summarize_counts(
        detail_rows,
        comparison,
        iteration=iteration_name,
        missing_baseline=missing_baseline,
    )


def summarize_counts(rows, comparison, iteration="", missing_baseline=0):
    """Hitung total correct/false_open/false_close untuk kumpulan baris."""
    counts = Counter(row["control_error_type"] for row in rows)
    matched = len(rows)
    false_open = counts["false_open"]
    false_close = counts["false_close"]
    false_count = false_open + false_close + counts["unknown"]
    correct = counts["correct"]

    false_open_pct = false_open / false_count * 100 if false_count else 0.0
    false_close_pct = false_close / false_count * 100 if false_count else 0.0
    decision_error_rate = false_count / matched * 100 if matched else 0.0

    summary = {
        "comparison": comparison,
        "matched_decisions": matched,
        "missing_baseline_decisions": missing_baseline,
        "correct_count": correct,
        "false_control_count": false_count,
        "false_open_count": false_open,
        "false_close_count": false_close,
        "false_open_pct_of_false": fmt_float(false_open_pct),
        "false_close_pct_of_false": fmt_float(false_close_pct),
        "decision_error_rate_pct": fmt_float(decision_error_rate),
    }
    if iteration:
        summary["iteration"] = iteration
    return summary


def summarize_overall(rows, iteration_summaries, comparison):
    """Gabungkan seluruh iterasi menjadi summary MITM vs baseline."""
    missing_baseline = sum(
        int(row["missing_baseline_decisions"]) for row in iteration_summaries
    )
    summary = summarize_counts(
        rows,
        comparison,
        missing_baseline=missing_baseline,
    )
    summary["iteration_count"] = len(iteration_summaries)
    return summary


def write_csv(path, columns, rows):
    """Tulis CSV output dengan header display."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[HEADER_LABELS[column] for column in columns],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {HEADER_LABELS[column]: row.get(column, "") for column in columns}
            )


def scenario_control_dir(data_dir, scenario):
    """Resolusi folder control_plane skenario dari nama baseline/MITM."""
    if scenario == "baseline":
        return data_dir / "Baseline" / "host_csv"
    if scenario == "mitm":
        return data_dir / "MITM" / "host_csv"
    raise ValueError(f"Unknown scenario: {scenario}")


def parse_args():
    """Argumen folder input/output, nama skenario, dan filter cycle."""
    parser = argparse.ArgumentParser(
        description="Compare MITM h4 breaker_DT against baseline h4 breaker_DT."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Graphs/Data folder containing Baseline and MITM host_csv logs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output folder for MITM false open/close CSV files.",
    )
    parser.add_argument(
        "--start-cycle",
        type=int,
        default=None,
        help="Only analyze origin_cycle values greater than or equal to this value.",
    )
    parser.add_argument(
        "--limit-cycles",
        type=int,
        default=None,
        help="Analyze only the first N selected origin_cycle values per iteration.",
    )
    return parser.parse_args()


def main():
    """Entry point klasifikasi false open/close."""
    args = parse_args()
    data_dir = args.data_dir.resolve()
    output_dir = args.output_dir.resolve()
    comparison = f"{DEFAULT_ATTACK_SCENARIO}_vs_{DEFAULT_REFERENCE_SCENARIO}"

    baseline_dir = scenario_control_dir(data_dir, DEFAULT_REFERENCE_SCENARIO)
    mitm_dir = scenario_control_dir(data_dir, DEFAULT_ATTACK_SCENARIO)

    detail_rows = []
    iteration_summaries = []
    warnings = []

    mitm_iterations = sorted(
        [path for path in mitm_dir.glob("iteration_*") if path.is_dir()],
        key=iteration_sort_key,
    )

    for mitm_iteration_dir in mitm_iterations:
        if iteration_sort_key(mitm_iteration_dir) <= 0:
            continue

        iteration_name = mitm_iteration_dir.name
        baseline_iteration_dir = baseline_dir / iteration_name
        baseline_h4 = baseline_iteration_dir / "control_plane" / "h4.csv"
        mitm_h4 = mitm_iteration_dir / "control_plane" / "h4.csv"

        if not baseline_h4.exists():
            warnings.append(f"missing baseline control file: {baseline_h4}")
            continue
        if not mitm_h4.exists():
            warnings.append(f"missing MITM control file: {mitm_h4}")
            continue

        baseline_rows = read_h4_control(baseline_h4)
        mitm_rows = read_h4_control(mitm_h4)
        iteration_detail, iteration_summary = analyze_iteration(
            comparison,
            iteration_name,
            baseline_rows,
            mitm_rows,
            args.start_cycle,
            args.limit_cycles,
        )
        detail_rows.extend(iteration_detail)
        iteration_summaries.append(iteration_summary)

    if not detail_rows:
        raise SystemExit("No matched baseline-vs-MITM h4 breaker_DT rows found.")

    write_csv(output_dir / "mitm_false_open_close_detail.csv", DETAIL_COLUMNS, detail_rows)
    write_csv(
        output_dir / "mitm_false_open_close_iteration_summary.csv",
        ITERATION_COLUMNS,
        iteration_summaries,
    )
    write_csv(
        output_dir / "mitm_false_open_close_summary.csv",
        SUMMARY_COLUMNS,
        [summarize_overall(detail_rows, iteration_summaries, comparison)],
    )

    print(f"Wrote baseline-vs-MITM false open/close CSV files to {output_dir}")
    for warning in warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
