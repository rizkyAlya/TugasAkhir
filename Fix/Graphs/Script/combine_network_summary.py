#!/usr/bin/env python3
r"""
Combine network summary.csv files from Graphs/Data/Network.

Run from project root:
    python .\Fix\Graphs\Script\combine_network_summary.py

Outputs:
- Graphs/Join/network_summary_combined.csv
- Graphs/Join/network_summary_table.csv
"""
import argparse
import csv
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
GRAPHS_DIR = SCRIPT_DIR.parent
DEFAULT_DATA_DIR = GRAPHS_DIR / "Data" / "Network"
DEFAULT_OUTPUT_DIR = GRAPHS_DIR / "Join"

SCENARIOS = [
    ("baseline", Path("baseline") / "summary.csv"),
    ("dos_light", Path("dos") / "light" / "summary.csv"),
    ("dos_heavy", Path("dos") / "heavy" / "summary.csv"),
    ("mitm", Path("mitm") / "summary.csv"),
]

BASE_COLUMNS = ["metric", "layer", "source", "destination"]
VALUE_COLUMNS = ["mean", "std_dev"]

HEADER_LABELS = {
    "scenario": "scenario (-)",
    "metric": "metric (-)",
    "layer": "layer (-)",
    "source": "source (-)",
    "destination": "destination (-)",
    "mean": "mean (metric_unit)",
    "std_dev": "std_dev (metric_unit)",
}


def display_header(column):
    return HEADER_LABELS.get(column, column)


def write_display_rows(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[display_header(col) for col in headers])
        writer.writeheader()
        for row in rows:
            writer.writerow({display_header(col): row.get(col, "") for col in headers})


def read_summary(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append({col: (row.get(col, "") or "").strip() for col in BASE_COLUMNS + VALUE_COLUMNS})
        return rows


def collect_rows(data_dir):
    combined = []
    missing = []

    for scenario, rel_path in SCENARIOS:
        path = data_dir / rel_path
        if not path.exists():
            missing.append(path)
            continue
        for row in read_summary(path):
            combined.append({"scenario": scenario, **row})

    return combined, missing


def write_combined_csv(rows, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["scenario", *BASE_COLUMNS, *VALUE_COLUMNS]
    write_display_rows(output_path, headers, rows)


def write_wide_table(rows, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_names = [scenario for scenario, _path in SCENARIOS]
    headers = [*BASE_COLUMNS]
    for scenario in scenario_names:
        headers.extend([f"{scenario}_mean", f"{scenario}_std_dev"])

    grouped = {}
    row_order = []
    for row in rows:
        key = tuple(row[col] for col in BASE_COLUMNS)
        if key not in grouped:
            grouped[key] = {}
            row_order.append(key)
        grouped[key][row["scenario"]] = row

    table_labels = {
        **HEADER_LABELS,
        **{
            f"{scenario}_mean": f"{scenario}_mean (metric_unit)"
            for scenario in scenario_names
        },
        **{
            f"{scenario}_std_dev": f"{scenario}_std_dev (metric_unit)"
            for scenario in scenario_names
        },
    }

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[table_labels[col] for col in headers])
        writer.writeheader()
        for key in row_order:
            out = dict(zip(BASE_COLUMNS, key))
            for scenario in scenario_names:
                scenario_row = grouped[key].get(scenario, {})
                out[f"{scenario}_mean"] = scenario_row.get("mean", "")
                out[f"{scenario}_std_dev"] = scenario_row.get("std_dev", "")
            writer.writerow({table_labels[col]: out.get(col, "") for col in headers})


def parse_args():
    parser = argparse.ArgumentParser(
        description="Gabungkan summary network baseline, DoS light/heavy, dan MITM."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Folder Graphs/Data/Network.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder output CSV gabungan.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    data_dir = args.data_dir.resolve()
    output_dir = args.output_dir.resolve()

    rows, missing = collect_rows(data_dir)
    if not rows:
        raise SystemExit(f"Tidak ada summary.csv yang ditemukan di {data_dir}")

    combined_path = output_dir / "network_summary_combined.csv"
    table_path = output_dir / "network_summary_table.csv"

    write_combined_csv(rows, combined_path)
    write_wide_table(rows, table_path)

    print(f"Wrote {combined_path}")
    print(f"Wrote {table_path}")
    if missing:
        print("Missing summary files:")
        for path in missing:
            print(f"- {path}")


if __name__ == "__main__":
    main()
