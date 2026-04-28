import csv
import os
from datetime import datetime

ATTACK_FLAG = "/tmp/mitm_attack_active"
RUN_ID_FILE = "/tmp/mitm_run_id"
_SESSION_DIR_KEYS = {}
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
    "v_dt",
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
    # Simpan trace terpisah berdasarkan phase, bukan agregat ke logs/mitm/mitm_trace.csv
    # Struktur output:
    # - baseline: logs/baseline/<timestamp>/mitm_trace.csv
    # - mitm    : logs/mitm/<run_id or timestamp>/mitm_trace.csv
    logs_root = os.path.dirname(os.path.dirname(trace_csv_path))

    run_id = str(row[1]).strip() if len(row) > 1 else ""
    phase = str(row[2]).strip() if len(row) > 2 else ""
    phase_bucket = "baseline" if phase == "pre_attack" else "mitm"

    # Gunakan run_id jika ada (dan bukan no_attack). Jika tidak, pakai timestamp sesi.
    if run_id and run_id != "no_attack":
        run_key = run_id
    else:
        key = (logs_root, phase_bucket)
        run_key = _SESSION_DIR_KEYS.get(key)
        if run_key is None:
            run_key = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            _SESSION_DIR_KEYS[key] = run_key

    run_dir = os.path.join(logs_root, phase_bucket, run_key)
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
