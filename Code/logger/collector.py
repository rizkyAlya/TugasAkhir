import re
import csv
import datetime
import time
import os
import statistics
import yaml

NUM_RUNS = 5

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEFAULT_CONFIG_PATH = os.path.join(base_dir, "config.yaml")


def _resolve_links_from_config(config_path):
    """
    Resolve measurement links using first host for each role from config.yaml:
    - field link: rtu[0] -> gateway[0]
    - system link: gateway[0] -> pandapower[0]
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

    required_roles = ("rtu", "gateway", "pandapower")
    missing = [r for r in required_roles if r not in hosts_by_role or not hosts_by_role[r]]
    if missing:
        raise ValueError(f"Missing required role(s) in config: {', '.join(missing)}")

    rtu = hosts_by_role["rtu"][0]
    gateway = hosts_by_role["gateway"][0]
    pandapower = hosts_by_role["pandapower"][0]

    return [
        ("field", rtu, ip_by_host[gateway], gateway),
        ("system", gateway, ip_by_host[pandapower], pandapower),
    ]


def collect_data(net, mode="baseline", logs_path=None, config_path=None):
    """
    Collect RTT, packet loss, and throughput data.
    Saves under logs/[timestamp]/baseline or logs/[timestamp]/dos/<mode> when
    logs_path is set (path to logs/[timestamp], from datetime). Otherwise uses
    logs/baseline or logs/dos/<mode> (legacy).
    """
    if logs_path:
        if mode == "baseline":
            log_dir = os.path.join(logs_path, "baseline")
        elif mode in ("light", "heavy"):
            log_dir = os.path.join(logs_path, "dos", mode)
        else:
            log_dir = os.path.join(logs_path, mode)
    else:
        if mode == "baseline":
            log_dir = os.path.join(base_dir, 'logs', 'baseline')
        else:
            log_dir = os.path.join(base_dir, 'logs', 'dos', mode)

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

    # RTT & Packet Loss
    with open(rtt_path, "w", newline="") as rtt_file, \
         open(loss_path, "w", newline="") as loss_file:

        rtt_writer = csv.writer(rtt_file)
        loss_writer = csv.writer(loss_file)

        rtt_writer.writerow(["timestamp","run","layer","source","destination","latency_ms"])
        loss_writer.writerow(["timestamp","run","layer","source","destination","packet_loss_percent"])

        rtt_summary = {}
        loss_summary = {}

        for layer, host, dest_ip, dest_host in links:
            rtt_summary[(layer, host, dest_host)] = []
            loss_summary[(layer, host, dest_host)] = []

            for run in range(NUM_RUNS):
                print(f"[{datetime.datetime.now()}] {mode.upper()} - RTT & Loss: {layer} (Run {run+1})")

                output = net.get(host).cmd(f"ping -c 20 {dest_ip}")

                # RTT parsing
                for line in output.split("\n"):
                    if "time=" in line:
                        latency = re.search(r'time=(\d+\.?\d*)', line)
                        if latency:
                            value = float(latency.group(1))
                            rtt_writer.writerow([
                                datetime.datetime.now(),
                                run+1,
                                layer,
                                host,
                                dest_host,
                                value
                            ])
                            rtt_summary[(layer, host, dest_host)].append(value)

                # Packet loss parsing
                for line in output.split("\n"):
                    if "packet loss" in line:
                        loss = re.search(r'(\d+)% packet loss', line)
                        if loss:
                            value = float(loss.group(1))
                            loss_writer.writerow([
                                datetime.datetime.now(),
                                run+1,
                                layer,
                                host,
                                dest_host,
                                value
                            ])
                            loss_summary[(layer, host, dest_host)].append(value)

                time.sleep(1)


    # Throughput
    with open(th_path, "w", newline="") as th_file:

        th_writer = csv.writer(th_file)
        th_writer.writerow(["timestamp","run","layer","source","destination","throughput_Mbps"])

        th_summary = {}

        for layer, host, dest_ip, dest_host in links:
            th_summary[(layer, host, dest_host)] = []

            for run in range(NUM_RUNS):

                print(f"[{datetime.datetime.now()}] {mode.upper()} - Throughput: {layer} (Run {run+1})")
                server_host = dest_host

                net.get(server_host).cmd("killall -9 iperf")
                net.get(server_host).cmd("iperf -s -p 5001 &")
                time.sleep(1)

                output = net.get(host).cmd(f"iperf -c {dest_ip} -t 5")

                for line in output.split("\n"):
                    if "Mbits/sec" in line and "sec" in line:
                        parts = line.split()
                        throughput = float(parts[-2])
                        th_writer.writerow([
                            datetime.datetime.now(),
                            run+1,
                            layer,
                            host,
                            dest_host,
                            throughput
                        ])
                        th_summary[(layer, host, dest_host)].append(throughput)
                        break

                net.get(server_host).cmd("killall -9 iperf")
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
