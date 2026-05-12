"""
Pengukuran delay jalur data field/RTU (h2) -> digital twin (h4) lewat gateway OPC (h3).

Menggunakan pasangan timestamp di log host (baris DT_PATH_LAT) yang disinkronkan
dengan siklus counter di Modbus HR 95 -> OPC DT_path_probe.

Dipanggil setelah collect_data jaringan DoS; orchestrator menjalankan DoS ulang
agar lalu lintas serangan aktif selama sampling.

Output tambahan: tabel gabungan per probe (CSV) untuk melihat OK vs MISSING_H4
dan delta waktu per probe.
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


def _h2_last_h4_first(events_h2, events_h4):
    """h2: timestamp terakhir per probe; h4: timestamp pertama per probe."""
    h2_last = {}
    for _h, ts, cid in events_h2:
        if cid == 0:
            continue
        h2_last[cid] = ts

    h4_first = {}
    for _h, ts, cid in events_h4:
        if cid == 0:
            continue
        if cid not in h4_first:
            h4_first[cid] = ts
    return h2_last, h4_first


def _pair_latencies_ms(events_h2, events_h4):
    """
    Untuk tiap cycle_id: h2_ts = waktu RTU selesai batch (tulis HR95),
    h4_ts = waktu pertama h4 melihat nilai probe sama di OPC.
    """
    h2_by, h4_first = _h2_last_h4_first(events_h2, events_h4)

    deltas_ms = []
    for cid, t2 in h4_first.items():
        if cid not in h2_by:
            continue
        t0 = h2_by[cid]
        dt = (t2 - t0) * 1000.0
        if 0 <= dt <= 60_000.0:
            deltas_ms.append(dt)
    return deltas_ms


def _build_probe_join_rows(events_h2, events_h4):
    """
    Satu baris per probe yang muncul di h2 dan/atau h4 pada jendela log.
    Kolom: probe, t_h2_unix, t_h4_unix, delta_ms, status
    """
    h2_last, h4_first = _h2_last_h4_first(events_h2, events_h4)
    all_ids = sorted(set(h2_last) | set(h4_first))
    rows = []
    for cid in all_ids:
        t2 = h2_last.get(cid)
        t4 = h4_first.get(cid)
        if t2 is not None and t4 is not None:
            delta_ms = (t4 - t2) * 1000.0
            if delta_ms < 0:
                status = "OUT_OF_ORDER"
            elif delta_ms > 60_000.0:
                status = "INVALID_DELTA"
            else:
                status = "OK"
            rows.append(
                [
                    cid,
                    f"{t2:.6f}",
                    f"{t4:.6f}",
                    f"{round(delta_ms, 4):.4f}",
                    status,
                ]
            )
        elif t2 is not None:
            rows.append([cid, f"{t2:.6f}", "", "", "MISSING_H4"])
        else:
            rows.append([cid, "", f"{t4:.6f}", "", "MISSING_H2"])
    return rows


def _join_counts(rows):
    """Hitung status dari baris join (tanpa header)."""
    n_ok = n_missing_h4 = n_missing_h2 = n_bad = 0
    for r in rows:
        st = r[4] if len(r) > 4 else ""
        if st == "OK":
            n_ok += 1
        elif st == "MISSING_H4":
            n_missing_h4 += 1
        elif st == "MISSING_H2":
            n_missing_h2 += 1
        else:
            n_bad += 1
    return {
        "n_rows": len(rows),
        "n_ok": n_ok,
        "n_missing_h4": n_missing_h4,
        "n_missing_h2": n_missing_h2,
        "n_out_of_order_or_invalid": n_bad,
    }


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
    join_path = os.path.join(out_dir, f"dt_path_probe_join_{dos_mode_label}.csv")
    join_counts_path = os.path.join(
        out_dir, f"dt_path_probe_join_{dos_mode_label}_counts.csv"
    )

    run_means = []
    run_rows = []

    join_start_h2 = _file_size(h2_log)
    join_start_h4 = _file_size(h4_log)
    off_h2 = join_start_h2
    off_h4 = join_start_h4

    chunks_h2 = []
    chunks_h4 = []

    print(
        f"\n[dt_path_latency] DoS={dos_mode_label}: {num_runs} jendela x {sample_seconds}s "
        f"(h2->h4 via OPC probe). Log: {h2_log} / {h4_log}"
    )

    for run in range(1, num_runs + 1):
        print(f"[dt_path_latency] Run {run}/{num_runs}: sampling {sample_seconds}s...")
        time.sleep(sample_seconds)

        blob_h2, off_h2 = _read_new_bytes(h2_log, off_h2)
        blob_h4, off_h4 = _read_new_bytes(h4_log, off_h4)
        chunks_h2.append(blob_h2)
        chunks_h4.append(blob_h4)

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

    blob_all_h2 = b"".join(chunks_h2)
    blob_all_h4 = b"".join(chunks_h4)
    ev_all_h2 = _parse_dt_events(blob_all_h2)
    ev_all_h4 = _parse_dt_events(blob_all_h4)
    join_rows = _build_probe_join_rows(ev_all_h2, ev_all_h4)
    counts = _join_counts(join_rows)

    with open(join_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["probe", "t_h2_unix", "t_h4_unix", "delta_ms", "status"])
        w.writerows(join_rows)

    with open(join_counts_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["dos_mode", dos_mode_label])
        w.writerow(["n_probe_rows", counts["n_rows"]])
        w.writerow(["n_ok", counts["n_ok"]])
        w.writerow(["n_missing_h4", counts["n_missing_h4"]])
        w.writerow(["n_missing_h2", counts["n_missing_h2"]])
        w.writerow(["n_out_of_order_or_invalid", counts["n_out_of_order_or_invalid"]])
        if counts["n_rows"] > 0:
            miss_h4_rate = counts["n_missing_h4"] / counts["n_rows"]
            w.writerow(["missing_h4_rate", round(miss_h4_rate, 6)])

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
        w.writerow([dos_mode_label, "join_n_probe_rows", counts["n_rows"]])
        w.writerow([dos_mode_label, "join_n_ok", counts["n_ok"]])
        w.writerow([dos_mode_label, "join_n_missing_h4", counts["n_missing_h4"]])
        w.writerow([dos_mode_label, "join_n_missing_h2", counts["n_missing_h2"]])

    print(f"[dt_path_latency] Detail: {detail_path}")
    print(f"[dt_path_latency] Ringkasan: {summary_path}")
    print(f"[dt_path_latency] Tabel join per probe: {join_path}")
    print(f"[dt_path_latency] Ringkasan join: {join_counts_path}")
    return detail_path, summary_path, join_path, join_counts_path
