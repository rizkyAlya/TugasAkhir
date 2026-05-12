"""
Visualisasi drift (matplotlib, gaya saintifik).

Masukan:
  - CSV per-bus berlabel (drift_mitm, drift_baseline, v_field, bus, waktu)
  - CSV agregat 34 baris (avg_drift_mitm, avg_drift_baseline, waktu)

Keluaran (PNG, dpi tinggi):
  1) fig_drift_mean_vs_waktu.png — mean drift vs waktu (MITM vs baseline)
  2) fig_drift_mitm_pct_per_bus.png — bar chart mean drift MITM (%) per bus
  3) fig_drift_share_by_bus_pie.png — kontribusi total drift_mitm per bus

Contoh:
  cd Visualisasi
  python plot_trace_drift_science.py
  python plot_trace_drift_science.py --out-dir fig_drift
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EPS = 1e-9

# Palet modern (kontras jelas di background terang; irisan Tailwind-like)
C_MITM = "#4f46e5"  # indigo-600
C_BASE = "#ea580c"  # orange-600
C_BAR = "#0d9488"  # teal-600
C_BAR_EDGE = "#134e4a"  # teal-900
C_GRID = "#e2e8f0"  # slate-200
C_AXES_BG = "#f8fafc"  # slate-50
PIE_COLORS = ["#4f46e5", "#7c3aed", "#db2777", "#059669", "#d97706"]  # indigo, violet, rose, emerald, amber


def apply_science_style() -> None:
    """Parameter rc: tipografi saintifik + nuansa UI modern."""
    mpl.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "figure.facecolor": "white",
            "axes.facecolor": C_AXES_BG,
            "axes.edgecolor": "#cbd5e1",
            "grid.color": C_GRID,
            "font.family": "serif",
            "font.serif": ["DejaVu Serif", "Times New Roman", "Bitstream Vera Serif"],
            "mathtext.fontset": "dejavuserif",
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.linewidth": 0.9,
            "axes.grid": True,
            "grid.alpha": 1.0,
            "grid.linestyle": "-",
            "grid.linewidth": 0.75,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 9,
            "legend.frameon": True,
            "legend.framealpha": 0.96,
            "legend.edgecolor": "#e2e8f0",
            "legend.facecolor": "white",
        }
    )


def plot_mean_drift_vs_waktu(df34: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    x = df34["waktu"].astype(int)
    y_m = df34["avg_drift_mitm"].astype(float)
    y_b = df34["avg_drift_baseline"].astype(float)
    ax.plot(
        x,
        y_m,
        marker="o",
        ms=5,
        lw=2.1,
        color=C_MITM,
        markerfacecolor=C_MITM,
        markeredgecolor="white",
        markeredgewidth=0.6,
        label=r"MITM",
    )
    ax.plot(
        x,
        y_b,
        marker="s",
        ms=4.5,
        lw=2.1,
        color=C_BASE,
        markerfacecolor=C_BASE,
        markeredgecolor="white",
        markeredgewidth=0.6,
        label=r"Baseline",
    )
    ax.set_xlabel(r"Waktu $t$")
    ax.set_ylabel("Rata-rata drift (pu)")
    ax.set_title("Mean drift terhadap waktu")
    ax.legend(loc="best")
    fig.savefig(out)
    plt.close(fig)


def plot_drift_mitm_pct_per_bus(df_lb: pd.DataFrame, out: Path) -> None:
    """Drift MITM relatif terhadap $V_{field}$ (pu), dalam persen."""
    df = df_lb.copy()
    df["drift_mitm_pct"] = 100.0 * df["drift_mitm"].astype(float) / (
        df["v_field"].astype(float).abs() + EPS
    )
    g = df.groupby("bus", as_index=False)["drift_mitm_pct"].mean().sort_values("bus")
    buses = g["bus"].astype(int).to_numpy()
    means = g["drift_mitm_pct"].to_numpy()
    sem = df.groupby("bus")["drift_mitm_pct"].sem().reindex(buses).fillna(0).to_numpy()

    fig, ax = plt.subplots(figsize=(5.8, 4.2))
    x = np.arange(len(buses))
    ax.bar(
        x,
        means,
        yerr=sem,
        capsize=3,
        color=C_BAR,
        edgecolor=C_BAR_EDGE,
        linewidth=0.75,
        error_kw={
            "elinewidth": 1.0,
            "capthick": 1.0,
            "ecolor": "#64748b",
        },
        label="Mean $\\pm$ SEM",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"Bus {b}" for b in buses])
    ax.set_ylabel(
        r"Mean drift MITM (\%)"
    )
    ax.set_xlabel("Bus")
    ax.set_title("Drift MITM per bus")
    ax.legend(loc="upper right")
    fig.savefig(out)
    plt.close(fig)


def plot_drift_share_pie(df_lb: pd.DataFrame, out: Path) -> None:
    """Proporsi total drift MITM (jumlah $|V_{DT}^{mitm}-V_{field}|$) per bus."""
    tot = df_lb.groupby("bus", as_index=False)["drift_mitm"].sum().sort_values("bus")
    labels = [f"Bus {int(b)}" for b in tot["bus"]]
    sizes = tot["drift_mitm"].to_numpy(dtype=float)
    if sizes.sum() <= 0:
        sizes = np.ones_like(sizes)
    colors = PIE_COLORS[: len(sizes)]

    fig, ax = plt.subplots(figsize=(5.5, 5.0))
    ax.pie(
        sizes,
        labels=labels,
        autopct="%1.1f%%",
        colors=colors,
        wedgeprops={"edgecolor": "white", "linewidth": 0.8},
        textprops={"fontsize": 9},
        startangle=90,
    )
    ax.set_title(
        "Kontribusi total drift MITM per bus"
    )
    fig.savefig(out)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--labeled",
        type=Path,
        default=Path("trace_mix.normalized.labeled.csv"),
        help="CSV per-bus berlabel",
    )
    ap.add_argument(
        "--mean34",
        type=Path,
        default=Path("trace_mix.normalized.labeled.by_waktu_mean34.csv"),
        help="CSV 34 baris (mean bus + mean iterasi)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path("fig_drift"),
        help="Folder keluaran PNG",
    )
    args = ap.parse_args()

    lb = args.labeled.resolve()
    m34 = args.mean34.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not lb.is_file():
        raise SystemExit(f"Tidak ditemukan: {lb}")
    if not m34.is_file():
        raise SystemExit(f"Tidak ditemukan: {m34}")

    apply_science_style()

    df_lb = pd.read_csv(lb)
    df34 = pd.read_csv(m34)

    need_lb = {"bus", "waktu", "drift_mitm", "drift_baseline", "v_field"}
    miss = need_lb - set(df_lb.columns)
    if miss:
        raise SystemExit(f"Kolom hilang di labeled: {miss}")
    need34 = {"waktu", "avg_drift_mitm", "avg_drift_baseline"}
    miss34 = need34 - set(df34.columns)
    if miss34:
        raise SystemExit(f"Kolom hilang di mean34: {miss34}")

    plot_mean_drift_vs_waktu(df34, out_dir / "fig_drift_mean_vs_waktu.png")
    plot_drift_mitm_pct_per_bus(df_lb, out_dir / "fig_drift_mitm_pct_per_bus.png")
    plot_drift_share_pie(df_lb, out_dir / "fig_drift_share_by_bus_pie.png")

    print(f"OK: gambar tersimpan di {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
