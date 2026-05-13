r"""
Satu figure per metrik (RTT, Packet Loss, Throughput). Sumbu Y: RTT (ms),
Packet Loss (%), Throughput (Mbps). Anotasi tiap batang memakai notasi LaTeX
($\mu$ untuk rata, $\sigma$ untuk simpangan baku), selaras kolom mean dan std_dev CSV.

Sumbu X: Baseline | DoS light | DoS heavy. Pada tiap posisi dua batang
(Field vs System) dengan warna berbeda.

Sumber CSV (folder ini):
  summary_baseline.csv, summary_light.csv, summary_heavy.csv

Contoh:
  python plot_dos_network_grouped.py
  python plot_dos_network_grouped.py --dir .
  python plot_dos_network_grouped.py --prefix fig_dos_net
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

C_GRID = "#e5e7eb"
C_AXES_BG = "#fafafa"
# Palet modern (indigo vs cyan), kontras jelas Field / System
C_FIELD = "#6366f1"
C_EDGE_FIELD = "#4338ca"
C_SYSTEM = "#06b6d4"
C_EDGE_SYSTEM = "#0e7490"


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
            "axes.axisbelow": True,
            "grid.alpha": 0.55,
            "grid.linewidth": 0.7,
            "grid.linestyle": "-",
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "legend.frameon": True,
            "legend.framealpha": 0.96,
            "legend.edgecolor": "#e2e8f0",
            "legend.facecolor": "white",
        }
    )


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for c in ("mean", "std_dev"):
        if c not in df.columns:
            raise ValueError(f"{path}: kolom '{c}' tidak ada")
    return df


def _mean_std_for_metric(df: pd.DataFrame, metric: str, layer: str) -> tuple[float, float]:
    row = df[(df["metric"] == metric) & (df["layer"] == layer)]
    if row.empty:
        return float("nan"), float("nan")
    return float(row["mean"].iloc[0]), float(row["std_dev"].iloc[0])


def _metric_slug(metric: str) -> str:
    s = metric.lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_]+", "", s)


# Judul panjang + label Y per satuan; anotasi batang: $\mu$ (rata), $\sigma$ (simpangan baku = stdev CSV)
_METRIC_STYLE: dict[str, dict[str, str | int]] = {
    "RTT": {
        "ylabel": r"RTT (ms)",
        "title": (
            r"Round-trip time (RTT) antar-host: lapisan Field ($h_2 \!\to\! h_3$) "
            r"dan System ($h_3 \!\to\! h_4$)"
        ),
        "fmt_decimals": 2,
    },
    "Packet Loss": {
        "ylabel": r"Packet Loss (\%)",
        "title": ("Persentase Packet Loss pada Tautan Field vs System"),
        "fmt_decimals": 2,
    },
    "Throughput": {
        "ylabel": r"Throughput (Mbps)",
        "title": (
            r"Throughput (Mbps) pada segmen Field ($h_2 \!\to\! h_3$) dan System ($h_3 \!\to\! h_4$)"
        ),
        "fmt_decimals": 2,
    },
}


def _asymmetric_yerr(means: list[float], stds: list[float], floor_frac: float = 5e-4) -> tuple[np.ndarray, np.ndarray]:
    """
    Error bar asimetris dari puncak batang (mean): batas bawah mean - lower > eps
    agar kompatibel dengan sumbu log / mean kecil.
    """
    lowers: list[float] = []
    uppers: list[float] = []
    for m, s in zip(means, stds):
        if not np.isfinite(m) or m <= 0:
            lowers.append(0.0)
            uppers.append(0.0)
            continue
        sig = float(s) if np.isfinite(s) else 0.0
        eps = max(m * floor_frac, 1e-6)
        max_down = max(0.0, m - eps)
        lowers.append(min(sig, max_down))
        uppers.append(sig)
    return np.asarray(lowers), np.asarray(uppers)


def _rtt_log_ylim(
    field_means: list[float],
    field_stds: list[float],
    sys_means: list[float],
    sys_stds: list[float],
) -> tuple[float, float]:
    """Batas Y untuk RTT (log): batas bawah kecil agar bar pendek tidak menempel ke sumbu X."""
    vals: list[float] = []
    for m, s in zip(field_means + sys_means, field_stds + sys_stds):
        if np.isfinite(m) and m > 0:
            vals.append(m)
            if np.isfinite(s):
                low = m - s
                if low > 0:
                    vals.append(low)
    if not vals:
        return 1e-3, 100.0
    vmin_data = min(vals)
    tops = [
        m + (float(s) if np.isfinite(s) else 0.0)
        for m, s in zip(field_means + sys_means, field_stds + sys_stds)
        if np.isfinite(m)
    ]
    ymax = max(tops) if tops else vmin_data * 10.0
    ymin = max(5e-4, vmin_data * 0.08)
    return ymin, ymax * 2.0


def _fmt_bar_label(mean: float, std: float, decimals: int) -> str:
    if not np.isfinite(mean):
        return ""
    spec = f"{{:.{decimals}f}}"
    mtxt = spec.format(mean)
    if np.isfinite(std):
        stxt = spec.format(std)
        return rf"$\mu={mtxt}$" "\n" + rf"$\sigma={stxt}$"
    return rf"$\mu={mtxt}$"


def _annotate_grouped_bars(
    ax: plt.Axes,
    x_centers: np.ndarray,
    means: list[float],
    stds: list[float],
    decimals: int,
    fontsize: float = 7.0,
) -> None:
    for xi, m, s in zip(x_centers, means, stds):
        if not np.isfinite(m):
            continue
        sig = float(s) if np.isfinite(s) else 0.0
        top = float(m) + max(sig, 0.0)
        txt = _fmt_bar_label(m, s, decimals)
        if not txt:
            continue
        ax.text(
            xi,
            top,
            txt,
            ha="center",
            va="bottom",
            fontsize=fontsize,
            linespacing=1.05,
            clip_on=False,
            zorder=5,
        )


def _plot_metric(
    ax: plt.Axes,
    metric: str,
    df_base: pd.DataFrame,
    df_light: pd.DataFrame,
    df_heavy: pd.DataFrame,
) -> None:
    style = _METRIC_STYLE[metric]
    ylabel = str(style["ylabel"])
    title = str(style["title"])
    decimals = int(style["fmt_decimals"])

    if metric == "RTT":
        ylabel = r"RTT (ms) — skala log"

    ax.set_axisbelow(True)
    ax.xaxis.grid(False)

    scenarios = (
        ("Baseline", df_base),
        ("DoS light", df_light),
        ("DoS heavy", df_heavy),
    )
    x = np.arange(len(scenarios))
    width = 0.36

    field_means: list[float] = []
    field_stds: list[float] = []
    sys_means: list[float] = []
    sys_stds: list[float] = []
    for _label, d in scenarios:
        mf, sf = _mean_std_for_metric(d, metric, "field")
        ms, ss = _mean_std_for_metric(d, metric, "system")
        field_means.append(mf)
        field_stds.append(sf)
        sys_means.append(ms)
        sys_stds.append(ss)

    if metric == "RTT":
        ymin, ymax = _rtt_log_ylim(field_means, field_stds, sys_means, sys_stds)
        fm = np.asarray(field_means, dtype=float)
        sm = np.asarray(sys_means, dtype=float)
        field_h = np.maximum(fm - ymin, 1e-12)
        sys_h = np.maximum(sm - ymin, 1e-12)
        f_lo, f_hi = _asymmetric_yerr(field_means, field_stds)
        s_lo, s_hi = _asymmetric_yerr(sys_means, sys_stds)
        ax.bar(
            x - width / 2,
            field_h,
            width,
            bottom=ymin,
            yerr=[f_lo, f_hi],
            label="Field (h2→h3)",
            color=C_FIELD,
            edgecolor=C_EDGE_FIELD,
            linewidth=0.65,
            capsize=3,
            zorder=3,
            error_kw={
                "linewidth": 1.05,
                "capthick": 1.05,
                "color": C_EDGE_FIELD,
                "zorder": 3,
            },
        )
        ax.bar(
            x + width / 2,
            sys_h,
            width,
            bottom=ymin,
            yerr=[s_lo, s_hi],
            label="System (h3→h4)",
            color=C_SYSTEM,
            edgecolor=C_EDGE_SYSTEM,
            linewidth=0.65,
            capsize=3,
            zorder=3,
            error_kw={
                "linewidth": 1.05,
                "capthick": 1.05,
                "color": C_EDGE_SYSTEM,
                "zorder": 3,
            },
        )
        ax.set_yscale("log")
        hi_ann = max(
            float(m + (float(s) if np.isfinite(s) else 0.0))
            for m, s in zip(field_means + sys_means, field_stds + sys_stds)
            if np.isfinite(m)
        )
        ax.set_ylim(ymin, max(ymax, hi_ann * 1.35))
    else:
        ax.bar(
            x - width / 2,
            field_means,
            width,
            yerr=field_stds,
            label="Field (h2→h3)",
            color=C_FIELD,
            edgecolor=C_EDGE_FIELD,
            linewidth=0.65,
            capsize=3,
            zorder=3,
            error_kw={
                "linewidth": 1.05,
                "capthick": 1.05,
                "color": C_EDGE_FIELD,
                "zorder": 3,
            },
        )
        ax.bar(
            x + width / 2,
            sys_means,
            width,
            yerr=sys_stds,
            label="System (h3→h4)",
            color=C_SYSTEM,
            edgecolor=C_EDGE_SYSTEM,
            linewidth=0.65,
            capsize=3,
            zorder=3,
            error_kw={
                "linewidth": 1.05,
                "capthick": 1.05,
                "color": C_EDGE_SYSTEM,
                "zorder": 3,
            },
        )

    xf = x - width / 2
    xs = x + width / 2
    _annotate_grouped_bars(ax, xf, field_means, field_stds, decimals)
    _annotate_grouped_bars(ax, xs, sys_means, sys_stds, decimals)

    if metric != "RTT":
        tops: list[float] = []
        for m, s in zip(field_means + sys_means, field_stds + sys_stds):
            if np.isfinite(m):
                sig = float(s) if np.isfinite(s) else 0.0
                tops.append(float(m) + max(sig, 0.0))
        if tops:
            hi = max(tops)
            pad = max(0.26 * hi, 0.12 * max(ax.get_ylim()[1], hi), 1e-6)
            ax.set_ylim(0.0, hi + pad)

    ax.set_xticks(x)
    ax.set_xticklabels([s[0] for s in scenarios])
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=9, pad=10)
    ax.legend(loc="best")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tiga PNG terpisah: RTT, Packet Loss, Throughput (Baseline + DoS light/heavy di X).",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Folder berisi summary_baseline.csv, summary_light.csv, summary_heavy.csv",
    )
    parser.add_argument(
        "--baseline-csv",
        type=Path,
        default=None,
        help="Default: <dir>/summary_baseline.csv",
    )
    parser.add_argument(
        "--light-csv",
        type=Path,
        default=None,
        help="Default: <dir>/summary_light.csv",
    )
    parser.add_argument(
        "--heavy-csv",
        type=Path,
        default=None,
        help="Default: <dir>/summary_heavy.csv",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="fig_dos_network",
        help="Awalan nama file: <prefix>_<slug>.png",
    )
    args = parser.parse_args()
    d = args.dir.resolve()
    df_base = _load(args.baseline_csv or (d / "summary_baseline.csv"))
    df_light = _load(args.light_csv or (d / "summary_light.csv"))
    df_heavy = _load(args.heavy_csv or (d / "summary_heavy.csv"))

    metrics = ["RTT", "Packet Loss", "Throughput"]
    apply_style()

    saved: list[Path] = []
    for metric in metrics:
        fig, ax = plt.subplots(1, 1, figsize=(6.6, 4.55))
        _plot_metric(ax, metric, df_base, df_light, df_heavy)
        fig.tight_layout()
        slug = _metric_slug(metric)
        out = (d / f"{args.prefix}_{slug}.png").resolve()
        fig.savefig(out)
        plt.close(fig)
        saved.append(out)

    for p in saved:
        print(f"Disimpan: {p}")


if __name__ == "__main__":
    main()
