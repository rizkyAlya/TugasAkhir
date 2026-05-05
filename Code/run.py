import os
import sys
import time
import argparse
import importlib.util
import json
import shlex
import yaml
from datetime import datetime

from mininet.cli import CLI
from mininet.log import setLogLevel

# PATH SETUP
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "script")
APPS_DIR = os.path.join(OUTPUT_DIR, "apps")
HOST_LOG_DIR = os.path.join(BASE_DIR, "logs", "host")
TOPOLOGY_PATH = os.path.join(OUTPUT_DIR, "topology.py")
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
ATTACK_ACTIVE_FLAG = "/tmp/mitm_attack_active"
MITM_RUN_ID_FILE = "/tmp/mitm_run_id"

sys.path.append(OUTPUT_DIR)
sys.path.append(BASE_DIR)

from logger.collector import collect_data
from logger.mitm_trace_logger import RUN_ROOT_HOST_FILE

def reset_attack_flags():
    for flag_path in (ATTACK_ACTIVE_FLAG, MITM_RUN_ID_FILE):
        try:
            if os.path.exists(flag_path):
                os.remove(flag_path)
        except Exception as e:
            print(f"Warning: failed to remove {flag_path}: {e}")


def clear_mininet_mitm_trace_state(net):
    """
    Hapus marker MITM dan pointer run root di /tmp setiap host Mininet.
    """
    extras = f"{ATTACK_ACTIVE_FLAG} {MITM_RUN_ID_FILE} {RUN_ROOT_HOST_FILE}"
    for host in net.hosts:
        try:
            host.cmd(f"rm -f {extras} 2>/dev/null || true")
        except Exception:
            pass


def publish_run_root_on_hosts(net, run_root_abs: str):
    """Tulis path absolut logs/runs/<run_id>/ di setiap host agar trace pakai layout sama."""
    path = os.path.abspath(run_root_abs)
    snippet = f"open({repr(RUN_ROOT_HOST_FILE)},'w',encoding='utf-8').write({repr(path)})"
    arg = shlex.quote(snippet)
    for host in net.hosts:
        try:
            host.cmd(f"python3 -c {arg}")
        except Exception:
            pass


def prime_mitm_phase_on_hosts(net):
    """
    Untuk mode --mitm, aktifkan marker serangan sebelum app start agar
    iterasi awal trace langsung masuk bucket mitm.
    """
    for host in net.hosts:
        try:
            host.cmd(f"touch {ATTACK_ACTIVE_FLAG}")
        except Exception:
            pass


def load_app_map():
    app_map_path = os.path.join(APPS_DIR, "app_map.json")
    if not os.path.exists(app_map_path):
        return {}
    try:
        with open(app_map_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_start_order_from_config(config_path=CONFIG_PATH):
    """
    Ambil urutan startup host dari config berdasarkan role:
    field -> gateway -> rtu -> pandapower.
    """
    role_order = ("field", "gateway", "rtu", "pandapower")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        zones = cfg.get("topology", {}).get("zones", {})
        hosts = []
        for zone in zones.values():
            hosts.extend(zone.get("hosts", []))
        by_role = {role: [] for role in role_order}
        for h in hosts:
            name = h.get("name")
            role = h.get("role")
            if name and role in by_role:
                by_role[role].append(name)
        ordered = []
        for role in role_order:
            ordered.extend(by_role[role])
        return ordered
    except Exception:
        return []


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
    app_map = load_app_map()
    attacker_filename_candidates = []
    if "h5" in app_map:
        attacker_filename_candidates.append(app_map["h5"])
    attacker_filename_candidates.extend(["h5.py", "attacker.py", "attacker_1.py"])

    attacker_path = None
    for filename in attacker_filename_candidates:
        path = os.path.join(APPS_DIR, filename)
        if os.path.exists(path):
            attacker_path = path
            break
    if attacker_path is None:
        return None

    spec = importlib.util.spec_from_file_location("generated_h5", attacker_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

# UTIL: START APPS
def start_apps(net, host_log_dir):
    print("Starting apps...")
    os.makedirs(host_log_dir, exist_ok=True)
    app_map = load_app_map()

    def _start_host_app(host):
        name = host.name
        # h5.py is attack helper (function-based), not a long-running host app.
        if name == "h5":
            print(" h5 skipped (attack helper)")
            return

        app_filename = app_map.get(name, f"{name}.py")
        app_path = os.path.join(APPS_DIR, app_filename)
        if not os.path.exists(app_path):
            return

        log_file = os.path.join(host_log_dir, f"{name}.log")
        host.cmd(f"python3 -u {app_path} > {log_file} 2>&1 &")
        print(f" {name} started ({app_filename})")

    # Priority order mengikuti config role: field -> gateway -> rtu -> pandapower.
    order = load_start_order_from_config()
    started = set()

    for name in order:
        if name in started:
            continue
        try:
            host = net.get(name)
        except KeyError:
            continue
        _start_host_app(host)
        started.add(name)
        time.sleep(0.5)

    # Start remaining host apps (stable deterministic order).
    for host in sorted(net.hosts, key=lambda h: h.name):
        if host.name in started:
            continue
        _start_host_app(host)

    print("All apps started\n")

def run_mitm(net, host_log_dir):
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
        run_mitm_attack(net, host_log_dir=host_log_dir)
        print("MITM running\n")
        return True
    except Exception as e:
        print(f"MITM failed: {e}")
        return False

# UTIL: RUN DOS
def run_dos(net, mode, host_log_dir):
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
        run_dos_attack(net, mode=mode, host_log_dir=host_log_dir)
        print(f"DoS {mode} running\n")
        return True
    except Exception as e:
        print(f"DoS failed: {e}")
        return False

# MAIN
def main():
    parser = argparse.ArgumentParser(description="Cyber Range Orchestrator")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Collect baseline metrics after apps started"
    )
    parser.add_argument(
        "--dos",
        action="store_true",
        help="Run DoS scenario after apps started (requires script/apps/h5.py)"
    )
    parser.add_argument(
        "--mitm",
        action="store_true",
        help="MITM: h2 route control via h5 Field; DNAT Modbus to proxy; I diubah in-path (mitm_modbus_proxy)"
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
        help="Seconds to wait before baseline collection (when enabled)"
    )

    args = parser.parse_args()
    # Baseline collection hanya saat diminta eksplisit.
    should_collect_baseline = bool(args.baseline)
    # Folder run tetap dibuat untuk skenario apa pun agar output rapi per eksekusi.
    should_create_run_folder = bool(args.baseline or args.mitm or args.dos)
    run_logs_path = None
    run_id_str = None
    if should_create_run_folder:
        run_id_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        run_logs_path = os.path.join(BASE_DIR, "logs", "runs", run_id_str)
        os.makedirs(run_logs_path, exist_ok=True)
        for sub in (
            os.path.join("network"),
            os.path.join("trace", "baseline"),
            os.path.join("trace", "mitm"),
        ):
            os.makedirs(os.path.join(run_logs_path, sub), exist_ok=True)
        meta_path = os.path.join(run_logs_path, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "run_id": run_id_str,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "modes": {
                        "baseline": bool(args.baseline),
                        "mitm": bool(args.mitm),
                        "dos": bool(args.dos),
                    },
                    "collect_delay_s": args.collect_delay if args.baseline else None,
                },
                f,
                indent=2,
            )
        print(f"Run logs path: {run_logs_path}")

    print("\n==============================")
    print("MODE: ORCHESTRATOR")
    print(f"Baseline: {'ON' if should_collect_baseline else 'OFF'}")
    print(f"MITM: {'ON' if args.mitm else 'OFF'}")
    print(f"DoS : {'ON' if args.dos else 'OFF'}")
    print("==============================\n")

    # Ensure phase markers do not leak from previous runs.
    reset_attack_flags()

    host_log_run_key = run_id_str or datetime.now().strftime("%Y-%m-%d_%H%M%S")
    host_log_dir = os.path.join(HOST_LOG_DIR, host_log_run_key)
    print(f"Host logs path: {host_log_dir}")

    # START NETWORK FROM GENERATED TOPOLOGY
    print("Starting generated topology...")
    net, topology_mod = create_network_from_generated_topology()
    net.start()
    if hasattr(topology_mod, "post_start_setup"):
        topology_mod.post_start_setup(net)

    print("Waiting for stabilization...")
    time.sleep(3)

    clear_mininet_mitm_trace_state(net)

    if run_logs_path:
        publish_run_root_on_hosts(net, run_logs_path)
    if args.mitm:
        prime_mitm_phase_on_hosts(net)

    # START APPS
    start_apps(net, host_log_dir)

    # Collect baseline only when enabled (explicitly or as part of a scenario).
    if should_collect_baseline:
        delay = max(0, args.collect_delay)
        print(f"Collecting baseline in {delay}s...")
        time.sleep(delay)
        collect_data(net, mode="baseline", logs_path=run_logs_path)
        print("Baseline collection complete.\n")

    if args.mitm:
        # Topologi: attacker foothold di Control dulu; eskalasi ke Field saat skenario MITM.
        if hasattr(topology_mod, "escalate_attacker_to_field"):
            topology_mod.escalate_attacker_to_field(net)
            time.sleep(1)
        run_mitm(net, host_log_dir)
        print("Collecting MITM metrics...")
        collect_data(net, mode="mitm", logs_path=run_logs_path)
        print("MITM collection complete.\n")

    if args.dos:
        # Always run both scenarios in one DoS run.
        for dos_mode in ("light", "heavy"):
            ok = run_dos(net, dos_mode, host_log_dir)
            if ok:
                print(f"Collecting DoS ({dos_mode}) metrics...")
                collect_data(net, mode=dos_mode, logs_path=run_logs_path)
                print(f"DoS ({dos_mode}) collection complete.\n")

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