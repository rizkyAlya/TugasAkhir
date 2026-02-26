import re
import csv
import datetime
import time
import os

links = [
    ("field", "h2", "10.0.2.2", "h3"),   # h2 → h3
    ("system", "h3", "10.0.3.2", "h4"),  # h3 → h4
]

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
log_dir = os.path.join(base_dir, 'logs', 'baseline')

rtt_path = os.path.join(log_dir, "rtt.csv")
loss_path = os.path.join(log_dir, "packet_loss.csv")
th_path = os.path.join(log_dir, "throughput.csv")

def collect_data(net):
    # RTT & Packet Loss
    with open(rtt_path, "w", newline="") as rtt_file, \
        open(loss_path, "w", newline="") as loss_file:

        rtt_writer = csv.writer(rtt_file)
        loss_writer = csv.writer(loss_file)

        rtt_writer.writerow(["timestamp","layer","source","destination","latency_ms"])
        loss_writer.writerow(["timestamp","layer","source","destination","packet_loss_percent"])

        for layer, host, dest_ip, dest_host in links:
            print(f"Testing RTT: {layer}...")

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
                            dest_host,
                            latency.group(1)
                        ])
        
            # Packet loss parsing (summary)
            print(f"Testing Packet Loss: {layer}...")
            for line in output.split("\n"):
                if "packet loss" in line:
                    loss = re.search(r'(\d+)% packet loss', line)
                    if loss:
                        loss_writer.writerow([
                            datetime.datetime.now(),
                            layer,
                            host,
                            dest_host,
                            loss.group(1)
                        ])

    # Throughput
    with open(th_path, "w", newline="") as th_file:

        th_writer = csv.writer(th_file)
        th_writer.writerow(["timestamp","layer","source","destination","throughput_Mbps"])

        for layer, host, dest_ip, dest_host in links:
            print(f"Testing Throughput: {layer}...")

            if layer == "field":
                server_host = "h3"
            elif layer == "system":
                server_host = "h4"

            # Kill all iperf processes
            net.get(server_host).cmd("killall -9 iperf")
        
            net.get(server_host).cmd("iperf -s -p 5001 &")
            time.sleep(1)

            output = net.get(host).cmd(f"iperf -c {dest_ip} -t 5")
            print(f"raw output:", output)
            
            for line in output.split("\n"):
                if "Mbits/sec" in line and "sec" in line:
                    parts = line.split()
                    throughput = parts[-2]
                    th_writer.writerow([
                        datetime.datetime.now(),
                        layer,
                        host,
                        dest_host,
                        throughput
                    ])

            net.get(server_host).cmd("killall -9 iperf")

    print("Baseline data collection complete.")
