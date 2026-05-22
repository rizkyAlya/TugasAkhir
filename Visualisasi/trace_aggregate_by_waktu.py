"""
Agregasi trace:

1) Per (iterasi_ke, waktu): rata-rata 5 bus -> satu baris per pasangan iterasi+waktu.

2) Opsional --collapse-iterations: rata-rata lagi antar iterasi 1,2,3 per waktu
   -> hanya kolom waktu (34 baris jika waktu 1..34 di setiap iterasi).

Masukan:
  - CSV per-bus: iterasi_ke, waktu, bus, ... (mis. trace_mix.normalized.labeled.csv)
  - ATAU CSV tahap-1: iterasi_ke, waktu, n_bus, avg_*, ... (tanpa kolom bus)
    lalu gunakan --collapse-iterations saja (tanpa hitung ulang per-bus).

Contoh:
  python trace_aggregate_by_waktu.py
  python trace_aggregate_by_waktu.py --collapse-iterations
  python trace_aggregate_by_waktu.py --in trace_mix.normalized.labeled.by_waktu_mean.csv \\
      --collapse-iterations --out trace_by_waktu_34.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

KEYS = ("iterasi_ke", "waktu")


def aggregate_per_bus(df: pd.DataFrame) -> pd.DataFrame:
    """Mean antar bus per (iterasi_ke, waktu)."""
    for k in KEYS:
        if k not in df.columns:
            raise SystemExit(f"CSV harus punya kolom: {k}")

    df = df.copy()
    df["waktu"] = pd.to_numeric(df["waktu"], errors="coerce")
    df["iterasi_ke"] = pd.to_numeric(df["iterasi_ke"], errors="coerce")

    exclude = set(KEYS) | {"line", "i_path"}
    num_cols = [c for c in df.columns if c not in exclude]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    gmean = df.groupby(list(KEYS), as_index=False)[num_cols].mean()
    gmean.columns = [c if c in KEYS else f"avg_{c}" for c in gmean.columns]

    nbus = df.groupby(list(KEYS), as_index=False).agg(n_bus=("line", "count"))

    out_df = nbus.merge(gmean, on=list(KEYS))

    if "i_path" in df.columns:
        share = (
            df.assign(_inj=(df["i_path"] == "injected").astype(float))
            .groupby(list(KEYS), as_index=False)["_inj"]
            .mean()
            .rename(columns={"_inj": "share_injected"})
        )
        out_df = out_df.merge(share, on=list(KEYS))

    base = ["iterasi_ke", "waktu", "n_bus"]
    pref = [
        "avg_i_before",
        "avg_i_after",
        "avg_v_field",
        "avg_v_dt_mitm",
        "avg_v_dt_baseline",
        "avg_drift_mitm",
        "avg_drift_baseline",
        "avg_breaker_mitm",
        "avg_breaker_baseline",
    ]
    avg_cols = [c for c in pref if c in out_df.columns]
    avg_cols += sorted(c for c in out_df.columns if c.startswith("avg_") and c not in avg_cols)
    tail = ["share_injected"] if "share_injected" in out_df.columns else []
    return out_df[base + avg_cols + tail]


def collapse_over_iterations(stage1: pd.DataFrame) -> pd.DataFrame:
    """Mean antar iterasi_ke per waktu; hilangkan kolom iterasi_ke."""
    if "iterasi_ke" not in stage1.columns or "waktu" not in stage1.columns:
        raise SystemExit("Tahap collapse butuh kolom iterasi_ke dan waktu")

    df = stage1.drop(columns=["iterasi_ke"])
    out = df.groupby("waktu", as_index=False).mean(numeric_only=True)
    out = out.sort_values("waktu", kind="mergesort").reset_index(drop=True)
    out.insert(1, "n_iter_combined", 3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--in",
        dest="inp",
        type=Path,
        default=Path("trace_mix.normalized.labeled.csv"),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Default: .by_waktu_mean.csv atau .by_waktu_mean34.csv jika --collapse-iterations",
    )
    ap.add_argument(
        "--collapse-iterations",
        action="store_true",
        help="Setelah mean per bus, rata-ratakan iterasi 1–3 per waktu (34 baris)",
    )
    ap.add_argument(
        "--collapse-only",
        action="store_true",
        help="Masukan sudah CSV by_waktu_mean (ada iterasi_ke); hanya jalankan collapse",
    )
    args = ap.parse_args()

    inp = args.inp.resolve()
    if not inp.is_file():
        raise SystemExit(f"Tidak ditemukan: {inp}")

    if args.collapse_only:
        stage1 = pd.read_csv(inp)
        out_df = collapse_over_iterations(stage1)
        if args.out is None:
            out = inp.with_name(inp.stem + "_over_iters.csv")
        else:
            out = args.out.resolve()
    else:
        raw = pd.read_csv(inp)
        if "line" not in raw.columns:
            raise SystemExit("Tanpa --collapse-only, CSV masukan harus punya kolom bus")
        out_df = aggregate_per_bus(raw)
        if args.collapse_iterations:
            out_df = collapse_over_iterations(out_df)

        if args.out is None:
            if args.collapse_iterations:
                out = inp.with_name(inp.stem + ".by_waktu_mean34.csv")
            else:
                out = inp.with_name(inp.stem + ".by_waktu_mean.csv")
        else:
            out = args.out.resolve()

    out_df.to_csv(out, index=False, encoding="utf-8", float_format="%.6f")
    msg = f"OK: {out} ({len(out_df)} baris)"
    if "n_iter_combined" in out_df.columns:
        msg += " - mean iterasi 1-3 per waktu"
    elif "iterasi_ke" in out_df.columns:
        msg += " - mean 4 line per iterasi_ke+waktu"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
