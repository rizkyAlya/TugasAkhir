import csv
import os
from datetime import datetime

ATTACK_FLAG = "/tmp/mitm_attack_active"
RUN_ID_FILE = "/tmp/mitm_run_id"
TRACE_HEADER = [
    "timestamp",
    "run_id",
    "phase",
    "source",
    "event",
    "bus",
    "v_raw",
    "i_raw",
    "v_final",
    "i_final",
    "breaker_cmd",
    "breaker_fb",
    "ttl",
    "client",
    "detail",
]


def ensure_trace_csv(trace_csv_path):
    os.makedirs(os.path.dirname(trace_csv_path), exist_ok=True)
    if not os.path.exists(trace_csv_path):
        with open(trace_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(TRACE_HEADER)


def get_run_id():
    try:
        if os.path.exists(RUN_ID_FILE):
            with open(RUN_ID_FILE, "r", encoding="utf-8") as f:
                value = f.read().strip()
                if value:
                    return value
    except Exception:
        pass
    return "no_attack"


def get_phase_label():
    return "post_attack" if os.path.exists(ATTACK_FLAG) else "pre_attack"


def append_trace_row(trace_csv_path, row):
    # 1) Tetap simpan ke file agregat (kompatibel dengan alur lama)
    with open(trace_csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)

    # 2) Simpan juga per-run agar histori tiap run tidak tercampur/tertimpa
    # row[1] = run_id berdasarkan format trace yang dipakai semua host.
    run_id = str(row[1]).strip() if len(row) > 1 else ""
    if run_id:
        base_dir = os.path.dirname(trace_csv_path)
        run_dir = os.path.join(base_dir, "runs", run_id)
        run_trace_csv = os.path.join(run_dir, "mitm_trace.csv")
        os.makedirs(run_dir, exist_ok=True)
        if not os.path.exists(run_trace_csv):
            with open(run_trace_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(TRACE_HEADER)
        with open(run_trace_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
