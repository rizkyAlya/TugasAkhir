"""
Visualisasi breaker_mitm vs breaker_baseline dari CSV berlabel.

Definisi (selaras dengan RTU: 0 = OPEN, 1 = CLOSE):
  - Decision error (per baris): breaker_mitm != breaker_baseline
    → laju kesalahan keputusan = fraksi baris yang salah × 100% per (bus, iterasi_ke).
  - False control / mismatch: sama secara boolean; bagian "kontrol palsu" ditonjolkan
    lewat timeline status aktual (MITM) vs harapan (baseline).

Keluaran (folder default fig_breaker/):
  1) fig_breaker_decision_error_grouped.png — bar terkelompok: Bus 1–5, seri Iterasi 1–3
  2) fig_breaker_decision_error_mean_sem.png — rata-rata 3 iterasi per bus ± SEM
  3) fig_breaker_timeline_actual_iter{k}.png — step chart status MITM vs waktu
  4) fig_breaker_timeline_overlay_iter{k}.png — overlay baseline vs MITM
  5) breaker_decision_error_rates.csv — per bus & iterasi
  6) breaker_decision_error_pivot_bus_by_iter.csv — pivot bus × iterasi (%)
  7) breaker_mismatch_summary.csv — mismatch & jumlah transisi status MITM
  8) breaker_summary_global.csv — satu baris: total baris & laju mismatch global

Contoh:
  cd Visualisasi
  python plot_breaker_decision_and_control.py
  python plot_breaker_decision_and_control.py --iterasi 2 --timeline-all-iters
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EPS = 1e-12

# Palet (selaras dengan plot_trace_drift_science)
C_GRID = "#e2e8f0"
C_AXES_BG = "#f8fafc"
C_ITER = ("#4f46e5", "#0d9488", "#ea580c")  # iter 1,2,3
C_EXPECT = "#64748b"  # baseline / expected
C_ACTUAL = "#db2777"  # MITM / actual


def apply_style() -> None:
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
            "axes.labelsize": 11,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.linewidth": 0.9,
            "axes.grid": True,
            "grid.alpha": 1.0,
            "grid.linewidth": 0.75,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "legend.frameon": True,
            "legend.framealpha": 0.96,
            "legend.edgecolor": "#e2e8f0",
            "legend.facecolor": "white",
        }
    )


def _sem(a: np.ndarray) -> float:
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) < 2:
        return 0.0
    return float(np.std(a, ddof=1) / np.sqrt(len(a)))


def load_labeled(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    need = {"waktu", "iterasi_ke", "bus", "breaker_mitm", "breaker_baseline"}
    miss = need - set(df.columns)
    if miss:
        raise SystemExit(f"Kolom hilang di CSV: {miss}")
    for c in ("waktu", "iterasi_ke", "bus", "breaker_mitm", "breaker_baseline"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=list(need))
    df["waktu"] = df["waktu"].astype(int)
    df["iterasi_ke"] = df["iterasi_ke"].astype(int)
    df["bus"] = df["bus"].astype(int)
    df["breaker_mitm"] = df["breaker_mitm"].astype(int)
    df["breaker_baseline"] = df["breaker_baseline"].astype(int)
    return df


def decision_error_mask(df: pd.DataFrame) -> pd.Series:
    return df["breaker_mitm"] != df["breaker_baseline"]


def rates_by_bus_iter(df: pd.DataFrame) -> pd.DataFrame:
    """Persentase decision error per (bus, iterasi_ke)."""
    m = decision_error_mask(df)
    tmp = df.assign(_err=m.astype(int))
    g = tmp.groupby(["bus", "iterasi_ke"], as_index=False).agg(
        n_steps=("waktu", "count"),
        n_mismatch=("_err", "sum"),
    )
    g["error_rate_pct"] = 100.0 * g["n_mismatch"] / (g["n_steps"] + EPS)
    return g.sort_values(["bus", "iterasi_ke"])


def plot_grouped_decision_error(rates: pd.DataFrame, out: Path) -> None:
    buses = sorted(rates["bus"].unique())
    iters = sorted(rates["iterasi_ke"].unique())
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    x = np.arange(len(buses))
    n_it = len(iters)
    width = 0.8 / max(n_it, 1)
    for j, it in enumerate(iters):
        sub = rates[rates["iterasi_ke"] == it].set_index("bus").reindex(buses)
        vals = sub["error_rate_pct"].to_numpy(dtype=float)
        offset = (j - (n_it - 1) / 2.0) * width
        color = C_ITER[j % len(C_ITER)]
        ax.bar(
            x + offset,
            vals,
            width,
            label=f"Iterasi {it}",
            color=color,
            edgecolor="white",
            linewidth=0.6,
        )
    ax.set_xticks(x)
    ax.set_xticklabels([f"Bus {b}" for b in buses])
    ax.set_ylabel("Decision error rate (%)")
    ax.set_xlabel("Bus")
    ax.set_title("Decision error rate vs referensi baseline\n(per baris waktu: "
                 r"$breaker_{mitm} \neq breaker_{baseline}$)")
    ax.legend(loc="upper right")
    ax.set_ylim(bottom=0)
    fig.savefig(out)
    plt.close(fig)


def plot_mean_sem_decision_error(rates: pd.DataFrame, out: Path) -> None:
    buses = sorted(rates["bus"].unique())
    means, sems = [], []
    for b in buses:
        sub = rates[rates["bus"] == b]["error_rate_pct"].to_numpy(dtype=float)
        means.append(float(np.mean(sub)) if len(sub) else 0.0)
        sems.append(_sem(sub))
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    x = np.arange(len(buses))
    ax.bar(
        x,
        means,
        yerr=sems,
        capsize=4,
        color="#0d9488",
        edgecolor="#134e4a",
        linewidth=0.75,
        error_kw={"elinewidth": 1.0, "ecolor": "#475569"},
        label="Mean ± SEM (3 iterasi)",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"Bus {b}" for b in buses])
    ax.set_ylabel("Decision error rate (%)")
    ax.set_xlabel("Bus")
    ax.set_title("Rata-rata decision error rate ± SEM\n(agregasi iterasi 1–3)")
    ax.legend(loc="upper right")
    ax.set_ylim(bottom=0)
    fig.savefig(out)
    plt.close(fig)


def _series_for_bus_iter(df: pd.DataFrame, bus: int, it: int) -> pd.DataFrame:
    s = df[(df["bus"] == bus) & (df["iterasi_ke"] == it)].sort_values("waktu")
    return s[["waktu", "breaker_mitm", "breaker_baseline"]]


def plot_timeline_actual(df: pd.DataFrame, out: Path, iterasi: int) -> None:
    buses = sorted(df["bus"].unique())
    fig, axes = plt.subplots(len(buses), 1, figsize=(8.5, 2.0 * len(buses)), sharex=True)
    if len(buses) == 1:
        axes = [axes]
    for ax, bus in zip(axes, buses):
        s = _series_for_bus_iter(df, bus, iterasi)
        t = s["waktu"].to_numpy()
        y = s["breaker_mitm"].to_numpy(dtype=float)
        ax.step(t, y, where="post", color=C_ACTUAL, linewidth=1.6, label="Actual (MITM)")
        ax.fill_between(t, y, step="post", alpha=0.12, color=C_ACTUAL)
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["OPEN", "CLOSE"])
        ax.set_ylabel(f"Bus {bus}", fontweight="bold")
        ax.set_ylim(-0.15, 1.15)
        ax.legend(loc="upper right", fontsize=8)
    fig.suptitle(
        f"Status breaker jalur MITM (OPEN=0, CLOSE=1) — iterasi {iterasi}",
        fontsize=11,
        y=1.01,
    )
    axes[-1].set_xlabel(r"Waktu $t$")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_timeline_overlay(df: pd.DataFrame, out: Path, iterasi: int) -> None:
    buses = sorted(df["bus"].unique())
    fig, axes = plt.subplots(len(buses), 1, figsize=(8.5, 2.0 * len(buses)), sharex=True)
    if len(buses) == 1:
        axes = [axes]
    for ax, bus in zip(axes, buses):
        s = _series_for_bus_iter(df, bus, iterasi)
        t = s["waktu"].to_numpy()
        y_e = s["breaker_baseline"].to_numpy(dtype=float)
        y_a = s["breaker_mitm"].to_numpy(dtype=float)
        ax.step(
            t,
            y_e,
            where="post",
            color=C_EXPECT,
            linewidth=1.5,
            linestyle="--",
            label="Expected (baseline)",
        )
        ax.step(
            t,
            y_a,
            where="post",
            color=C_ACTUAL,
            linewidth=1.2,
            label="Actual (MITM)",
        )
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["OPEN", "CLOSE"])
        ax.set_ylabel(f"Bus {bus}", fontweight="bold")
        ax.set_ylim(-0.15, 1.15)
        ax.legend(loc="upper right", fontsize=8)
    fig.suptitle(
        f"Overlay: expected (baseline) vs actual (MITM) — iterasi {iterasi}",
        fontsize=11,
        y=1.01,
    )
    axes[-1].set_xlabel(r"Waktu $t$")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def count_transitions(y: np.ndarray) -> int:
    if len(y) < 2:
        return 0
    return int(np.sum(y[1:] != y[:-1]))


def build_mismatch_summary(df: pd.DataFrame) -> pd.DataFrame:
    m = decision_error_mask(df)
    tmp = df.assign(_mismatch=m.astype(int))
    rows = []
    for (bus, it), g in tmp.groupby(["bus", "iterasi_ke"]):
        g = g.sort_values("waktu")
        y_m = g["breaker_mitm"].to_numpy(dtype=int)
        rows.append(
            {
                "bus": int(bus),
                "iterasi_ke": int(it),
                "n_timesteps": len(g),
                "n_mismatch": int(g["_mismatch"].sum()),
                "mismatch_rate_pct": 100.0 * float(g["_mismatch"].mean()),
                "n_transitions_mitm": count_transitions(y_m),
            }
        )
    return pd.DataFrame(rows).sort_values(["bus", "iterasi_ke"])


def main() -> int:
    ap = argparse.ArgumentParser(description="Plot decision error & breaker timeline.")
    ap.add_argument(
        "--labeled",
        type=Path,
        default=Path("trace_mix.normalized.labeled.csv"),
        help="CSV berlabel (breaker_mitm, breaker_baseline, waktu, bus, iterasi_ke)",
    )
    ap.add_argument("--out-dir", type=Path, default=Path("fig_breaker"))
    ap.add_argument(
        "--iterasi",
        type=int,
        default=1,
        help="Iterasi untuk gambar timeline (1–3)",
    )
    ap.add_argument(
        "--timeline-all-iters",
        action="store_true",
        help="Juga tulis timeline actual+overlay untuk iterasi 2 dan 3",
    )
    args = ap.parse_args()

    lb = args.labeled.resolve()
    if not lb.is_file():
        raise SystemExit(f"Tidak ditemukan: {lb}")

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_labeled(lb)
    it = int(args.iterasi)
    if it not in set(df["iterasi_ke"].unique()):
        raise SystemExit(f"iterasi_ke={it} tidak ada di data: {sorted(df['iterasi_ke'].unique())}")

    apply_style()

    rates = rates_by_bus_iter(df)
    rates.to_csv(out_dir / "breaker_decision_error_rates.csv", index=False)

    plot_grouped_decision_error(rates, out_dir / "fig_breaker_decision_error_grouped.png")
    plot_mean_sem_decision_error(rates, out_dir / "fig_breaker_decision_error_mean_sem.png")

    pivot = rates.pivot(index="bus", columns="iterasi_ke", values="error_rate_pct")
    pivot.to_csv(out_dir / "breaker_decision_error_pivot_bus_by_iter.csv")

    iters_timeline = sorted(df["iterasi_ke"].unique())
    if args.timeline_all_iters:
        iters_timeline = [int(i) for i in iters_timeline]
    else:
        iters_timeline = [it]

    for it_plot in iters_timeline:
        plot_timeline_actual(
            df, out_dir / f"fig_breaker_timeline_actual_iter{it_plot}.png", it_plot
        )
        plot_timeline_overlay(
            df, out_dir / f"fig_breaker_timeline_overlay_iter{it_plot}.png", it_plot
        )

    summ = build_mismatch_summary(df)
    summ.to_csv(out_dir / "breaker_mismatch_summary.csv", index=False)

    total_m = int(decision_error_mask(df).sum())
    pd.DataFrame(
        [
            {
                "n_rows": len(df),
                "n_mismatch_breaker": total_m,
                "global_mismatch_rate_pct": 100.0 * total_m / (len(df) + EPS),
            }
        ]
    ).to_csv(out_dir / "breaker_summary_global.csv", index=False)

    print(f"OK: keluaran di {out_dir}")
    print(f"  Timeline iterasi: {iters_timeline}")
    print(f"  Total mismatch breaker_mitm vs breaker_baseline: {total_m} / {len(df)}")
    print(
        "  CSV: breaker_decision_error_rates.csv, breaker_decision_error_pivot_bus_by_iter.csv, "
        "breaker_mismatch_summary.csv, breaker_summary_global.csv"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
