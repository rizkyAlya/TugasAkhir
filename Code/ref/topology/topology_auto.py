"""
Automated scalable CPS topology for Mininet.
Builds a 3-zone topology: Field (scalable), Control (1 host), IT (2 hosts).
Config via user input or YAML/JSON file. Each topology run is logged with a timestamp.
"""

from mininet.net import Mininet
from mininet.node import Controller, OVSSwitch, Node
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel

import time
import os
import sys
import argparse
import json
from datetime import datetime

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(base_dir)
from logger.collector import collect_data
from apps.h5_attacker import run_dos_attack

try:
    import yaml
except ImportError:
    yaml = None

# Subnet base for each zone: 10.0.{zone}.0/24
FIELD_SUBNET = (10, 0, 1)
CONTROL_SUBNET = (10, 0, 2)
IT_SUBNET = (10, 0, 3)

def load_config_from_file(path):
    """
    Load topology config from a YAML or JSON file.
    Only field (number of hosts in Field zone) and bandwidth are configurable.
    Control zone is fixed at 1 host, IT zone at 2 hosts.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        if yaml is None:
            raise ImportError("PyYAML is required for .yaml config. Install with: pip install pyyaml")
        data = yaml.safe_load(raw)
    elif ext == ".json":
        data = json.loads(raw)
    else:
        raise ValueError(f"Unsupported config format: {ext}. Use .yaml, .yml, or .json")

    if data is None:
        data = {}

    # Allow nested "topology" key or flat keys
    if "topology" in data:
        data = data["topology"]

    config = {
        "n_field": int(data.get("field", data.get("n_field", 2))),
        "n_control": 1,
        "n_it": 2,
        "bandwidth": int(data.get("bandwidth", 5)),
    }
    config["n_field"] = max(1, config["n_field"])
    config["bandwidth"] = max(1, config["bandwidth"])
    return config

def write_topology_log(config, config_path=None, timestamp_str=None):
    """
    Write a log entry for this topology creation under logs/topology/.
    Creates logs/topology/topology_<timestamp>.log with timestamp and config.
    """
    if timestamp_str is None:
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_dir = os.path.join(base_dir, "logs", "topology")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"topology_{timestamp_str}.log")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"topology_created_at={timestamp_str}\n")
        f.write(f"iso_datetime={datetime.now().isoformat()}\n")
        if config_path:
            f.write(f"config_file={os.path.abspath(config_path)}\n")
        f.write(f"n_field={config['n_field']}\n")
        f.write(f"n_control={config['n_control']}\n")
        f.write(f"n_it={config['n_it']}\n")
        f.write(f"bandwidth={config['bandwidth']}\n")
    return log_file

def add_router(net, name):
    r = net.addHost(name, cls=Node)
    r.cmd('sysctl -w net.ipv4.ip_forward=1')
    return r

def ip_for_zone(zone_base, host_index):
    """Host index 0 -> .2, 1 -> .3, etc. (router uses .1)."""
    return f"{zone_base[0]}.{zone_base[1]}.{zone_base[2]}.{host_index + 2}/24"

def get_user_input():
    """Get topology parameters via interactive prompts. Only Field zone is scalable."""
    print("\n--- Scalable CPS Topology Builder ---\n")
    print("Control zone: 1 host (fixed). IT zone: 2 hosts (fixed).\n")
    defaults = {"field": 2, "bandwidth": 5}

    try:
        n_field = input(f"Number of hosts in Field zone [{defaults['field']}]: ").strip() or defaults["field"]
        n_field = int(n_field)
        bw = input(f"Link bandwidth (Mbps) [{defaults['bandwidth']}]: ").strip() or defaults["bandwidth"]
        bw = int(bw)
    except ValueError as e:
        print(f"Invalid input, using defaults. Error: {e}")
        n_field, bw = defaults["field"], defaults["bandwidth"]

    return {
        "n_field": max(1, n_field),
        "n_control": 1,
        "n_it": 2,
        "bandwidth": max(1, bw),
    }


def build_topology(config):
    """
    Build Mininet topology from config.
    Field zone: n_field hosts (scalable). Control: 1 host. IT: 2 hosts.
    """
    n_field = config["n_field"]
    n_control = 1
    n_it = 2
    bw = config["bandwidth"]

    net = Mininet(controller=Controller, link=TCLink, switch=OVSSwitch)

    print("Adding controller")
    net.addController("c0")

    # Host naming: h1, h2, ... in order: field first, then control, then IT
    host_index = 1
    field_hosts = []
    control_hosts = []
    it_hosts = []

    print("Adding hosts")
    for i in range(n_field):
        name = f"h{host_index}"
        ip = ip_for_zone(FIELD_SUBNET, i)
        net.addHost(name, ip=ip)
        field_hosts.append(name)
        host_index += 1
    for i in range(n_control):
        name = f"h{host_index}"
        ip = ip_for_zone(CONTROL_SUBNET, i)
        net.addHost(name, ip=ip)
        control_hosts.append(name)
        host_index += 1
    for i in range(n_it):
        name = f"h{host_index}"
        ip = ip_for_zone(IT_SUBNET, i)
        net.addHost(name, ip=ip)
        it_hosts.append(name)
        host_index += 1

    print("Adding switches")
    switch_field = net.addSwitch("s1")
    switch_control = net.addSwitch("s2")
    switch_it = net.addSwitch("s3")
    core_switch = net.addSwitch("s4")

    print("Adding router")
    r0 = add_router(net, "r0")

    print("Creating links")
    for h in field_hosts:
        net.addLink(h, switch_field, bw=bw)
    net.addLink(switch_field, core_switch, bw=bw)
    net.addLink(r0, switch_field, bw=bw)

    for h in control_hosts:
        net.addLink(h, switch_control, bw=bw)
    net.addLink(switch_control, core_switch, bw=bw)
    net.addLink(r0, switch_control, bw=bw)

    for h in it_hosts:
        net.addLink(h, switch_it, bw=bw)
    net.addLink(switch_it, core_switch, bw=bw)
    net.addLink(r0, switch_it, bw=bw)

    print("Starting network")
    net.start()

    print("Configuring router interfaces")
    r0.cmd("ifconfig r0-eth0 10.0.1.1/24 up")
    r0.cmd("ifconfig r0-eth1 10.0.2.1/24 up")
    r0.cmd("ifconfig r0-eth2 10.0.3.1/24 up")

    print("Setting default routes on hosts")
    for h in field_hosts:
        net.get(h).cmd("ip route add default via 10.0.1.1")
    for h in control_hosts:
        net.get(h).cmd("ip route add default via 10.0.2.1")
    for h in it_hosts:
        net.get(h).cmd("ip route add default via 10.0.3.1")

    host_names_by_zone = {
        "field": field_hosts,
        "control": control_hosts,
        "it": it_hosts,
    }
    return net, host_names_by_zone, config


def start_apps(net, host_names_by_zone, config):
    """
    Start host applications (field device, RTU, gateway, twin, attacker).
    Control=1 and IT=2 are fixed; need at least 2 field hosts (h1=field, h2=RTU).
    """
    field = host_names_by_zone["field"]
    control = host_names_by_zone["control"]
    it = host_names_by_zone["it"]

    if len(field) < 2:
        print("Skipping apps: need at least 2 field hosts for field device and RTU.")
        return

    h1 = net.get(field[0])
    h2 = net.get(field[1])
    h3 = net.get(control[0])
    h4 = net.get(it[0])
    h5 = net.get(it[1])

    log_dir = os.path.join(base_dir, "logs", "host")
    os.makedirs(log_dir, exist_ok=True)

    print("Starting host applications...")
    h1.cmd(f"python3 -u {base_dir}/apps/h1_field.py > {log_dir}/h1.log 2>&1 &")
    h3.cmd(f"python3 -u {base_dir}/apps/h3_gateway.py > {log_dir}/h3.log 2>&1 &")
    time.sleep(2)
    h2.cmd(f"python3 -u {base_dir}/apps/h2_rtu.py > {log_dir}/h2.log 2>&1 &")
    h4.cmd(f"python3 -u {base_dir}/apps/h4_twin.py > {log_dir}/h4.log 2>&1 &")
    print("All applications started.")


def run_experiment(net, host_names_by_zone, config, logs_path=None):
    """Run baseline and DoS data collection. Requires at least 2 field hosts.
    Saves under logs/[timestamp]/baseline and logs/[timestamp]/dos/ when logs_path is set."""
    field = host_names_by_zone["field"]
    control = host_names_by_zone["control"]
    it = host_names_by_zone["it"]

    if len(field) < 2:
        print("Skipping experiment: need at least 2 field hosts.")
        return

    time.sleep(60)
    collect_data(net, mode="baseline", logs_path=logs_path)

    print("\nStarting DoS: mode light")
    run_dos_attack(net, mode="light")
    time.sleep(2)
    collect_data(net, mode="light", logs_path=logs_path)

    print("\nStarting DoS: mode heavy")
    run_dos_attack(net, mode="heavy")
    time.sleep(2)
    collect_data(net, mode="heavy", logs_path=logs_path)


def main():
    parser = argparse.ArgumentParser(
        description="Build a scalable CPS topology (Field / Control / IT zones) from user input or config file."
    )
    parser.add_argument(
        "--config", "-C", type=str, default=None, metavar="FILE",
        help="Load topology from YAML or JSON file (e.g. topology.yaml)",
    )
    parser.add_argument(
        "--field", "-f", type=int, default=None,
        help="Number of hosts in Field zone (scalable; ignored if --config is set)",
    )
    parser.add_argument(
        "--bandwidth", "-b", type=int, default=None,
        help="Link bandwidth in Mbps",
    )
    parser.add_argument(
        "--no-apps", action="store_true",
        help="Do not start host apps or run experiment (topology only)",
    )
    parser.add_argument(
        "--no-cli", action="store_true",
        help="Do not open Mininet CLI after startup (useful with --no-apps for quick tests)",
    )
    parser.add_argument(
        "--interactive", action="store_true",
        help="Always prompt for parameters (overrides CLI args)",
    )
    args = parser.parse_args()

    # Resolve config: file > interactive > CLI args
    config_path = args.config
    if config_path:
        try:
            config = load_config_from_file(config_path)
            print(f"Loaded config from: {config_path}")
        except (FileNotFoundError, ValueError, ImportError) as e:
            print(f"Error loading config: {e}")
            sys.exit(1)
    elif args.interactive or (args.field is None and args.bandwidth is None):
        config = get_user_input()
    else:
        config = {
            "n_field": args.field if args.field is not None else 2,
            "n_control": 1,
            "n_it": 2,
            "bandwidth": args.bandwidth if args.bandwidth is not None else 5,
        }
        config["n_field"] = max(1, config["n_field"])
        config["bandwidth"] = max(1, config["bandwidth"])

    # Timestamp and log this topology creation
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = write_topology_log(config, config_path=config_path, timestamp_str=timestamp)
    print(f"\nTopology timestamp: {timestamp}")
    print(f"Topology log: {log_file}")

    print(f"\nTopology: Field={config['n_field']} (scalable), Control=1, IT=2, BW={config['bandwidth']} Mbps")

    # Logs for this run go under logs/[timestamp]/(baseline or dos)
    logs_path = None
    if not args.no_apps:
        logs_path = os.path.join(base_dir, "logs", timestamp)
        os.makedirs(os.path.join(logs_path, "baseline"), exist_ok=True)
        os.makedirs(os.path.join(logs_path, "dos", "light"), exist_ok=True)
        os.makedirs(os.path.join(logs_path, "dos", "heavy"), exist_ok=True)
        print(f"Run results will be saved under: logs/{timestamp}/")

    net, host_names_by_zone, _ = build_topology(config)

    print("\nWaiting for network stabilization...")
    time.sleep(5)
    print("Network ready.")

    if not args.no_apps:
       start_apps(net, host_names_by_zone, config)
       # run_experiment(net, host_names_by_zone, config, logs_path=logs_path)

    if not args.no_cli:
        CLI(net)

    print("Stopping network")
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    main()
