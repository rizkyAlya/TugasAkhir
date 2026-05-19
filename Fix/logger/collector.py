import re
import csv
import datetime
import time
import os
import shlex
import statistics
import yaml

from logger.mitm_trace_logger import publish_collect_run_on_hosts

NUM_RUNS = 1
IPERF_PORT = 5001
IPERF_DURATION_S = 5
IPERF_CONNECT_TIMEOUT_S = 8
IPERF_MAX_RETRIES = 3
IPERF_ERROR_TAIL_CHARS = 220

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEFAULT_CONFIG_PATH = os.path.join(base_dir, "config.yaml")


def _resolve_links_from_config(config_path):
    """
    Resolve measurement links using first host for each role from config.yaml:
    - field link: rtu[0] -> gateway[0]
    - system link: gateway[0] -> dt[0]
    Returns list of tuples: (layer, source_host, destination_ip, destination_host)
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    zones = config.get("topology", {}).get("zones", {})
    hosts_by_role = {}
    ip_by_host = {}

    for zone in zones.values():
        subnet = zone.get("subnet", "")
        subnet_base = subnet.split("/")[0].rsplit(".", 1)[0] if subnet else ""
        for i, host in enumerate(zone.get("hosts", [])):
            name = host.get("name")
            role = host.get("role")
            if not name or not role:
                continue
            hosts_by_role.setdefault(role, []).append(name)
            if subnet_base:
                ip_by_host[name] = f"{subnet_base}.{i + 2}"

    required_roles = ("rtu", "gateway", "dt")
    missing = [r for r in required_roles if r not in hosts_by_role or not hosts_by_role[r]]
    if missing:
        raise ValueError(f"Missing required role(s) in config: {', '.join(missing)}")

    rtu = hosts_by_role["rtu"][0]
    gateway = hosts_by_role["gateway"][0]
    dt_host = hosts_by_role["dt"][0]

    return [
        ("field", rtu, ip_by_host[gateway], gateway),
        ("system", gateway, ip_by_host[dt_host], dt_host),
    ]


def _is_scenario_session_root(logs_path):
    """True jika logs_path = logs/<baseline|mitm|dos>/<run_id>/ (satu sesi orchestrator)."""
    if not logs_path:
        return False
    parent = os.path.basename(os.path.dirname(os.path.abspath(logs_path)))
    return parent in ("baseline", "mitm", "dos")


def _extract_throughput_mbps(output: str):
    """
    Parse throughput dari output iperf2/iperf3 teks.
    Return float Mbps atau None jika tidak ada match valid.
    """
    # Contoh: "4.95 Mbits/sec", "980 Kbits/sec", "1.2 Gbits/sec"
    matches = re.findall(r'(\d+(?:\.\d+)?)\s*([KMG])bits/sec', output, flags=re.IGNORECASE)
    if not matches:
        return None
    value_s, unit = matches[-1]
    value = float(value_s)
    u = unit.upper()
    if u == "K":
        return value / 1000.0
    if u == "G":
        return value * 1000.0
    return value


def collect_data(
    net,
    mode="baseline",
    logs_path=None,
    config_path=None,
    measure_phase=None,
):
    """
    Collect RTT, packet loss, and throughput data.

    Unified (logs_path = logs/<baseline|mitm|dos>/<run_id>/): menyimpan di
    .../network/baseline|mitm|dos/...

    measure_phase: jika diisi, kolom fase ditambahkan pada CSV (selaras trace).

    Legacy flat timestamp (logs_path = logs/<timestamp>/): seperti semula,
    langsung di bawah logs_path tanpa subfolder network/.

    Tanpa logs_path: logs/baseline atau logs/dos/<mode> / logs/<mode>.
    """
    if logs_path:
        if _is_scenario_session_root(logs_path):
            net_prefix = os.path.join(logs_path, "network")
            if mode == "baseline":
                log_dir = os.path.join(net_prefix, "baseline")
            elif mode in ("light", "heavy"):
                log_dir = os.path.join(net_prefix, "dos", mode)
            else:
                log_dir = os.path.join(net_prefix, mode)
        elif mode == "baseline":
            log_dir = os.path.join(logs_path, "baseline")
        elif mode in ("light", "heavy"):
            log_dir = os.path.join(logs_path, "dos", mode)
        else:
            log_dir = os.path.join(logs_path, mode)
    else:
        if mode == "baseline":
            log_dir = os.path.join(base_dir, "logs", "baseline")
        elif mode in ("light", "heavy"):
            log_dir = os.path.join(base_dir, "logs", "dos", mode)
        else:
            log_dir = os.path.join(base_dir, "logs", mode)

    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    try:
        links = _resolve_links_from_config(config_path)
    except Exception as e:
        print(f"Warning: using fallback links, failed to parse config ({e})")
        links = [
            ("field", "h2", "10.0.2.2", "h3"),
            ("system", "h3", "10.0.3.2", "h4"),
        ]

    os.makedirs(log_dir, exist_ok=True)

    rtt_path = os.path.join(log_dir, "rtt.csv")
    loss_path = os.path.join(log_dir, "packet_loss.csv")
    th_path = os.path.join(log_dir, "throughput.csv")
    summary_path = os.path.join(log_dir, "summary.csv")

    print(f"\nStarting data collection mode: {mode}")
    print(f"Saving to: {log_dir}")

    use_fase = measure_phase is not None
    rtt_header = ["timestamp", "run", "layer", "source", "destination", "latency_ms"]
    loss_header = ["timestamp", "run", "layer", "source", "destination", "packet_loss_percent"]
    th_header = [
        "timestamp",
        "run",
        "layer",
        "source",
        "destination",
        "throughput_Mbps",
        "status",
        "error",
        "raw_output_tail",
    ]
    if use_fase:
        rtt_header.insert(2, "fase")
        loss_header.insert(2, "fase")
        th_header.insert(2, "fase")

    # RTT & Packet Loss
    with open(rtt_path, "w", newline="") as rtt_file, \
         open(loss_path, "w", newline="") as loss_file:

        rtt_writer = csv.writer(rtt_file)
        loss_writer = csv.writer(loss_file)

        rtt_writer.writerow(rtt_header)
        loss_writer.writerow(loss_header)

        rtt_summary = {}
        loss_summary = {}

        for layer, host, dest_ip, dest_host in links:
            rtt_summary[(layer, host, dest_host)] = []
            loss_summary[(layer, host, dest_host)] = []

            for run in range(NUM_RUNS):
                publish_collect_run_on_hosts(net, run + 1)
                print(f"[{datetime.datetime.now()}] {mode.upper()} - RTT & Loss: {layer} (Run {run+1})")

                output = net.get(host).cmd(f"ping -c 20 {dest_ip}")

                # RTT parsing
                for line in output.split("\n"):
                    if "time=" in line:
                        latency = re.search(r'time=(\d+\.?\d*)', line)
                        if latency:
                            value = float(latency.group(1))
                            row_rtt = [
                                datetime.datetime.now(),
                                run + 1,
                                layer,
                                host,
                                dest_host,
                                value,
                            ]
                            if use_fase:
                                row_rtt.insert(2, measure_phase)
                            rtt_writer.writerow(row_rtt)
                            rtt_summary[(layer, host, dest_host)].append(value)

                # Packet loss parsing
                for line in output.split("\n"):
                    if "packet loss" in line:
                        loss = re.search(r'(\d+)% packet loss', line)
                        if loss:
                            value = float(loss.group(1))
                            row_loss = [
                                datetime.datetime.now(),
                                run + 1,
                                layer,
                                host,
                                dest_host,
                                value,
                            ]
                            if use_fase:
                                row_loss.insert(2, measure_phase)
                            loss_writer.writerow(row_loss)
                            loss_summary[(layer, host, dest_host)].append(value)

                time.sleep(1)

    # Throughput
    with open(th_path, "w", newline="") as th_file:

        th_writer = csv.writer(th_file)
        th_writer.writerow(th_header)

        th_summary = {}

        for layer, host, dest_ip, dest_host in links:
            th_summary[(layer, host, dest_host)] = []

            for run in range(NUM_RUNS):
                publish_collect_run_on_hosts(net, run + 1)

                print(f"[{datetime.datetime.now()}] {mode.upper()} - Throughput: {layer} (Run {run+1})")
                server_host = dest_host

                throughput = 0.0
                status = "failed"
                error = "parse_failed"
                output_tail = ""

                for attempt in range(1, IPERF_MAX_RETRIES + 1):
                    net.get(server_host).cmd("killall -9 iperf >/dev/null 2>&1 || true")
                    net.get(server_host).cmd(f"iperf -s -p {IPERF_PORT} >/dev/null 2>&1 &")
                    time.sleep(1.2)

                    output = net.get(host).cmd(
                        f"timeout {IPERF_CONNECT_TIMEOUT_S}s iperf -c {dest_ip} -p {IPERF_PORT} -t {IPERF_DURATION_S}"
                    )
                    output_tail = (output or "").strip()[-IPERF_ERROR_TAIL_CHARS:]

                    parsed_value = _extract_throughput_mbps(output or "")
                    if parsed_value is not None:
                        throughput = parsed_value
                        status = "ok"
                        error = ""
                        th_summary[(layer, host, dest_host)].append(throughput)
                        break

                    text = (output or "").lower()
                    if "timed out" in text or "timeout" in text:
                        error = "timeout"
                    elif "connection refused" in text:
                        error = "refused"
                    elif "unable to connect" in text:
                        error = "unreachable"
                    else:
                        error = "parse_failed"
                    status = f"failed_retry_{attempt}"
                    time.sleep(0.6 * attempt)

                row_th = [
                    datetime.datetime.now(),
                    run + 1,
                    layer,
                    host,
                    dest_host,
                    round(throughput, 2),
                    "ok" if throughput > 0 else status,
                    error if throughput == 0 else "",
                    output_tail if throughput == 0 else "",
                ]
                if use_fase:
                    row_th.insert(2, measure_phase)
                th_writer.writerow(row_th)

                net.get(server_host).cmd("killall -9 iperf >/dev/null 2>&1 || true")
                time.sleep(1)

    # Summary
    with open(summary_path, "w", newline="") as sum_file:

        sum_writer = csv.writer(sum_file)
        sum_writer.writerow(["metric","layer","source","destination","mean","std_dev"])

        # RTT
        for key, values in rtt_summary.items():
            if values:
                layer, src, dst = key
                mean = round(statistics.mean(values), 2)
                std = round(statistics.stdev(values), 2) if len(values) > 1 else 0
                sum_writer.writerow(["RTT", layer, src, dst, mean, std])

        # Packet Loss
        for key, values in loss_summary.items():
            if values:
                layer, src, dst = key
                mean = round(statistics.mean(values), 2)
                std = round(statistics.stdev(values), 2) if len(values) > 1 else 0
                sum_writer.writerow(["Packet Loss", layer, src, dst, mean, std])

        # Throughput
        for key, values in th_summary.items():
            if values:
                layer, src, dst = key
                mean = round(statistics.mean(values), 2)
                std = round(statistics.stdev(values), 2) if len(values) > 1 else 0
                sum_writer.writerow(["Throughput", layer, src, dst, mean, std])

    print(f"\nData collection ({mode}) complete")
    print(f"CSVs saved in {log_dir}")
