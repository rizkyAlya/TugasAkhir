import os
import sys
import time
import argparse

from mininet.cli import CLI

# PATH SETUP
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "script")
APPS_DIR = os.path.join(OUTPUT_DIR, "apps")

sys.path.append(OUTPUT_DIR)

# import topology hasil generator
from topology import create_network

# optional DoS (kalau ada)
try:
    from apps.h5_attacker import run_dos_attack
except:
    run_dos_attack = None

# UTIL: START APPS
def start_apps(net):
    print("Starting apps...")

    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    for host in net.hosts:
        name = host.name
        app_path = os.path.join(APPS_DIR, f"{name}.py")

        if os.path.exists(app_path):
            log_file = os.path.join(log_dir, f"{name}.log")
            host.cmd(f"python3 -u {app_path} > {log_file} 2>&1 &")
            print(f" {name} started")

    print("All apps started\n")

# UTIL: SETUP MITM
def setup_mitm(net):
    print("Setting up MITM...")

    try:
        h2 = net.get("h2")  # RTU
        h3 = net.get("h3")  # gateway
        h5 = net.get("h5")  # attacker

        # enable forwarding
        h5.cmd("sysctl -w net.ipv4.ip_forward=1")

        # NOTE: sesuaikan IP kalau berubah dari generator
        h3_ip = h3.IP()
        h5_ip = h5.IP()

        # redirect traffic dari h2 ke h3 lewat h5
        h2.cmd(f"ip route replace {h3_ip} via {h5_ip}")

        print(f" h2 → {h3_ip} via {h5_ip}")
        print("MITM configured\n")

    except Exception as e:
        print(f"MITM setup failed: {e}")

# UTIL: RUN DOS
def run_dos(net):
    print("Starting DoS attack...")

    if run_dos_attack is None:
        print("DoS function not found (apps/h5_attacker.py)")
        return

    try:
        run_dos_attack(net, mode="light")
        print("DoS running\n")
    except Exception as e:
        print(f"DoS failed: {e}")

# MAIN
def main():
    parser = argparse.ArgumentParser(description="Cyber Range Orchestrator")
    parser.add_argument(
        "--mode",
        choices=["normal", "dos", "mitm"],
        default="normal",
        help="Run mode"
    )
    parser.add_argument(
        "--no-cli",
        action="store_true",
        help="Run without Mininet CLI"
    )

    args = parser.parse_args()

    print("\n==============================")
    print(f"MODE: {args.mode.upper()}")
    print("==============================\n")

    # START NETWORK
    print("Starting network...")
    net = create_network()
    net.start()

    print("Waiting for stabilization...")
    time.sleep(3)

    # START APPS
    start_apps(net)

    # MODE CONTROL
    if args.mode == "dos":
        run_dos(net)

    elif args.mode == "mitm":
        setup_mitm(net)

    else:
        print("Running in NORMAL mode\n")

    print("System ready\n")

    # CLI
    if not args.no_cli:
        CLI(net)

    # STOP NETWORK
    print("🛑 Stopping network...")
    net.stop()

# ENTRY POINT
if __name__ == "__main__":
    main()