import re
import csv
import datetime

links = [
    ("field", "h1", "10.0.1.3"),
    ("gateway", "h2", "10.0.2.2"),
    ("system", "h3", "10.0.3.2"),
]

# RTT and Packet Loss
with open("rtt.csv", "w", newline="") as rtt_file, \
     open("packet_loss.csv", "w", newline="") as loss_file:

    rtt_writer = csv.writer(rtt_file)
    loss_writer = csv.writer(loss_file)

    rtt_writer.writerow(["timestamp","layer","source","destination","latency_ms"])
    loss_writer.writerow(["timestamp","layer","source","destination","packet_loss_percent"])

    for layer, host, dest_ip in links:
        print(f"Testing {layer} layer...")

        output = net.get(host).cmd(f"ping -c 20 {dest_ip}")

        # RTT parsing
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

        # Packet loss parsing
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

        # start iperf server
        server_host = None
        if layer == "field":
            server_host = "h2"
        elif layer == "gateway":
            server_host = "h3"
        elif layer == "system":
            server_host = "h4"

        net.get(server_host).cmd("iperf -s -p 5001 &")

        output = net.get(host).cmd(f"iperf -c {dest_ip} -t 5")

        for line in output.split("\n"):
            if "Mbits/sec" in line:
                parts = line.split()
                throughput = parts[-2]
                th_writer.writerow([
                    datetime.datetime.now(),
                    layer,
                    host,
                    dest_ip,
                    throughput
                ])

print("Baseline data collection complete.")
