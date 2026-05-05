import csv
import json
import os
from datetime import datetime

ATTACK_FLAG = "/tmp/mitm_attack_active"
RUN_ID_FILE = "/tmp/mitm_run_id"
# Absolute path ke logs/runs/<run_id>/ ditulis orchestrator di setiap host Mininet.
RUN_ROOT_HOST_FILE = "/tmp/cyber_range_run_root"
MITM_PROXY_SNAPSHOT_FILE = "/tmp/mitm_proxy_snapshot.json"
_SESSION_DIR_KEYS = {}


def read_run_root():
    """Path ke logs/runs/<run_id>/ jika ada; selain itu None."""
    try:
        if os.path.exists(RUN_ROOT_HOST_FILE):
            with open(RUN_ROOT_HOST_FILE, "r", encoding="utf-8") as f:
                p = f.read().strip()
                if p and os.path.isdir(p):
                    return p
    except Exception:
        pass
    return None

# Hanya pengukuran gateway (h3): V/I in & out; V_dt + breaker dari/ke h4 via OPC UA.
# Baseline vs MITM: folder dipilih dari flag serangan (bukan kolom di CSV).
TRACE_HEADER = [
    "timestamp",
    "iterasi_ke",
    "run_id",
    "bus",
    "v_berfore",
    "v_after",
    "i_before",
    "i_after",
    "v_dt",
    "breaker_cmd",
    "breaker_fb",
]


def ensure_trace_csv(trace_csv_path):
    """Legacy stub path; jika RUN_ROOT aktif, berkas dibuat saat append pertama."""
    if read_run_root():
        return
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
    """
    row: [timestamp, iterasi_ke, run_id, bus, v_berfore, v_after, i_before, i_after, v_dt, breaker_cmd, breaker_fb]

    Unified: logs/runs/<run_id>/trace/<baseline|mitm>/trace.csv
    (RUN_ROOT_HOST_FILE menunjuk ke logs/runs/<run_id>).

    Legacy: logs/<baseline|mitm>/<run_key>/trace.csv dari placeholder trace_csv_path.
    """
    if len(row) != len(TRACE_HEADER):
        raise ValueError(
            f"mitm_trace row length {len(row)} != header {len(TRACE_HEADER)}: {TRACE_HEADER}"
        )

    phase_bucket = "mitm" if os.path.exists(ATTACK_FLAG) else "baseline"

    run_root = read_run_root()
    if run_root:
        run_trace_csv = os.path.join(run_root, "trace", phase_bucket, "trace.csv")
        os.makedirs(os.path.dirname(run_trace_csv), exist_ok=True)
    else:
        logs_root = os.path.dirname(os.path.dirname(trace_csv_path))
        run_id = str(row[2]).strip() if len(row) > 2 else ""
        if run_id and run_id != "no_attack":
            run_key = run_id
        else:
            key = (logs_root, phase_bucket)
            run_key = _SESSION_DIR_KEYS.get(key)
            if run_key is None:
                run_key = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                _SESSION_DIR_KEYS[key] = run_key
        run_dir = os.path.join(logs_root, phase_bucket, run_key)
        run_trace_csv = os.path.join(run_dir, "trace.csv")
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


def read_mitm_proxy_snapshot(bus: int):
    """Ambil snapshot latest before/after dari proxy untuk bus tertentu."""
    try:
        if not os.path.exists(MITM_PROXY_SNAPSHOT_FILE):
            return None
        with open(MITM_PROXY_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        by_bus = data.get("by_bus", {})
        item = by_bus.get(str(bus))
        if not isinstance(item, dict):
            return None
        return item
    except Exception:
        return None


def write_mitm_proxy_snapshot(bus: int, v_before, v_after, i_before, i_after):
    """Update snapshot before/after dari proxy (shared via filesystem host)."""
    data = {"by_bus": {}, "updated_at": now_ts()}
    try:
        if os.path.exists(MITM_PROXY_SNAPSHOT_FILE):
            with open(MITM_PROXY_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f) or {}
            if isinstance(loaded, dict):
                data.update(loaded)
                if not isinstance(data.get("by_bus"), dict):
                    data["by_bus"] = {}
    except Exception:
        data = {"by_bus": {}, "updated_at": now_ts()}

    data["updated_at"] = now_ts()
    data["by_bus"][str(bus)] = {
        "v_before": "" if v_before is None else f"{float(v_before):.6f}",
        "v_after": "" if v_after is None else f"{float(v_after):.6f}",
        "i_before": "" if i_before is None else f"{float(i_before):.6f}",
        "i_after": "" if i_after is None else f"{float(i_after):.6f}",
    }

    tmp = f"{MITM_PROXY_SNAPSHOT_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, MITM_PROXY_SNAPSHOT_FILE)
