#!/usr/bin/env python3
# Analisis latency kontrol dari CSV control_plane.
# Baris cocok bila cmd_id dan bus ada di h4 (DT mengirim) dan h1 (field menerima);
# latency = h1.ts_received - h4.ts_sent.
import argparse
import csv
import statistics
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
GRAPHS_DIR = SCRIPT_DIR.parent
DEFAULT_DATA_DIR = GRAPHS_DIR / "Data"
DEFAULT_OUTPUT_DIR = GRAPHS_DIR / "Join" / "dos"

# Input baseline dan DoS dipakai untuk membandingkan dampak serangan pada jalur kontrol.
SCENARIO_PATHS = [
    ("baseline", Path("Baseline") / "host_csv"),
    ("dos_light", Path("DoS") / "host_csv" / "dos_light"),
    ("dos_heavy", Path("DoS") / "host_csv" / "dos_heavy"),
]

SCENARIO_LABELS = {
    "baseline": "Baseline",
    "dos_light": "DoS Light",
    "dos_heavy": "DoS Heavy",
}

DETAIL_COLUMNS = [
    "scenario",
    "iteration",
    "cmd_id",
    "origin_cycle",
    "bus",
    "h4_ts_sent",
    "h1_ts_received",
    "control_latency_s",
]

ITERATION_COLUMNS = [
    "scenario",
    "iteration",
    "matched_control_rows",
    "missing_h1_rows",
    "control_latency_mean_s",
    "control_latency_std_dev_s",
    "control_latency_min_s",
    "control_latency_max_s",
]

SCENARIO_COLUMNS = [
    "scenario",
    "iteration_count",
    "matched_control_rows_sum",
    "missing_h1_rows_sum",
    "control_latency_mean_s_mean",
    "control_latency_mean_s_std_dev",
    "control_latency_std_dev_s_mean",
    "control_latency_std_dev_s_std_dev",
    "control_latency_min_s_min",
    "control_latency_max_s_max",
]

FINAL_COLUMNS = [
    "scenario_label",
    "control_latency_mean_pm_std_s",
    "final_matched_control_rows",
    "final_missing_h1_rows",
]

HEADER_LABELS = {
    "scenario": "scenario (-)",
    "iteration": "iteration (-)",
    "cmd_id": "cmd_id (-)",
    "origin_cycle": "origin_cycle (-)",
    "bus": "bus (-)",
    "h4_ts_sent": "h4_ts_sent (epoch_s)",
    "h1_ts_received": "h1_ts_received (epoch_s)",
    "control_latency_s": "control_latency (s)",
    "matched_control_rows": "matched_control_rows (count)",
    "missing_h1_rows": "missing_h1_rows (count)",
    "control_latency_mean_s": "control_latency_mean (s)",
    "control_latency_std_dev_s": "control_latency_std_dev (s)",
    "control_latency_min_s": "control_latency_min (s)",
    "control_latency_max_s": "control_latency_max (s)",
    "iteration_count": "iteration_count (count)",
    "matched_control_rows_sum": "matched_control_rows_sum (count)",
    "missing_h1_rows_sum": "missing_h1_rows_sum (count)",
    "control_latency_mean_s_mean": "control_latency_mean_mean (s)",
    "control_latency_mean_s_std_dev": "control_latency_mean_std_dev (s)",
    "control_latency_std_dev_s_mean": "control_latency_std_dev_mean (s)",
    "control_latency_std_dev_s_std_dev": "control_latency_std_dev_std_dev (s)",
    "control_latency_min_s_min": "control_latency_min_min (s)",
    "control_latency_max_s_max": "control_latency_max_max (s)",
    "scenario_label": "Skenario",
    "control_latency_mean_pm_std_s": "Mean Control Latency (s)",
    "final_matched_control_rows": "Matched Control Rows (count)",
    "final_missing_h1_rows": "Missing H1 Rows (count)",
}


def display_header(column):
    """Ubah nama kolom internal menjadi label CSV dengan satuan."""
    return HEADER_LABELS.get(column, column)


def fmt_float(value, digits=6):
    """Format angka float; kosong bila nilai tidak tersedia."""
    if value == "":
        return ""
    return f"{float(value):.{digits}f}"


def fmt_pm(mean_value, std_value, digits=2):
    """Format mean dan standar deviasi untuk tabel final."""
    return f"{float(mean_value):.{digits}f} ± {float(std_value):.{digits}f}"


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


def selected_cmd_ids(cmd_rows, start_origin_cycle=None, limit_commands=None):
    """Pilih command berdasarkan origin_cycle dan batas jumlah command."""
    commands = sorted(
        {
            (row["origin_cycle"], row["cmd_id"])
            for row in cmd_rows
            if start_origin_cycle is None or row["origin_cycle"] >= start_origin_cycle
        }
    )
    if limit_commands is not None:
        commands = commands[:limit_commands]
    return {cmd_id for _origin_cycle, cmd_id in commands}


def read_control_rows(path, timestamp_column):
    """Baca control_plane dan ambil kolom timestamp yang relevan untuk host tersebut."""
    rows = []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append(
                    {
                        "cmd_id": int(row["cmd_id"]),
                        "origin_cycle": int(row["origin_cycle"]),
                        "bus": int(row["bus"]),
                        timestamp_column: float(row[timestamp_column]),
                    }
                )
            except (KeyError, ValueError):
                continue
    return rows


def analyze_iteration(
    scenario,
    iteration_dir,
    start_origin_cycle=None,
    limit_commands=None,
):
    """Cocokkan command DT di h4 dengan penerimaan di h1 untuk satu iterasi."""
    h4_path = iteration_dir / "control_plane" / "h4.csv"
    h1_path = iteration_dir / "control_plane" / "h1.csv"
    if not h4_path.exists() or not h1_path.exists():
        return [], None, f"missing h4/h1 control data in {iteration_dir}"

    h4_rows = read_control_rows(h4_path, "ts_sent")
    h1_rows = read_control_rows(h1_path, "ts_received")
    selected_commands = selected_cmd_ids(
        h4_rows,
        start_origin_cycle=start_origin_cycle,
        limit_commands=limit_commands,
    )

    h1_by_key = {
        (row["cmd_id"], row["bus"]): row
        for row in h1_rows
        if row["cmd_id"] in selected_commands
    }

    detail_rows = []
    latency_values = []
    missing_h1_rows = 0

    for h4 in h4_rows:
        if h4["cmd_id"] not in selected_commands:
            continue
        key = (h4["cmd_id"], h4["bus"])
        h1 = h1_by_key.get(key)
        if h1 is None:
            missing_h1_rows += 1
            continue

        latency = h1["ts_received"] - h4["ts_sent"]
        if latency < 0:
            missing_h1_rows += 1
            continue

        latency_values.append(latency)
        detail_rows.append(
            {
                "scenario": scenario,
                "iteration": iteration_dir.name,
                "cmd_id": h4["cmd_id"],
                "origin_cycle": h4["origin_cycle"],
                "bus": h4["bus"],
                "h4_ts_sent": fmt_float(h4["ts_sent"]),
                "h1_ts_received": fmt_float(h1["ts_received"]),
                "control_latency_s": fmt_float(latency),
            }
        )

    summary = {
        "scenario": scenario,
        "iteration": iteration_dir.name,
        "matched_control_rows": len(detail_rows),
        "missing_h1_rows": missing_h1_rows,
        "control_latency_mean_s": fmt_float(mean(latency_values)),
        "control_latency_std_dev_s": fmt_float(std_dev(latency_values)),
        "control_latency_min_s": fmt_float(min(latency_values) if latency_values else 0.0),
        "control_latency_max_s": fmt_float(max(latency_values) if latency_values else 0.0),
    }
    return detail_rows, summary, None


def summarize_scenario(scenario, rows):
    """Ringkas detail latency menjadi statistik per skenario."""
    items = [row for row in rows if row["scenario"] == scenario]
    if not items:
        return None

    def values(column):
        return [float(row[column]) for row in items]

    return {
        "scenario": scenario,
        "iteration_count": len(items),
        "matched_control_rows_sum": sum(int(row["matched_control_rows"]) for row in items),
        "missing_h1_rows_sum": sum(int(row["missing_h1_rows"]) for row in items),
        "control_latency_mean_s_mean": fmt_float(mean(values("control_latency_mean_s"))),
        "control_latency_mean_s_std_dev": fmt_float(std_dev(values("control_latency_mean_s"))),
        "control_latency_std_dev_s_mean": fmt_float(mean(values("control_latency_std_dev_s"))),
        "control_latency_std_dev_s_std_dev": fmt_float(std_dev(values("control_latency_std_dev_s"))),
        "control_latency_min_s_min": fmt_float(min(values("control_latency_min_s"))),
        "control_latency_max_s_max": fmt_float(max(values("control_latency_max_s"))),
    }


def build_final_table(rows):
    """Buat tabel akhir ringkas untuk baseline, DoS light, dan DoS heavy."""
    out = []
    for row in rows:
        scenario = row["scenario"]
        out.append(
            {
                "scenario_label": SCENARIO_LABELS.get(scenario, scenario),
                "control_latency_mean_pm_std_s": fmt_pm(
                    row["control_latency_mean_s_mean"],
                    row["control_latency_mean_s_std_dev"],
                ),
                "final_matched_control_rows": row["matched_control_rows_sum"],
                "final_missing_h1_rows": row["missing_h1_rows_sum"],
            }
        )
    return out


def write_csv(path, columns, rows, encoding="utf-8"):
    """Tulis CSV dengan header display."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=encoding) as f:
        fieldnames = [display_header(column) for column in columns]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({display_header(column): row.get(column, "") for column in columns})


def parse_args():
    """Argumen folder input/output dan filter command."""
    parser = argparse.ArgumentParser(
        description="Analyze control latency from H4.ts_sent to H1.ts_received."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Graphs/Data folder containing Baseline and DoS.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output folder for control latency CSV files.",
    )
    parser.add_argument(
        "--start-origin-cycle",
        type=int,
        default=None,
        help="Only analyze commands with origin_cycle greater than or equal to this value.",
    )
    parser.add_argument(
        "--limit-commands",
        type=int,
        default=None,
        help="Analyze only the first N selected cmd_id values per iteration.",
    )
    return parser.parse_args()


def main():
    """Entry point analisis latency kontrol."""
    args = parse_args()
    data_dir = args.data_dir.resolve()
    output_dir = args.output_dir.resolve()

    all_detail_rows = []
    iteration_summaries = []
    warnings = []

    for scenario, rel_path in SCENARIO_PATHS:
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
                start_origin_cycle=args.start_origin_cycle,
                limit_commands=args.limit_commands,
            )
            all_detail_rows.extend(detail_rows)
            if summary is not None:
                iteration_summaries.append(summary)
            if warning:
                warnings.append(warning)

    scenario_summaries = [
        row
        for scenario, _rel_path in SCENARIO_PATHS
        if (row := summarize_scenario(scenario, iteration_summaries))
    ]
    final_table = build_final_table(scenario_summaries)

    write_csv(output_dir / "control_latency_detail.csv", DETAIL_COLUMNS, all_detail_rows)
    write_csv(
        output_dir / "control_latency_iteration_summary.csv",
        ITERATION_COLUMNS,
        iteration_summaries,
    )
    write_csv(
        output_dir / "control_latency_scenario_summary.csv",
        SCENARIO_COLUMNS,
        scenario_summaries,
    )
    write_csv(
        output_dir / "control_latency_final_table.csv",
        FINAL_COLUMNS,
        final_table,
        encoding="utf-8-sig",
    )

    print(f"Wrote outputs to {output_dir}")
    for warning in warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
