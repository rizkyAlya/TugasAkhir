#!/usr/bin/env python3
# Membuat line graph metrik DT drift dan false control dari CSV Join.
# Sumbu x dinormalisasi per iterasi: t = cycle_id - cycle_id pertama yang matched.
import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent
GRAPHS_DIR = SCRIPT_DIR.parent
DEFAULT_JOIN_DIR = GRAPHS_DIR / "Join"
DEFAULT_OUTPUT_DIR = GRAPHS_DIR / "Graph"

# Label, warna, dan marker dibuat eksplisit agar grafik antar skrip konsisten.
SCENARIO_LABELS = {
    "baseline": "Baseline",
    "mitm": "MITM",
    "dos_light": "DoS Light",
    "dos_heavy": "DoS Heavy",
}

SCENARIO_COLORS = {
    "baseline": "#10B981",
    "mitm": "#101EB9",
    "dos_light": "#F59E0B",
    "dos_heavy": "#EF4444",
}

SCENARIO_MARKERS = {
    "baseline": "o",
    "mitm": "s",
    "dos_light": "^",
    "dos_heavy": "D",
}

# Set perbandingan menentukan skenario dan folder output tiap gambar.
COMPARISONS = [
    {
        "name": "mitm",
        "output_dir": "mitm",
        "title_suffix": "Baseline vs MITM",
        "scenarios": ["baseline", "mitm"],
    },
    {
        "name": "baseline_mitm_dos",
        "output_dir": "dos",
        "title_suffix": "Baseline vs MITM vs DoS",
        "scenarios": ["baseline", "mitm", "dos_light", "dos_heavy"],
    },
]

# Konfigurasi plot: sumber data, judul, nama file, dan label sumbu.
PLOTS = [
    {
        "name": "dt_drift",
        "source": "drift",
        "title": "Mean DT Voltage Drift",
        "ylabel": "Mean |V_DT - V_Field| (pu)",
        "filename": "dt_drift_line.png",
        "value_fmt": "{:.5f}",
        "log_y": True,
    },
    {
        "name": "false_control_count",
        "source": "false_count",
        "title": "False Control Actions",
        "ylabel": "False Control Actions (count)",
        "filename": "false_control_count_line.png",
        "value_fmt": "{:.2f}",
        "log_y": False,
    },
    {
        "name": "decision_error_rate",
        "source": "error_rate",
        "title": "Decision Error Rate",
        "ylabel": "Decision Error Rate (%)",
        "filename": "decision_error_rate_line.png",
        "value_fmt": "{:.1f}",
        "log_y": False,
    },
]

HEADER_ALIASES = {
    "drift_abs_pu": ["drift_abs"],
    "false_control_action": ["false_control_action"],
    "cycle_id": ["origin_cycle"],
}


def get_csv_value(row, column):
    """Ambil nilai kolom, termasuk CSV yang memakai label dengan satuan."""
    if column in row:
        return row[column]
    prefixes = [f"{column} ("]
    prefixes.extend(f"{alias} (" for alias in HEADER_ALIASES.get(column, []))
    for prefix in prefixes:
        for key, value in row.items():
            if key.startswith(prefix):
                return value
    return ""


def mean(values):
    """Rata-rata aman untuk list kosong."""
    return statistics.fmean(values) if values else 0.0


def read_dt_drift_detail(path):
    """Baca detail drift dan normalisasi cycle menjadi waktu relatif per iterasi."""
    raw = defaultdict(list)
    min_cycle_by_iter = {}

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = (get_csv_value(row, "scenario") or "").strip()
            iteration = (get_csv_value(row, "iteration") or "").strip()
            if not scenario or not iteration:
                continue
            try:
                cycle_id = int(get_csv_value(row, "cycle_id"))
                drift_abs = float(get_csv_value(row, "drift_abs_pu"))
            except ValueError:
                continue

            raw[(scenario, iteration, cycle_id)].append(drift_abs)
            key = (scenario, iteration)
            min_cycle_by_iter[key] = min(cycle_id, min_cycle_by_iter.get(key, cycle_id))

    per_t = defaultdict(list)
    for (scenario, iteration, cycle_id), values in raw.items():
        t = cycle_id - min_cycle_by_iter[(scenario, iteration)]
        per_t[(scenario, t)].append(mean(values))

    return [
        {"scenario": scenario, "t": t, "value": mean(values)}
        for (scenario, t), values in sorted(per_t.items())
    ]


def read_false_control_detail(path):
    """Baca detail false control dan agregasi jumlah/error rate per cycle relatif."""
    raw = defaultdict(list)
    min_cycle_by_iter = {}

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = (get_csv_value(row, "scenario") or "").strip()
            iteration = (get_csv_value(row, "iteration") or "").strip()
            if not scenario or not iteration:
                continue
            try:
                origin_cycle = int(get_csv_value(row, "origin_cycle"))
                false_action = int(get_csv_value(row, "false_control_action"))
            except ValueError:
                continue

            raw[(scenario, iteration, origin_cycle)].append(false_action)
            key = (scenario, iteration)
            min_cycle_by_iter[key] = min(origin_cycle, min_cycle_by_iter.get(key, origin_cycle))

    count_per_t = defaultdict(list)
    rate_per_t = defaultdict(list)
    for (scenario, iteration, origin_cycle), values in raw.items():
        t = origin_cycle - min_cycle_by_iter[(scenario, iteration)]
        false_count = sum(values)
        error_rate = false_count / len(values) * 100 if values else 0.0
        count_per_t[(scenario, t)].append(false_count)
        rate_per_t[(scenario, t)].append(error_rate)

    false_count_rows = [
        {"scenario": scenario, "t": t, "value": mean(values)}
        for (scenario, t), values in sorted(count_per_t.items())
    ]
    error_rate_rows = [
        {"scenario": scenario, "t": t, "value": mean(values)}
        for (scenario, t), values in sorted(rate_per_t.items())
    ]
    return false_count_rows, error_rate_rows


def draw_line_plot(rows, comparison, plot_cfg, output_dir):
    """Gambar satu line plot untuk konfigurasi metrik dan perbandingan tertentu."""
    rows = [row for row in rows if row["scenario"] in comparison["scenarios"]]
    if not rows:
        return None

    fig, ax = plt.subplots(figsize=(11.5, 6.1), dpi=160)
    fig.patch.set_facecolor("#F8FAFC")
    ax.set_facecolor("#FFFFFF")
    use_log_y = bool(plot_cfg.get("log_y"))
    if use_log_y:
        ax.set_yscale("log")

    for scenario in comparison["scenarios"]:
        scenario_rows = sorted(
            [row for row in rows if row["scenario"] == scenario],
            key=lambda row: row["t"],
        )
        if not scenario_rows:
            continue
        x_values = [row["t"] for row in scenario_rows]
        if use_log_y:
            positive_values = [row["value"] for row in scenario_rows if row["value"] > 0]
            floor_value = min(positive_values) * 0.5 if positive_values else 1e-9
            y_values = [row["value"] if row["value"] > 0 else floor_value for row in scenario_rows]
        else:
            y_values = [row["value"] for row in scenario_rows]

        ax.plot(
            x_values,
            y_values,
            marker=SCENARIO_MARKERS.get(scenario, "o"),
            markevery=max(1, len(x_values) // 12),
            markersize=5.5,
            linewidth=2.2,
            color=SCENARIO_COLORS.get(scenario, "#64748B"),
            label=SCENARIO_LABELS.get(scenario, scenario),
        )

    ax.set_title(
        f"{plot_cfg['title']}: {comparison['title_suffix']}",
        fontsize=15,
        fontweight="bold",
        color="#0F172A",
        pad=14,
    )
    ax.set_xlabel("t", fontsize=12, fontweight="semibold")
    ax.set_ylabel(plot_cfg["ylabel"], fontsize=11, fontweight="semibold")
    ax.grid(axis="both", linestyle="--", linewidth=0.8, alpha=0.45, color="#94A3B8")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.legend(
        title="Scenario",
        frameon=True,
        facecolor="#FFFFFF",
        edgecolor="#CBD5E1",
        fontsize=10,
        title_fontsize=10,
        loc="best",
    )

    if use_log_y:
        positive_all = [row["value"] for row in rows if row["value"] > 0]
        if positive_all:
            ax.set_ylim(bottom=min(positive_all) * 0.45, top=max(positive_all) * 1.8)
    else:
        y_max = max(row["value"] for row in rows)
        ax.set_ylim(bottom=0, top=1.0 if y_max == 0 else y_max * 1.18)

    note = (
        "Only matched records are used. "
        "Each t is cycle_id normalized to start at 0 per iteration, then averaged across iterations."
    )
    if use_log_y:
        note += " Drift uses a log-scaled Y-axis so small baseline values remain visible."
    fig.text(0.01, 0.015, note, fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, 0.035, 1, 1))

    target_dir = output_dir / comparison["output_dir"]
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{comparison['name']}_{plot_cfg['filename']}"
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def parse_args():
    """Argumen folder Join dan folder output Graph."""
    parser = argparse.ArgumentParser(
        description="Create matched-only line graphs by normalized cycle time t."
    )
    parser.add_argument(
        "--join-dir",
        type=Path,
        default=DEFAULT_JOIN_DIR,
        help="Graphs/Join folder containing DT drift and false control detail CSVs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Graphs/Graph output folder.",
    )
    return parser.parse_args()


def main():
    """Entry point plotting DT drift dan false control."""
    args = parse_args()
    join_dir = args.join_dir.resolve()
    output_dir = args.output_dir.resolve()
    drift_path = join_dir / "dt_drift_detail.csv"
    control_path = join_dir / "false_control_detail.csv"

    if not drift_path.exists():
        raise SystemExit(f"Input not found: {drift_path}")
    if not control_path.exists():
        raise SystemExit(f"Input not found: {control_path}")

    drift_rows = read_dt_drift_detail(drift_path)
    false_count_rows, error_rate_rows = read_false_control_detail(control_path)
    source_rows = {
        "drift": drift_rows,
        "false_count": false_count_rows,
        "error_rate": error_rate_rows,
    }

    written = []
    for comparison in COMPARISONS:
        for plot_cfg in PLOTS:
            output_path = draw_line_plot(
                source_rows[plot_cfg["source"]],
                comparison,
                plot_cfg,
                output_dir,
            )
            if output_path:
                written.append(output_path)

    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
