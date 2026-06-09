#!/usr/bin/env python3
# Membuat grafik decision error rate per line khusus skenario MITM.
# Input berasal dari false_control_detail.csv dan outputnya berupa PNG serta CSV summary.
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
DEFAULT_GRAPH_DIR = GRAPHS_DIR / "Graph" / "mitm"
DEFAULT_SUMMARY_DIR = GRAPHS_DIR / "Join" / "mitm"

# File detail dari analyze_dt_drift_control.py yang menjadi sumber agregasi per line.
DETAIL_FILE = "false_control_detail.csv"
SCENARIO = "mitm"

SUMMARY_COLUMNS = [
    "line",
    "iteration_count",
    "matched_decisions_sum",
    "false_control_count_sum",
    "decision_error_rate_mean_pct",
    "decision_error_rate_std_dev_pct",
]

HEADER_LABELS = {
    "line": "line (-)",
    "iteration_count": "iteration_count (count)",
    "matched_decisions_sum": "matched_decisions_sum (count)",
    "false_control_count_sum": "false_control_count_sum (count)",
    "decision_error_rate_mean_pct": "decision_error_rate_mean (%)",
    "decision_error_rate_std_dev_pct": "decision_error_rate_std_dev (%)",
}

# Warna sengaja seragam agar fokus pembaca pada besar error rate per line.
LINE_COLORS = ["#14B8A6", "#14B8A6", "#14B8A6", "#14B8A6", "#14B8A6"]


def get_csv_value(row, column):
    """Ambil nilai kolom, termasuk CSV yang memakai label dengan satuan."""
    if column in row:
        return row[column]
    prefix = f"{column} ("
    for key, value in row.items():
        if key.startswith(prefix):
            return value
    return ""


def fmt_float(value, digits=6):
    """Format angka float untuk CSV summary."""
    return f"{float(value):.{digits}f}"


def mean(values):
    """Rata-rata aman untuk list kosong."""
    return statistics.fmean(values) if values else 0.0


def std_dev(values):
    """Standar deviasi sample; nol bila data kurang dari dua."""
    return statistics.stdev(values) if len(values) > 1 else 0.0


def read_mitm_false_control(path):
    """Baca detail false control MITM dan kelompokkan per line/iterasi."""
    grouped = defaultdict(list)

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = (get_csv_value(row, "scenario") or "").strip()
            if scenario != SCENARIO:
                continue
            try:
                iteration = (get_csv_value(row, "iteration") or "").strip()
                line = int(get_csv_value(row, "bus"))
                false_control_action = int(get_csv_value(row, "false_control_action"))
            except ValueError:
                continue
            if not iteration:
                continue
            grouped[(line, iteration)].append(false_control_action)

    return grouped


def summarize_per_line(grouped):
    """Hitung total keputusan dan rata-rata error rate untuk tiap line."""
    rates_by_line = defaultdict(list)
    matched_by_line = defaultdict(int)
    false_by_line = defaultdict(int)

    for (line, _iteration), values in grouped.items():
        matched = len(values)
        false_count = sum(values)
        rate = false_count / matched * 100 if matched else 0.0
        rates_by_line[line].append(rate)
        matched_by_line[line] += matched
        false_by_line[line] += false_count

    rows = []
    for line in sorted(rates_by_line):
        rates = rates_by_line[line]
        rows.append(
            {
                "line": line,
                "iteration_count": len(rates),
                "matched_decisions_sum": matched_by_line[line],
                "false_control_count_sum": false_by_line[line],
                "decision_error_rate_mean_pct": fmt_float(mean(rates)),
                "decision_error_rate_std_dev_pct": fmt_float(std_dev(rates)),
            }
        )
    return rows


def write_summary(path, rows):
    """Tulis CSV summary per line dengan label kolom bersatuan."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[HEADER_LABELS[column] for column in SUMMARY_COLUMNS],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    HEADER_LABELS[column]: row.get(column, "")
                    for column in SUMMARY_COLUMNS
                }
            )


def draw_chart(rows, output_path):
    """Gambar bar chart decision error rate per line."""
    if not rows:
        raise ValueError("No MITM false-control rows found.")

    labels = [f"Line {row['line']}" for row in rows]
    means = [float(row["decision_error_rate_mean_pct"]) for row in rows]
    std_devs = [float(row["decision_error_rate_std_dev_pct"]) for row in rows]

    fig, ax = plt.subplots(figsize=(10.5, 6.0), dpi=160)
    fig.patch.set_facecolor("#F8FAFC")
    ax.set_facecolor("#FFFFFF")

    x_positions = list(range(len(rows)))
    bars = ax.bar(
        x_positions,
        means,
        yerr=std_devs,
        capsize=6,
        color=LINE_COLORS[: len(rows)],
        edgecolor="#0F172A",
        linewidth=0.8,
        error_kw={
            "elinewidth": 1.4,
            "ecolor": "#334155",
            "capthick": 1.4,
        },
    )

    for bar, mean_value, std_value in zip(bars, means, std_devs):
        label = f"μ={mean_value:.1f}%\nσ={std_value:.1f}%"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + std_value + 1.2,
            label,
            ha="center",
            va="bottom",
            fontsize=9,
            color="#0F172A",
            fontweight="semibold",
        )

    ax.set_title(
        "MITM Decision Error Rate per Line",
        fontsize=16,
        fontweight="bold",
        color="#0F172A",
        pad=14,
    )
    ax.set_xlabel("Line", fontsize=11, fontweight="semibold", color="#334155")
    ax.set_ylabel("Decision Error Rate (%)", fontsize=11, fontweight="semibold", color="#334155")
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, max(mean + std for mean, std in zip(means, std_devs)) + 12)
    ax.grid(axis="y", color="#CBD5E1", linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)

    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#94A3B8")
    ax.spines["bottom"].set_color("#94A3B8")
    ax.tick_params(axis="both", colors="#334155")

    fig.text(
        0.01,
        0.015,
        "Decision error rate = false control actions / matched decisions × 100. Error bars show standard deviation across iterations.",
        fontsize=8.5,
        color="#475569",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def parse_args():
    """Argumen folder Join, folder Graph, dan folder summary."""
    parser = argparse.ArgumentParser(
        description="Plot MITM decision error rate per line from false_control_detail.csv."
    )
    parser.add_argument(
        "--join-dir",
        type=Path,
        default=DEFAULT_JOIN_DIR,
        help="Graphs/Join folder containing false_control_detail.csv.",
    )
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=DEFAULT_GRAPH_DIR,
        help="Output folder for the PNG chart.",
    )
    parser.add_argument(
        "--summary-dir",
        type=Path,
        default=DEFAULT_SUMMARY_DIR,
        help="Output folder for the per-line summary CSV.",
    )
    return parser.parse_args()


def main():
    """Entry point plotting decision error MITM per line."""
    args = parse_args()
    detail_path = args.join_dir.resolve() / DETAIL_FILE
    graph_path = args.graph_dir.resolve() / "mitm_decision_error_rate_per_line.png"
    summary_path = args.summary_dir.resolve() / "mitm_decision_error_rate_per_line.csv"

    grouped = read_mitm_false_control(detail_path)
    summary_rows = summarize_per_line(grouped)

    write_summary(summary_path, summary_rows)
    draw_chart(summary_rows, graph_path)

    print(f"Wrote chart to {graph_path}")
    print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
