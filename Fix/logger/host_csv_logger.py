import csv
import os
import time

RUN_ROOT_HOST_FILE = "/tmp/cyber_range_run_root"

DATA_HEADERS = {
    "h1": [
        "cycle_id",
        "ts_sent",
        "bus",
        "V_sent",
        "I_sent",
        "P_bus",
        "Q_bus",
        "power_factor",
        "breaker_actual",
    ],
    "h2": [
        "cycle_id",
        "ts_received",
        "ts_sent",
        "bus",
        "V_sent",
        "I_sent",
        "power_factor",
        "breaker_actual",
    ],
    "h3": [
        "cycle_id",
        "ts_received",
        "ts_sent",
        "bus",
        "V_received",
        "I_received",
        "P_sent",
        "Q_sent",
        "breaker_actual",
    ],
    "h4": [
        "cycle_id",
        "ts_received",
        "bus",
        "line",
        "V_DT",
        "I_line",
        "breaker_actual",
    ],
}

CONTROL_HEADERS = {
    "h1": ["cmd_id", "origin_cycle", "ts_received", "breaker_DT"],
    "h2": ["cmd_id", "origin_cycle", "ts_received", "ts_sent", "breaker_DT"],
    "h3": ["cmd_id", "origin_cycle", "ts_received", "ts_sent", "breaker_DT"],
    "h4": ["cmd_id", "origin_cycle", "ts_sent", "breaker_DT"],
}


def timestamp():
    return f"{time.time():.6f}"


def breaker_state(values):
    if isinstance(values, dict):
        return ";".join(f"{int(k)}:{int(values[k])}" for k in sorted(values))
    return str(values)


def _read_run_root():
    try:
        if os.path.exists(RUN_ROOT_HOST_FILE):
            with open(RUN_ROOT_HOST_FILE, "r", encoding="utf-8") as f:
                value = f.read().strip()
            if value:
                return value
    except Exception:
        pass
    return None


def _fallback_root():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_dir, "logs")


def _csv_path(plane, host):
    root = _read_run_root() or _fallback_root()
    return os.path.join(root, "host_csv", plane, f"{host}.csv")


def _append_row(path, headers, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in headers})


def log_data_plane(host, row):
    headers = DATA_HEADERS[host]
    _append_row(_csv_path("data_plane", host), headers, row)


def log_control_plane(host, row):
    headers = CONTROL_HEADERS[host]
    _append_row(_csv_path("control_plane", host), headers, row)
