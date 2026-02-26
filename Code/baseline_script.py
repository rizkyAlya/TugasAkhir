import re
import csv
import datetime
import time

links = [
    ("field", "h2", "10.0.2.2"),   # h2 → h3
    ("system", "h3", "10.0.3.2"),  # h3 → h4
]

# RTT & Packet Loss
with open("rtt.csv", "w", newline="") as rtt_file, \
     open("packet_loss.csv", "w", newline="") as loss_file:

    rtt_writer = csv.writer(rtt_file)
    loss_writer = csv.writer(loss_file)

    rtt_writer.writerow(["timestamp","layer","source","destination","latency_ms"])
    loss_writer.writerow(["timestamp","layer","source","destination","packet_loss_percent"])

    for layer, host, dest_ip in links:
        print(f"Testing {layer} layer...")

        output = net.get(host).cmd(f"ping -c 20 {dest_ip}")

        # RTT parsing (per packet)
        for line in output.split("\n"):
            if "time=" in line:
                latency = re.search(r'time=(\d+\.?\d*)', line)
                if latency:
                    rtt_writer.writerow([
                        datetime.datetime.now(),
                        layer,
                        host,
                        dest_ip,
                        latency.group(1)
                    ])

        # Packet loss parsing (summary)
        for line in output.split("\n"):
            if "packet loss" in line:
                loss = re.search(r'(\d+)% packet loss', line)
                if loss:
                    loss_writer.writerow([
                        datetime.datetime.now(),
                        layer,
                        host,
                        dest_ip,
                        loss.group(1)
                    ])

# Throughput
with open("throughput.csv", "w", newline="") as th_file:

    th_writer = csv.writer(th_file)
    th_writer.writerow(["timestamp","layer","source","destination","throughput_Mbps"])

    for layer, host, dest_ip in links:

        print(f"Testing throughput {layer}...")

        if layer == "field":
            server_host = "h3"
        elif layer == "system":
            server_host = "h4"

        net.get(server_host).cmd("iperf -s -p 5001 &")
        time.sleep(1)

        output = net.get(host).cmd(f"iperf -c {dest_ip} -t 5")

        for line in output.split("\n"):
            if "Mbits/sec" in line and "sec" in line:
                parts = line.split()
                throughput = parts[-2]
                th_writer.writerow([
                    datetime.datetime.now(),
                    layer,
                    host,
                    dest_ip,
                    throughput
                ])

        net.get(server_host).cmd("kill %iperf")

print("Baseline data collection complete.")
