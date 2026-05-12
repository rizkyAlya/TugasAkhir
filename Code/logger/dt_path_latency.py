"""
Pengukuran delay jalur data field/RTU (h2) -> digital twin (h4) lewat gateway OPC (h3).

Menggunakan pasangan timestamp di log host (baris DT_PATH_LAT) yang disinkronkan
dengan siklus counter di Modbus HR 95 -> OPC DT_path_probe.

Dipanggil setelah collect_data jaringan DoS; orchestrator menjalankan DoS ulang
agar lalu lintas serangan aktif selama sampling.
"""
import csv
import os
import re
import statistics
import time

NUM_RUNS = 3
SAMPLE_SECONDS = 20

_DT_LINE = re.compile(r"DT_PATH_LAT,h([24]),([0-9.]+),(\d+)")


def _file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _read_new_bytes(path, start_off):
    if not os.path.isfile(path):
        return b"", start_off
    with open(path, "rb") as f:
        f.seek(start_off)
        chunk = f.read()
    return chunk, start_off + len(chunk)


def _parse_dt_events(blob):
    """Return list of (host, ts, cycle_id) from log bytes."""
    text = blob.decode("utf-8", errors="replace")
    out = []
    for line in text.splitlines():
        m = _DT_LINE.search(line)
        if m:
            out.append((m.group(1), float(m.group(2)), int(m.group(3))))
    return out


def _pair_latencies_ms(events_h2, events_h4):
    """
    Untuk tiap cycle_id: h2_ts = waktu RTU selesai batch (tulis HR95),
    h4_ts = waktu pertama h4 melihat nilai probe sama di OPC.
    """
    h2_by = {}
    for _h, ts, cid in events_h2:
        if cid == 0:
            continue
        h2_by[cid] = ts

    h4_first = {}
    for _h, ts, cid in events_h4:
        if cid == 0:
            continue
        if cid not in h4_first:
            h4_first[cid] = ts

    deltas_ms = []
    for cid, t2 in h4_first.items():
        if cid not in h2_by:
            continue
        t0 = h2_by[cid]
        dt = (t2 - t0) * 1000.0
        if 0 <= dt <= 60_000.0:
            deltas_ms.append(dt)
    return deltas_ms


def collect_dt_path_latency(
    net,
    out_dir,
    dos_mode_label,
    host_log_dir,
    num_runs=NUM_RUNS,
    sample_seconds=SAMPLE_SECONDS,
):
    """
    num_runs: jumlah jendela sampling berturut-turut (default 3).
    Membaca penambahan baris di logs/host/<run>/h2.log dan h4.log.
    """
    del net  # reserved for future (e.g. remote pull)
    os.makedirs(out_dir, exist_ok=True)
    h2_log = os.path.join(host_log_dir, "h2.log")
    h4_log = os.path.join(host_log_dir, "h4.log")

    detail_path = os.path.join(out_dir, f"dt_path_latency_{dos_mode_label}_runs.csv")
    summary_path = os.path.join(out_dir, f"dt_path_latency_{dos_mode_label}_summary.csv")

    run_means = []
    run_rows = []

    off_h2 = _file_size(h2_log)
    off_h4 = _file_size(h4_log)

    print(
        f"\n[dt_path_latency] DoS={dos_mode_label}: {num_runs} jendela x {sample_seconds}s "
        f"(h2->h4 via OPC probe). Log: {h2_log} / {h4_log}"
    )

    for run in range(1, num_runs + 1):
        print(f"[dt_path_latency] Run {run}/{num_runs}: sampling {sample_seconds}s...")
        time.sleep(sample_seconds)

        blob_h2, off_h2 = _read_new_bytes(h2_log, off_h2)
        blob_h4, off_h4 = _read_new_bytes(h4_log, off_h4)

        ev2 = _parse_dt_events(blob_h2)
        ev4 = _parse_dt_events(blob_h4)
        deltas = _pair_latencies_ms(ev2, ev4)

        if deltas:
            mean_ms = statistics.mean(deltas)
            std_ms = statistics.stdev(deltas) if len(deltas) > 1 else 0.0
            mn = min(deltas)
            mx = max(deltas)
            run_means.append(mean_ms)
        else:
            mean_ms = std_ms = mn = mx = ""
            print(f"[dt_path_latency] Run {run}: tidak ada pasangan h2/h4 (cek log / probe).")

        run_rows.append(
            [
                dos_mode_label,
                run,
                len(deltas),
                round(mean_ms, 4) if deltas else "",
                round(std_ms, 4) if deltas else "",
                round(mn, 4) if deltas else "",
                round(mx, 4) if deltas else "",
            ]
        )

    with open(detail_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "dos_mode",
                "run",
                "n_samples",
                "mean_latency_ms",
                "stdev_latency_ms",
                "min_ms",
                "max_ms",
            ]
        )
        w.writerows(run_rows)

    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dos_mode", "metric", "value"])
        w.writerow([dos_mode_label, "n_runs", num_runs])
        if run_means:
            w.writerow(
                [
                    dos_mode_label,
                    "mean_of_run_means_ms",
                    round(statistics.mean(run_means), 4),
                ]
            )
            w.writerow(
                [
                    dos_mode_label,
                    "stdev_of_run_means_ms",
                    round(statistics.stdev(run_means), 4) if len(run_means) > 1 else 0.0,
                ]
            )
        else:
            w.writerow([dos_mode_label, "mean_of_run_means_ms", ""])
            w.writerow([dos_mode_label, "stdev_of_run_means_ms", ""])

    print(f"[dt_path_latency] Detail: {detail_path}")
    print(f"[dt_path_latency] Ringkasan: {summary_path}")
    return detail_path, summary_path
