#!/usr/bin/env python3
# Analisis manipulasi arus (I) dengan mencocokkan H2.I_sent dan H3.I_received.
# Sampel dianggap cocok bila cycle_id/bus sama dan timestamp h3 tidak lebih awal dari h2.
# Manipulasi ditandai bila selisih memenuhi ambang absolut dan persentase.
import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
GRAPHS_DIR = SCRIPT_DIR.parent
DEFAULT_DATA_DIR = GRAPHS_DIR / "Data"
DEFAULT_OUTPUT_DIR = GRAPHS_DIR / "Join"

# Folder host_csv yang dapat dianalisis; default fokus baseline vs MITM.
SCENARIO_PATHS = [
    ("baseline", Path("Baseline") / "host_csv"),
    ("dos_light", Path("DoS") / "host_csv" / "dos_light"),
    ("dos_heavy", Path("DoS") / "host_csv" / "dos_heavy"),
    ("mitm", Path("MITM") / "host_csv"),
]

DEFAULT_SCENARIOS = ["baseline", "mitm"]
DEFAULT_ABS_THRESHOLD_A = 40.0
DEFAULT_PCT_THRESHOLD = 5.0

DETAIL_COLUMNS = [
    "scenario",
    "iteration",
    "cycle_id",
    "bus",
    "h2_ts_sent",
    "h3_ts_received",
    "i_sent_a",
    "i_received_a",
    "diff_signed_a",
    "diff_abs_a",
    "diff_pct",
    "manipulated",
]

ITERATION_COLUMNS = [
    "scenario",
    "iteration",
    "matched_samples",
    "manipulated_count",
    "manipulation_rate_pct",
    "diff_abs_mean_a",
    "diff_abs_std_dev_a",
    "diff_abs_max_a",
    "diff_pct_mean",
    "diff_pct_std_dev",
]

SCENARIO_COLUMNS = [
    "scenario",
    "iteration_count",
    "matched_samples_sum",
    "manipulated_count_sum",
    "manipulation_rate_pct_mean",
    "manipulation_rate_pct_std_dev",
    "diff_abs_mean_a_mean",
    "diff_abs_mean_a_std_dev",
    "diff_abs_max_a_max",
    "diff_pct_mean_mean",
    "diff_pct_mean_std_dev",
]

BUS_COLUMNS = [
    "scenario",
    "bus",
    "matched_samples",
    "manipulated_count",
    "manipulation_rate_pct",
    "diff_abs_mean_a",
    "diff_abs_std_dev_a",
    "diff_abs_max_a",
]

HEADER_LABELS = {
    "scenario": "scenario (-)",
    "iteration": "iteration (-)",
    "cycle_id": "cycle_id (-)",
    "bus": "bus (-)",
    "h2_ts_sent": "h2_ts_sent (epoch_s)",
    "h3_ts_received": "h3_ts_received (epoch_s)",
    "i_sent_a": "I_sent_h2 (A)",
    "i_received_a": "I_received_h3 (A)",
    "diff_signed_a": "diff_signed (A)",
    "diff_abs_a": "diff_abs (A)",
    "diff_pct": "diff (%)",
    "manipulated": "manipulated (-)",
    "matched_samples": "matched_samples (count)",
    "manipulated_count": "manipulated_count (count)",
    "manipulation_rate_pct": "manipulation_rate (%)",
    "diff_abs_mean_a": "diff_abs_mean (A)",
    "diff_abs_std_dev_a": "diff_abs_std_dev (A)",
    "diff_abs_max_a": "diff_abs_max (A)",
    "diff_pct_mean": "diff_mean (%)",
    "diff_pct_std_dev": "diff_std_dev (%)",
    "iteration_count": "iteration_count (count)",
    "matched_samples_sum": "matched_samples_sum (count)",
    "manipulated_count_sum": "manipulated_count_sum (count)",
    "manipulation_rate_pct_mean": "manipulation_rate_mean (%)",
    "manipulation_rate_pct_std_dev": "manipulation_rate_std_dev (%)",
    "diff_abs_mean_a_mean": "diff_abs_mean_mean (A)",
    "diff_abs_mean_a_std_dev": "diff_abs_mean_std_dev (A)",
    "diff_abs_max_a_max": "diff_abs_max_max (A)",
    "diff_pct_mean_mean": "diff_mean_mean (%)",
    "diff_pct_mean_std_dev": "diff_mean_std_dev (%)",
}


def display_header(column):
    """Ubah nama kolom internal menjadi label CSV dengan satuan."""
    return HEADER_LABELS.get(column, column)


def fmt_float(value, digits=6):
    """Format angka float; kosong bila nilai tidak tersedia."""
    if value == "":
        return ""
    return f"{float(value):.{digits}f}"


def mean(values):
    """Rata-rata aman untuk list kosong."""
    return statistics.fmean(values) if values else 0.0


def std_dev(values):
    """Standar deviasi sample; nol bila data kurang dari dua."""
    return statistics.stdev(values) if len(values) > 1 else 0.0


def iteration_sort_key(path):
    """Urutkan folder iteration_N secara numerik."""
    try:
        return int(path.name.split("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def selected_cycle_ids(cycle_ids, start_cycle=None, limit_cycles=None):
    """Pilih cycle_id berdasarkan start dan limit dari argumen CLI."""
    selected = sorted(cycle_ids)
    if start_cycle is not None:
        selected = [cycle_id for cycle_id in selected if cycle_id >= start_cycle]
    if limit_cycles is not None:
        selected = selected[:limit_cycles]
    return set(selected)


def read_h2_current(path):
    """Baca arus yang dikirim RTU h2 per cycle dan bus."""
    rows = defaultdict(list)
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cycle_id = int(row["cycle_id"])
                bus = int(row["bus"])
                ts_sent = float(row["ts_sent"])
                i_sent = float(row["I_sent"])
            except (KeyError, ValueError):
                continue
            rows[(cycle_id, bus)].append({"ts_sent": ts_sent, "i_sent": i_sent})

    for key in rows:
        rows[key].sort(key=lambda item: item["ts_sent"])
    return rows


def read_h3_current(path):
    """Baca arus yang diterima gateway h3 per cycle dan bus."""
    rows = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append(
                    {
                        "cycle_id": int(row["cycle_id"]),
                        "bus": int(row["bus"]),
                        "ts_received": float(row["ts_received"]),
                        "i_received": float(row["I_received"]),
                    }
                )
            except (KeyError, ValueError):
                continue
    return rows


def pick_h2_sample(h2_candidates, h3_ts_received):
    """Ambil sampel h2 terakhir yang masih terjadi sebelum penerimaan h3."""
    before_or_equal = [
        candidate for candidate in h2_candidates if candidate["ts_sent"] <= h3_ts_received
    ]
    if before_or_equal:
        return before_or_equal[-1]
    return None


def analyze_iteration(
    scenario,
    iteration_dir,
    abs_threshold_a,
    pct_threshold,
    start_cycle=None,
    limit_cycles=None,
):
    """Cocokkan sampel h2-h3 dan tandai manipulasi untuk satu iterasi."""
    h2_path = iteration_dir / "data_plane" / "h2.csv"
    h3_path = iteration_dir / "data_plane" / "h3.csv"
    if not h2_path.exists() or not h3_path.exists():
        return [], None, f"missing h2/h3 data in {iteration_dir}"

    h2_rows = read_h2_current(h2_path)
    h3_rows = read_h3_current(h3_path)
    selected_cycles = selected_cycle_ids(
        {cycle_id for cycle_id, _bus in h2_rows},
        start_cycle,
        limit_cycles,
    )

    detail_rows = []
    diff_abs_values = []
    diff_pct_values = []
    manipulated_count = 0

    for h3 in h3_rows:
        cycle_id = h3["cycle_id"]
        bus = h3["bus"]
        if selected_cycles and cycle_id not in selected_cycles:
            continue
        h2 = pick_h2_sample(h2_rows.get((cycle_id, bus), []), h3["ts_received"])
        if h2 is None:
            continue

        i_sent = h2["i_sent"]
        i_received = h3["i_received"]
        diff_signed = i_received - i_sent
        diff_abs = abs(diff_signed)
        diff_pct = diff_abs / abs(i_sent) * 100 if abs(i_sent) > 1e-12 else 0.0
        manipulated = int(diff_abs >= abs_threshold_a and diff_pct >= pct_threshold)

        manipulated_count += manipulated
        diff_abs_values.append(diff_abs)
        diff_pct_values.append(diff_pct)
        detail_rows.append(
            {
                "scenario": scenario,
                "iteration": iteration_dir.name,
                "cycle_id": cycle_id,
                "bus": bus,
                "h2_ts_sent": fmt_float(h2["ts_sent"]),
                "h3_ts_received": fmt_float(h3["ts_received"]),
                "i_sent_a": fmt_float(i_sent),
                "i_received_a": fmt_float(i_received),
                "diff_signed_a": fmt_float(diff_signed),
                "diff_abs_a": fmt_float(diff_abs),
                "diff_pct": fmt_float(diff_pct),
                "manipulated": manipulated,
            }
        )

    matched_samples = len(detail_rows)
    summary = {
        "scenario": scenario,
        "iteration": iteration_dir.name,
        "matched_samples": matched_samples,
        "manipulated_count": manipulated_count,
        "manipulation_rate_pct": fmt_float(
            manipulated_count / matched_samples * 100 if matched_samples else 0.0
        ),
        "diff_abs_mean_a": fmt_float(mean(diff_abs_values)),
        "diff_abs_std_dev_a": fmt_float(std_dev(diff_abs_values)),
        "diff_abs_max_a": fmt_float(max(diff_abs_values) if diff_abs_values else 0.0),
        "diff_pct_mean": fmt_float(mean(diff_pct_values)),
        "diff_pct_std_dev": fmt_float(std_dev(diff_pct_values)),
    }
    return detail_rows, summary, None


def summarize_scenario(scenario, rows):
    """Ringkas hasil manipulasi arus per skenario."""
    items = [row for row in rows if row["scenario"] == scenario]
    if not items:
        return None

    def values(column):
        return [float(row[column]) for row in items]

    return {
        "scenario": scenario,
        "iteration_count": len(items),
        "matched_samples_sum": sum(int(row["matched_samples"]) for row in items),
        "manipulated_count_sum": sum(int(row["manipulated_count"]) for row in items),
        "manipulation_rate_pct_mean": fmt_float(mean(values("manipulation_rate_pct"))),
        "manipulation_rate_pct_std_dev": fmt_float(std_dev(values("manipulation_rate_pct"))),
        "diff_abs_mean_a_mean": fmt_float(mean(values("diff_abs_mean_a"))),
        "diff_abs_mean_a_std_dev": fmt_float(std_dev(values("diff_abs_mean_a"))),
        "diff_abs_max_a_max": fmt_float(max(values("diff_abs_max_a"))),
        "diff_pct_mean_mean": fmt_float(mean(values("diff_pct_mean"))),
        "diff_pct_mean_std_dev": fmt_float(std_dev(values("diff_pct_mean"))),
    }


def summarize_bus(rows):
    """Ringkas hasil manipulasi arus per bus."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["scenario"], row["bus"])].append(row)

    out = []
    for (scenario, bus), items in sorted(grouped.items()):
        diff_abs_values = [float(row["diff_abs_a"]) for row in items]
        manipulated_count = sum(int(row["manipulated"]) for row in items)
        matched_samples = len(items)
        out.append(
            {
                "scenario": scenario,
                "bus": bus,
                "matched_samples": matched_samples,
                "manipulated_count": manipulated_count,
                "manipulation_rate_pct": fmt_float(
                    manipulated_count / matched_samples * 100 if matched_samples else 0.0
                ),
                "diff_abs_mean_a": fmt_float(mean(diff_abs_values)),
                "diff_abs_std_dev_a": fmt_float(std_dev(diff_abs_values)),
                "diff_abs_max_a": fmt_float(max(diff_abs_values) if diff_abs_values else 0.0),
            }
        )
    return out


def write_csv(path, columns, rows):
    """Tulis CSV output dengan header display."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [display_header(column) for column in columns]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({display_header(column): row.get(column, "") for column in columns})


def default_output_dir_for_scenarios(scenarios):
    """Pilih subfolder output otomatis berdasarkan skenario yang dianalisis."""
    selected = set(scenarios)
    has_dos = bool(selected & {"dos_light", "dos_heavy"})
    has_mitm = "mitm" in selected
    if has_dos and not has_mitm:
        return DEFAULT_OUTPUT_DIR / "dos"
    if has_mitm and not has_dos:
        return DEFAULT_OUTPUT_DIR / "mitm"
    return DEFAULT_OUTPUT_DIR


def parse_args():
    """Argumen input/output, skenario, threshold, dan filter cycle."""
    parser = argparse.ArgumentParser(
        description="Analyze current manipulation from matched H2/H3 current logs."
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
        default=DEFAULT_SCENARIOS,
        help="Scenarios to analyze.",
    )
    parser.add_argument(
        "--abs-threshold-a",
        type=float,
        default=DEFAULT_ABS_THRESHOLD_A,
        help="Absolute current-difference threshold in ampere.",
    )
    parser.add_argument(
        "--pct-threshold",
        type=float,
        default=DEFAULT_PCT_THRESHOLD,
        help="Relative current-difference threshold in percent.",
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
    """Entry point analisis manipulasi arus."""
    args = parse_args()
    data_dir = args.data_dir.resolve()
    output_dir = (
        default_output_dir_for_scenarios(args.scenarios)
        if args.output_dir == DEFAULT_OUTPUT_DIR
        else args.output_dir
    ).resolve()
    selected_scenarios = set(args.scenarios)

    all_detail_rows = []
    iteration_summaries = []
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
            detail_rows, summary, warning = analyze_iteration(
                scenario,
                iteration_dir,
                args.abs_threshold_a,
                args.pct_threshold,
                start_cycle=args.start_cycle,
                limit_cycles=args.limit_cycles,
            )
            all_detail_rows.extend(detail_rows)
            if summary is not None:
                iteration_summaries.append(summary)
            if warning:
                warnings.append(warning)

    scenario_order = [scenario for scenario, _rel_path in SCENARIO_PATHS if scenario in selected_scenarios]
    scenario_summaries = [
        row
        for scenario in scenario_order
        if (row := summarize_scenario(scenario, iteration_summaries))
    ]
    bus_summaries = summarize_bus(all_detail_rows)

    write_csv(output_dir / "current_manipulation_detail.csv", DETAIL_COLUMNS, all_detail_rows)
    write_csv(
        output_dir / "current_manipulation_iteration_summary.csv",
        ITERATION_COLUMNS,
        iteration_summaries,
    )
    write_csv(
        output_dir / "current_manipulation_scenario_summary.csv",
        SCENARIO_COLUMNS,
        scenario_summaries,
    )
    write_csv(output_dir / "current_manipulation_bus_summary.csv", BUS_COLUMNS, bus_summaries)

    print(f"Wrote outputs to {output_dir}")
    print(
        f"Thresholds: abs_diff >= {args.abs_threshold_a:g} A "
        f"and diff_pct >= {args.pct_threshold:g}%"
    )
    for warning in warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
