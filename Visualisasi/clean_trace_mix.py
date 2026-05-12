"""
Normalisasi trace_mix.csv:
  - delimiter titik koma -> koma (RFC-style CSV)
  - hapus kolom kosong di akhir (Unnamed)
  - header: Waktu -> waktu; integer untuk waktu/iterasi_ke/bus/breaker
  - float 6 desimal

Jalankan dari folder ini setelah menutup trace_mix.csv di editor:
  python clean_trace_mix.py

Secara default membaca trace_mix.csv dan menimpa berkas yang sama
(menulis ke .tmp lalu replace). Gunakan --in/--out untuk path lain.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed", na=False)]
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"Waktu": "waktu"})
    for c in ("waktu", "iterasi_ke", "bus", "breaker_mitm", "breaker_baseline"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=Path("trace_mix.csv"))
    ap.add_argument("--out", type=Path, default=None, help="Default: sama dengan --in")
    args = ap.parse_args()
    inp = args.inp.resolve()
    out = (args.out or args.inp).resolve()

    head = inp.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    sep = ";" if head and ";" in head[0] else ","
    df = pd.read_csv(inp, sep=sep)
    df = normalize(df)

    tmp = out.with_suffix(out.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8", float_format="%.6f")
    tmp.replace(out)
    print(f"OK: {out} ({len(df)} baris, {len(df.columns)} kolom)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
