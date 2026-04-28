import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np

# 1. LOAD DATA
file_path = "data2.csv"
df = pd.read_csv(file_path, delimiter=';')

# Normalisasi nilai dan skenario agar plotting konsisten
df["scenario"] = df["scenario"].astype(str).str.replace("-", "_", regex=False)
df["mean"] = pd.to_numeric(df["mean"], errors="coerce")
df["std_dev"] = pd.to_numeric(df["std_dev"], errors="coerce")

# 2. SET OUTPUT FOLDER
output_dir = "graph2"
os.makedirs(output_dir, exist_ok=True)

# Bersihkan file PNG lama agar output hanya berisi grafik terbaru
for old_file in os.listdir(output_dir):
    if old_file.lower().endswith(".png"):
        os.remove(os.path.join(output_dir, old_file))

# 3. DEFINISI URUTAN SCENARIO
scenario_order = [
    "baseline_dos",
    "dos_light",
    "dos_heavy",
    "baseline_mitm",
    "mitm"
]

scenario_labels = {
    "baseline_dos": "Baseline (DoS)",
    "dos_light": "DoS Light",
    "dos_heavy": "DoS Heavy",
    "baseline_mitm": "Baseline (MITM)",
    "mitm": "MITM"
}

# 4. DEFINISI LAYER & METRIK TARGET
layers = ["field", "system"]
metric_order = ["RTT", "packet_loss", "throughput"]


def annotate_mean_std(ax, bars, means, stds):
    """
    Tampilkan dua label per bar:
    - mean (mu) di dalam/atas bar
    - std dev (sigma) di atas error bar
    """
    y_min, y_max = ax.get_ylim()
    y_span = y_max - y_min if y_max > y_min else 1
    mean_offset = 0.02 * y_span
    std_offset = 0.045 * y_span

    for bar, mean_val, std_val in zip(bars, means, stds):
        x = bar.get_x() + (bar.get_width() / 2)
        y = bar.get_height()

        # Label mean: selalu di atas bar agar bar pendek tetap terbaca
        mean_y = y + mean_offset
        ax.text(
            x,
            mean_y,
            f"μ={mean_val:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
            color="black",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.7, pad=1.2),
            clip_on=False,
        )

        # Label std dev: selalu di atas error bar agar tidak ambigu
        std_top = y + std_val
        ax.text(
            x,
            std_top + std_offset,
            f"σ={std_val:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
            color="dimgray",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.6, pad=1.0),
            clip_on=False,
        )

# 5. LOOP: 1 GRAFIK PER METRIK (TOTAL 3)
for metric in metric_order:
    subset_metric = df[df["metric"].str.lower() == metric.lower()].copy()
    if subset_metric.empty:
        continue

    # Pivot agar setiap scenario punya kolom mean/std per layer
    pivot_mean = (
        subset_metric.pivot_table(
            index="scenario",
            columns="layer",
            values="mean",
            aggfunc="first"
        )
        .reindex(scenario_order)
    )
    pivot_std = (
        subset_metric.pivot_table(
            index="scenario",
            columns="layer",
            values="std_dev",
            aggfunc="first"
        )
        .reindex(scenario_order)
    )

    # Sisakan scenario yang punya data minimal satu layer
    valid_idx = pivot_mean[layers].notna().any(axis=1)
    pivot_mean = pivot_mean[valid_idx]
    pivot_std = pivot_std[valid_idx]
    if pivot_mean.empty:
        continue

    x = np.arange(len(pivot_mean.index))
    bar_width = 0.38
    labels = [scenario_labels[s] for s in pivot_mean.index]

    fig, ax = plt.subplots(figsize=(12, 7))

    # Field bar
    field_mean = pivot_mean["field"].fillna(0).values
    field_std = pivot_std["field"].fillna(0).values
    bars_field = ax.bar(
        x - bar_width / 2,
        field_mean,
        width=bar_width,
        yerr=field_std,
        capsize=5,
        label="Field Layer",
        color="#4E79A7",
    )

    # System bar
    system_mean = pivot_mean["system"].fillna(0).values
    system_std = pivot_std["system"].fillna(0).values
    bars_system = ax.bar(
        x + bar_width / 2,
        system_mean,
        width=bar_width,
        yerr=system_std,
        capsize=5,
        label="System Layer",
        color="#F28E2B",
    )

    # Beri ruang ekstra di atas bar/error bar untuk label sigma
    max_top = max(np.max(field_mean + field_std), np.max(system_mean + system_std))
    y_upper = max_top * 1.25 if max_top > 0 else 1
    ax.set_ylim(0, y_upper)

    ax.set_title(f"{metric.upper().replace('_', ' ')} Comparison Across Scenarios")
    ax.set_xlabel("Scenario")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend()

    # Y label tergantung metrik
    metric_lower = metric.lower()
    if metric_lower == "rtt":
        ax.set_ylabel("RTT (ms)")
    elif metric_lower == "packet_loss":
        ax.set_ylabel("Packet Loss (%)")
    elif metric_lower == "throughput":
        ax.set_ylabel("Throughput (Mbps)")
    else:
        ax.set_ylabel("Value")

    # Label mean dan std dev dipisah agar mudah dibaca
    annotate_mean_std(ax, bars_field, field_mean, field_std)
    annotate_mean_std(ax, bars_system, system_mean, system_std)

    plt.subplots_adjust(bottom=0.43)

    # 6. SIMPAN (hanya 3 file output)
    filename = f"{metric.lower()}_summary.png"
    plt.savefig(os.path.join(output_dir, filename), dpi=300, bbox_inches="tight")
    plt.close(fig)

# 7. DONE
print("Semua grafik berhasil dibuat di folder 'graph2/' (3 file summary).")