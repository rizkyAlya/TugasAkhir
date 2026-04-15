import os
import sys
import time
import argparse
import importlib.util
from datetime import datetime

from mininet.cli import CLI
from mininet.log import setLogLevel

# PATH SETUP
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "script")
APPS_DIR = os.path.join(OUTPUT_DIR, "apps")
HOST_LOG_DIR = os.path.join(BASE_DIR, "logs", "host")
TOPOLOGY_PATH = os.path.join(OUTPUT_DIR, "topology.py")

sys.path.append(OUTPUT_DIR)
sys.path.append(BASE_DIR)

from logger.collector import collect_data

def load_topology_module():
    if not os.path.exists(TOPOLOGY_PATH):
        raise FileNotFoundError(f"Generated topology not found: {TOPOLOGY_PATH}")

    spec = importlib.util.spec_from_file_location("generated_topology", TOPOLOGY_PATH)
    topology_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(topology_mod)
    return topology_mod

def create_network_from_generated_topology():
    """
    Use generated topology output directly (do not rebuild from config).
    Expected API in script/topology.py: create_network()
    """
    topology_mod = load_topology_module()
    if not hasattr(topology_mod, "create_network"):
        raise AttributeError(
            "script/topology.py does not expose create_network(). "
            "Update topology template to provide create_network() that returns a Mininet object."
        )
    return topology_mod.create_network(), topology_mod

def load_generated_attacker_module():
    attacker_path = os.path.join(APPS_DIR, "h5.py")
    if not os.path.exists(attacker_path):
        return None

    spec = importlib.util.spec_from_file_location("generated_h5", attacker_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

# UTIL: START APPS
def start_apps(net):
    print("Starting apps...")
    os.makedirs(HOST_LOG_DIR, exist_ok=True)

    for host in net.hosts:
        name = host.name
        app_path = os.path.join(APPS_DIR, f"{name}.py")

        if os.path.exists(app_path):
            # h5.py is attack helper (function-based), not a long-running host app.
            if name == "h5":
                print(" h5 skipped (attack helper)")
                continue

            log_file = os.path.join(HOST_LOG_DIR, f"{name}.log")
            host.cmd(f"python3 -u {app_path} > {log_file} 2>&1 &")
            print(f" {name} started")

    print("All apps started\n")

def run_mitm(net):
    print("Starting MITM attack...")
    attacker_module = load_generated_attacker_module()

    if attacker_module is None:
        print("Attacker module not found (script/apps/h5.py)")
        return False

    run_mitm_attack = getattr(attacker_module, "run_mitm_attack", None)
    if run_mitm_attack is None:
        print("MITM function not found (script/apps/h5.py::run_mitm_attack)")
        return False

    try:
        run_mitm_attack(net)
        print("MITM running\n")
        return True
    except Exception as e:
        print(f"MITM failed: {e}")
        return False

# UTIL: RUN DOS
def run_dos(net, mode):
    print(f"Starting DoS attack ({mode})...")
    attacker_module = load_generated_attacker_module()

    if attacker_module is None:
        print("Attacker module not found (script/apps/h5.py)")
        return False

    run_dos_attack = getattr(attacker_module, "run_dos_attack", None)
    if run_dos_attack is None:
        print("DoS function not found (script/apps/h5.py::run_dos_attack)")
        return False

    try:
        run_dos_attack(net, mode=mode)
        print(f"DoS {mode} running\n")
        return True
    except Exception as e:
        print(f"DoS failed: {e}")
        return False

# MAIN
def main():
    parser = argparse.ArgumentParser(description="Cyber Range Orchestrator")
    parser.add_argument(
        "--dos",
        action="store_true",
        help="Run DoS scenario after apps started (requires script/apps/h5.py)"
    )
    parser.add_argument(
        "--mitm",
        action="store_true",
        help="Apply MITM route setup (h2 -> h3 via h5) if hosts exist"
    )
    parser.add_argument(
        "--no-cli",
        action="store_true",
        help="Run without Mininet CLI"
    )
    parser.add_argument(
        "--collect-delay",
        type=int,
        default=10,
        help="Seconds to wait before baseline collection in normal mode"
    )

    args = parser.parse_args()
    run_timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_logs_path = os.path.join(BASE_DIR, "logs", run_timestamp)
    os.makedirs(run_logs_path, exist_ok=True)
    print(f"Run logs path: {run_logs_path}")

    print("\n==============================")
    print("MODE: ORCHESTRATOR")
    print(f"MITM: {'ON' if args.mitm else 'OFF'}")
    print(f"DoS : {'ON' if args.dos else 'OFF'}")
    print("==============================\n")

    # START NETWORK FROM GENERATED TOPOLOGY
    print("Starting generated topology...")
    net, topology_mod = create_network_from_generated_topology()
    net.start()
    if hasattr(topology_mod, "post_start_setup"):
        topology_mod.post_start_setup(net)

    print("Waiting for stabilization...")
    time.sleep(3)

    # START APPS
    start_apps(net)

    if args.mitm:
        run_mitm(net)

    if args.dos:
        # Always run both scenarios in one DoS run.
        for dos_mode in ("light", "heavy"):
            ok = run_dos(net, dos_mode)
            if ok:
                print(f"Collecting DoS ({dos_mode}) metrics...")
                collect_data(net, mode=dos_mode, logs_path=run_logs_path)
                print(f"DoS ({dos_mode}) collection complete.\n")

    # In normal mode, wait a bit then collect baseline logs.
    if not args.mitm and not args.dos:
        delay = max(0, args.collect_delay)
        print(f"Normal mode detected: collecting baseline in {delay}s...")
        time.sleep(delay)
        collect_data(net, mode="baseline", logs_path=run_logs_path)
        print("Baseline collection complete.\n")

    # In MITM mode (without DoS), still collect baseline metrics in per-run folder.
    if args.mitm and not args.dos:
        delay = max(0, args.collect_delay)
        print(f"MITM mode detected: collecting baseline in {delay}s...")
        time.sleep(delay)
        collect_data(net, mode="baseline", logs_path=run_logs_path)
        print("MITM baseline collection complete.\n")

    print("System ready\n")

    # CLI
    if not args.no_cli:
        CLI(net)

    # STOP NETWORK
    print("Stopping network...")
    net.stop()

# ENTRY POINT
if __name__ == "__main__":
    setLogLevel("info")
    main()