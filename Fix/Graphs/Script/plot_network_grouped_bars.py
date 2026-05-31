#!/usr/bin/env python3
r"""
Create grouped bar charts for network summary comparisons.

Run from project root:
    python .\Fix\Graphs\Script\plot_network_grouped_bars.py

Outputs:
- Graphs/Graph/dos/dos_rtt_grouped_bar.png
- Graphs/Graph/dos/dos_throughput_grouped_bar.png
- Graphs/Graph/mitm/mitm_rtt_grouped_bar.png
- Graphs/Graph/mitm/mitm_throughput_grouped_bar.png
"""
import argparse
import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
GRAPHS_DIR = SCRIPT_DIR.parent
DEFAULT_INPUT = GRAPHS_DIR / "Join" / "network_summary_combined.csv"
DEFAULT_OUTPUT_DIR = GRAPHS_DIR / "Graph"

METRICS = {
    "RTT": {
        "filename": "rtt",
        "ylabel": "Latency (ms)",
        "title": "RTT Comparison",
        "value_fmt": "{:.2f}",
    },
    "Throughput": {
        "filename": "throughput",
        "ylabel": "Throughput (Mbps)",
        "title": "Throughput Comparison",
        "value_fmt": "{:.2f}",
    },
}

COMPARISONS = [
    {
        "name": "dos",
        "title_suffix": "Baseline, Light DoS, and Heavy DoS",
        "scenarios": ["baseline", "dos_light", "dos_heavy"],
        "labels": {
            "baseline": "Baseline",
            "dos_light": "Light DoS",
            "dos_heavy": "Heavy DoS",
        },
        "colors": {
            "baseline": "#2563EB",
            "dos_light": "#F59E0B",
            "dos_heavy": "#EF4444",
        },
    },
    {
        "name": "mitm",
        "title_suffix": "Baseline and MITM",
        "scenarios": ["baseline", "mitm"],
        "labels": {
            "baseline": "Baseline",
            "mitm": "MITM",
        },
        "colors": {
            "baseline": "#2563EB",
            "mitm": "#10B981",
        },
    },
]

ROUTE_COLORS = {
    "field": "#6366f1",
    "system": "#06b6d4",
}

ROUTE_LABELS = {
    "field": "Field",
    "system": "System",
}


def get_csv_value(row, column):
    if column in row:
        return row[column]
    prefix = f"{column} ("
    for key, value in row.items():
        if key.startswith(prefix):
            return value
    return ""


def read_rows(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            metric = (get_csv_value(row, "metric") or "").strip()
            if metric not in METRICS:
                continue
            rows.append(
                {
                    "scenario": (get_csv_value(row, "scenario") or "").strip(),
                    "metric": metric,
                    "layer": (get_csv_value(row, "layer") or "").strip(),
                    "source": (get_csv_value(row, "source") or "").strip(),
                    "destination": (get_csv_value(row, "destination") or "").strip(),
                    "mean": float(get_csv_value(row, "mean") or 0.0),
                    "std_dev": float(get_csv_value(row, "std_dev") or 0.0),
                }
            )
        return rows


def route_legend_label(row):
    layer = ROUTE_LABELS.get(row["layer"], row["layer"].title())
    return f"{layer} ({row['source']} -> {row['destination']})"


def index_rows(rows):
    indexed = {}
    route_order = []
    for row in rows:
        key = (row["metric"], row["layer"], row["source"], row["destination"])
        if key not in route_order:
            route_order.append(key)
        indexed[(row["scenario"], *key)] = row
    return indexed, route_order


def add_bar_annotations(ax, bars, std_devs, fmt):
    is_log = ax.get_yscale() == "log"
    y_min, y_max = ax.get_ylim()
    offset = max((y_max - y_min) * 0.012, 0.01)

    for bar, std_dev in zip(bars, std_devs):
        height = bar.get_height()
        if is_log:
            visible_bottom = max(y_min, 1e-9)
            mean_y = math.sqrt(visible_bottom * max(height, visible_bottom))
            sigma_y = max((height + std_dev) * 1.12, height * 1.25)
        else:
            mean_y = height * 0.52
            sigma_y = height + std_dev + offset

        ax.text(
            bar.get_x() + bar.get_width() / 2,
            mean_y,
            f"$\\mu$={fmt.format(height)}",
            ha="center",
            va="center",
            fontsize=8.5,
            fontweight="bold",
            color="#030303",
        )
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            sigma_y,
            f"$\\sigma$={fmt.format(std_dev)}",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#111827",
        )


def plot_grouped_bar(rows, comparison, metric, output_dir):
    metric_cfg = METRICS[metric]
    indexed, route_order = index_rows(rows)
    route_order = [key for key in route_order if key[0] == metric]

    if not route_order:
        print(f"Skip {comparison['name']} {metric}: no rows")
        return None

    scenarios = comparison["scenarios"]
    x = np.arange(len(scenarios))
    width = min(0.32, 0.72 / len(route_order))

    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=160)
    fig.patch.set_facecolor("#F8FAFC")
    ax.set_facecolor("#FFFFFF")

    use_log_scale = comparison["name"] == "dos" and metric == "RTT"
    if use_log_scale:
        ax.set_yscale("log")

    bar_groups = []
    for idx, key in enumerate(route_order):
        sample_row = None
        means = []
        std_devs = []
        for scenario in scenarios:
            row = indexed.get((scenario, *key), {})
            means.append(float(row.get("mean", 0.0)))
            std_devs.append(float(row.get("std_dev", 0.0)))
            if row and sample_row is None:
                sample_row = row

        color = ROUTE_COLORS.get(key[1], "#64748B")
        positions = x + (idx - (len(route_order) - 1) / 2) * width
        if use_log_scale:
            lower_errors = [min(std, max(mean * 0.9, 1e-3)) for mean, std in zip(means, std_devs)]
            yerr = np.array([lower_errors, std_devs])
        else:
            yerr = std_devs
        bars = ax.bar(
            positions,
            means,
            width,
            yerr=yerr,
            capsize=5,
            label=route_legend_label(sample_row) if sample_row else key[1].title(),
            color=color,
            edgecolor="#0F172A",
            linewidth=0.6,
            error_kw={
                "elinewidth": 1.1,
                "ecolor": "#334155",
                "capthick": 1.1,
            },
        )
        bar_groups.append((bars, std_devs))

    ax.set_xticks(x)
    ax.set_xticklabels([comparison["labels"][scenario] for scenario in scenarios], fontsize=10)
    ax.set_ylabel(metric_cfg["ylabel"], fontsize=11, fontweight="semibold")
    ax.set_xlabel("Test Scenario", fontsize=11, fontweight="semibold")
    ax.set_title(
        f"{metric_cfg['title']}: {comparison['title_suffix']}",
        fontsize=15,
        fontweight="bold",
        pad=14,
        color="#0F172A",
    )
    ax.legend(
        title="Network Segment",
        frameon=True,
        facecolor="#FFFFFF",
        edgecolor="#CBD5E1",
        fontsize=10,
        title_fontsize=10,
        loc="upper left",
    )
    ax.grid(axis="y", linestyle="--", linewidth=0.8, alpha=0.45, color="#94A3B8")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")

    max_mean = max(
        float(indexed.get((scenario, *key), {}).get("mean", 0.0))
        + float(indexed.get((scenario, *key), {}).get("std_dev", 0.0))
        for scenario in scenarios
        for key in route_order
    )
    if use_log_scale:
        positive_values = [
            max(float(indexed.get((scenario, *key), {}).get("mean", 0.0)), 1e-3)
            for scenario in scenarios
            for key in route_order
        ]
        ax.set_ylim(min(positive_values) * 0.45, max(max_mean * 2.2, 1.0))
    else:
        ax.set_ylim(0, max(max_mean * 1.34, 1.0))

    for bars, std_devs in bar_groups:
        add_bar_annotations(ax, bars, std_devs, metric_cfg["value_fmt"])

    note = "Bars show mean values ($\\mu$); error bars and labels show standard deviation ($\\sigma$)."
    if use_log_scale:
        note += " The Y-axis uses a log scale because DoS RTT values differ widely."
    fig.text(0.01, 0.015, note, fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, 0.035, 1, 1))

    scenario_dir = output_dir / comparison["name"]
    scenario_dir.mkdir(parents=True, exist_ok=True)
    output_path = scenario_dir / f"{comparison['name']}_{metric_cfg['filename']}_grouped_bar.png"
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create grouped bar charts for baseline vs DoS and baseline vs MITM network summaries."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Combined CSV from combine_network_summary.py.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Graph output folder.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    rows = read_rows(input_path)
    if not rows:
        raise SystemExit(f"No RTT/Throughput data found in {input_path}")

    written = []
    for comparison in COMPARISONS:
        for metric in METRICS:
            output_path = plot_grouped_bar(rows, comparison, metric, output_dir)
            if output_path:
                written.append(output_path)

    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
