import re
import csv
import datetime
import time
import os
import statistics

NUM_RUNS = 5

links = [
    ("field", "h2", "10.0.2.2", "h3"),   # h2 → h3
    ("system", "h3", "10.0.3.2", "h4"),  # h3 → h4
]

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
log_dir = os.path.join(base_dir, 'logs', 'baseline')

rtt_path = os.path.join(log_dir, "rtt.csv")
loss_path = os.path.join(log_dir, "packet_loss.csv")
th_path = os.path.join(log_dir, "throughput.csv")
summary_path = os.path.join(log_dir, "summary.csv")

def collect_data(net):
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
                print(f"[{datetime.datetime.now()}] Testing RTT & Packet Loss: {layer} (Run {run+1})")
                output = net.get(host).cmd(f"ping -c 20 {dest_ip}")

                # RTT per packet
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

                # Packet loss
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

    # Throughput
    with open(th_path, "w", newline="") as th_file:
        th_writer = csv.writer(th_file)
        th_writer.writerow(["timestamp","run","layer","source","destination","throughput_Mbps"])

        th_summary = {} 

        for layer, host, dest_ip, dest_host in links:
            th_summary[(layer, host, dest_host)] = []

            for run in range(NUM_RUNS):
                print(f"[{datetime.datetime.now()}] Testing Throughput: {layer} (Run {run+1})")

                server_host = "h3" if layer == "field" else "h4"

                # Kill old iperf server
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

    # Summary CSV
    with open(summary_path, "w", newline="") as sum_file:
        sum_writer = csv.writer(sum_file)
        sum_writer.writerow([
            "metric","layer","source","destination","mean","std_dev"
        ])

        # RTT
        for key, values in rtt_summary.items():
            layer, src, dst = key
            mean = round(statistics.mean(values), 2)
            std = round(statistics.stdev(values), 2) if len(values) > 1 else 0
            sum_writer.writerow(["RTT", layer, src, dst, mean, std])

        # Packet Loss
        for key, values in loss_summary.items():
            layer, src, dst = key
            mean = round(statistics.mean(values), 2)
            std = round(statistics.stdev(values), 2) if len(values) > 1 else 0
            sum_writer.writerow(["Packet Loss", layer, src, dst, mean, std])

        # Throughput
        for key, values in th_summary.items():
            layer, src, dst = key
            mean = round(statistics.mean(values), 2)
            std = round(statistics.stdev(values), 2) if len(values) > 1 else 0
            sum_writer.writerow(["Throughput", layer, src, dst, mean, std])

    print(f"\nBaseline data collection complete\nCSVs saved in {log_dir}")
