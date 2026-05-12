"""
Tambah kolom pada CSV hasil normalisasi (trace_mix.normalized.csv):

1) i_path (nama bisa --col):
   - i_before != i_after  -> "injected"
   - selain itu            -> "normal"

2) drift_mitm      = |v_dt_mitm - v_field|  (drift absolut twin MITM vs tegangan lapangan, pu)
3) drift_baseline  = v_dt_baseline - v_field

Perbandingan arus memakai toleransi epsilon. Drift dalam satuan yang sama dengan V (pu).

Contoh:
  python add_trace_i_status.py
  python add_trace_i_status.py --in trace_mix.normalized.csv --out trace_mix.labeled.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

EPS = 1e-6


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--in",
        dest="inp",
        type=Path,
        default=Path("trace_mix.normalized.csv"),
        help="CSV masukan (koma, kolom i_before / i_after)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="CSV keluaran (default: nama masukan + .labeled sebelum .csv)",
    )
    ap.add_argument(
        "--col",
        type=str,
        default="i_path",
        help="Nama kolom baru (default: i_path)",
    )
    args = ap.parse_args()

    inp = args.inp.resolve()
    if not inp.is_file():
        raise SystemExit(f"Tidak ditemukan: {inp}")

    out = args.out
    if out is None:
        out = inp.with_name(inp.stem + ".labeled" + inp.suffix)
    else:
        out = out.resolve()

    df = pd.read_csv(inp)
    if "i_before" not in df.columns or "i_after" not in df.columns:
        raise SystemExit("CSV harus punya kolom i_before dan i_after")
    need_v = ("v_field", "v_dt_mitm", "v_dt_baseline")
    miss = [c for c in need_v if c not in df.columns]
    if miss:
        raise SystemExit(f"CSV harus punya kolom: {', '.join(miss)}")

    ib = pd.to_numeric(df["i_before"], errors="coerce")
    ia = pd.to_numeric(df["i_after"], errors="coerce")
    injected = ib.notna() & ia.notna() & (ib.sub(ia).abs() > EPS)
    df[args.col] = injected.map({True: "injected", False: "normal"})

    vf = pd.to_numeric(df["v_field"], errors="coerce")
    vm = pd.to_numeric(df["v_dt_mitm"], errors="coerce")
    vb = pd.to_numeric(df["v_dt_baseline"], errors="coerce")
    df["drift_mitm"] = (vm - vf).abs()
    df["drift_baseline"] = vb - vf

    # Urutan kolom: drift setelah v_dt_* lalu breaker lalu i_path
    ordered = [
        "waktu",
        "iterasi_ke",
        "bus",
        "i_before",
        "i_after",
        "v_field",
        "v_dt_mitm",
        "v_dt_baseline",
        "drift_mitm",
        "drift_baseline",
        "breaker_mitm",
        "breaker_baseline",
        args.col,
    ]
    ordered = [c for c in ordered if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    df = df[ordered + rest]

    df.to_csv(out, index=False, encoding="utf-8", float_format="%.6f")
    n_inj = int(injected.sum())
    print(f"OK: {out}")
    print(f"  {args.col}: injected={n_inj}, normal={len(df) - n_inj}")
    print("  drift_mitm: |v_dt_mitm - v_field|; drift_baseline: v_dt_baseline - v_field (pu)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
