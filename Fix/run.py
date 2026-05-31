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
from logger.pcap_collector import (
    pcap_session_dir,
    start_trace_iteration_captures,
    stop_any_running_captures,
    stop_trace_iteration_captures,
    write_pcap_manifest,
)
from logger.mitm_trace_logger import (
    MITM_PROXY_SNAPSHOT_FILE,
    RUN_ROOT_HOST_FILE,
    TRACE_COLLECT_RUN_FILE,
    MEASURE_PHASE_FILE,
    TRACE_ENABLED_FILE,
    publish_collect_run_on_hosts,
    publish_measure_phase_on_hosts,
    publish_trace_enabled_on_hosts,
    clear_measure_session_markers_on_hosts,
)

# Jeda fase normal (tanpa pengumpulan baseline) sebelum serangan MITM.
NORMAL_PHASE_PRE_ATTACK_S = 5

# Trace sebelum collect_data jaringan (baseline & MITM, durasi sama agar comparable).
# Satu tick kolom "waktu" ≈ satu putaran loop gateway — selaras generator/templates/gateway.j2 (time.sleep akhir loop).
TRACE_BEFORE_NETWORK_NUM_ITERATIONS = 3
TRACE_BEFORE_NETWORK_MIN_WAKTU_PER_ITERATION = 35
TRACE_BEFORE_NETWORK_GATEWAY_CYCLE_S = 1


def trace_phase_before_network_collect(
    net,
    log_label: str,
    *,
    pcap_dir=None,
    pcap_phase: str = None,
    include_mitm_eth1: bool = False,
    pcap_manifest: list = None,
) -> None:
    """
    Set iterasi_ke 1..N di host, tunggu agar gateway mengisi trace.
    Jika pcap_dir diisi: tcpdump per iterasi (selaras iterasi_ke trace CSV).
    """
    wait_s = TRACE_BEFORE_NETWORK_MIN_WAKTU_PER_ITERATION * TRACE_BEFORE_NETWORK_GATEWAY_CYCLE_S
    n = TRACE_BEFORE_NETWORK_NUM_ITERATIONS
    phase_key = (pcap_phase or log_label).lower()

    for i in range(1, n + 1):
        publish_collect_run_on_hosts(net, i)
        iter_entries = []
        if pcap_dir:
            iter_entries = start_trace_iteration_captures(
                net,
                pcap_dir,
                phase_key,
                i,
                include_mitm_eth1=include_mitm_eth1,
            )
        print(
            f"[orchestrator] {log_label} trace: iterasi_ke={i}/{n}, "
            f"menunggu {wait_s}s (target >= {TRACE_BEFORE_NETWORK_MIN_WAKTU_PER_ITERATION} waktu/iterasi)..."
        )
        time.sleep(wait_s)
        if pcap_dir and iter_entries:
            saved = stop_trace_iteration_captures(net, iter_entries)
            if pcap_manifest is not None:
                pcap_manifest.extend(saved)
                write_pcap_manifest(
                    pcap_dir,
                    pcap_manifest,
                    trace_iterations=n,
                    aligned_with="trace.csv iterasi_ke",
                )


def dos_phase_with_pcap(
    net,
    dos_mode: str,
    *,
    pcap_dir=None,
    pcap_manifest: list = None,
    measure_fn,
) -> None:
    """
    Satu capture iter01 per mode (dos_light / dos_heavy) selama serangan + pengukuran.
    measure_fn: callable tanpa argumen (run_dos, collect_data, dll.).
    """
    phase_key = f"dos_{dos_mode}"
    iter_entries = []
    if pcap_dir:
        iter_entries = start_trace_iteration_captures(
            net,
            pcap_dir,
            phase_key,
            1,
            include_mitm_eth1=False,
        )
        print(f"[orchestrator] PCAP {phase_key} iter01 started -> {pcap_dir}")
    try:
        measure_fn()
    finally:
        if pcap_dir and iter_entries:
            saved = stop_trace_iteration_captures(net, iter_entries)
            if pcap_manifest is not None:
                pcap_manifest.extend(saved)
                write_pcap_manifest(
                    pcap_dir,
                    pcap_manifest,
                    dos_modes=["light", "heavy"],
                    aligned_with="DoS attack + network metrics per mode",
                )


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
    extras = (
        f"{ATTACK_ACTIVE_FLAG} {MITM_RUN_ID_FILE} {RUN_ROOT_HOST_FILE} "
        f"{MITM_PROXY_SNAPSHOT_FILE} {TRACE_COLLECT_RUN_FILE} "
        f"{MEASURE_PHASE_FILE} {TRACE_ENABLED_FILE}"
    )
    for host in net.hosts:
        try:
            host.cmd(f"rm -f {extras} 2>/dev/null || true")
        except Exception:
            pass


def publish_run_root_on_hosts(net, run_root_abs: str):
    """Tulis path absolut root sesi logs/<baseline|mitm|dos>/<run_id>/ di setiap host untuk trace CSV."""
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


def write_session_meta(
    session_root: str,
    run_id_str: str,
    args,
    pcap_dir=None,
) -> None:
    os.makedirs(session_root, exist_ok=True)
    meta_path = os.path.join(session_root, "meta.json")
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
                "pcap_dir": pcap_dir,
            },
            f,
            indent=2,
        )


def initial_trace_session_root(path_baseline, path_mitm, path_dos, args):
    """Folder RUN_ROOT awal: mitm > baseline > dos (output trace sesi utama)."""
    if args.mitm and path_mitm:
        return path_mitm
    if args.baseline and path_baseline:
        return path_baseline
    if args.dos and path_dos:
        return path_dos
    return None


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
    field -> gateway -> rtu -> dt.
    """
    role_order = ("field", "gateway", "rtu", "dt")
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

    # Priority order mengikuti config role: field -> gateway -> rtu -> dt.
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
        time.sleep(2)

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


def stop_dos_hping_on_net(net):
    """Hentikan hping3 di host attacker (topologi ini: h5)."""
    try:
        h = net.get("h5")
        if h:
            h.cmd("killall hping3 >/dev/null 2>&1 || true")
    except Exception:
        pass


def clear_mitm_attack_flag_on_hosts(net):
    """Hapus marker serangan MITM di semua host (setelah pengumpulan fase attack)."""
    for host in net.hosts:
        try:
            host.cmd(f"rm -f {ATTACK_ACTIVE_FLAG} 2>/dev/null || true")
        except Exception:
            pass


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
        default=5,
        help="Seconds to wait before baseline collection (when enabled)"
    )
    parser.add_argument(
        "--no-pcap",
        action="store_true",
        help="Disable tcpdump capture on h1–h5 and r0",
    )

    args = parser.parse_args()
    # Baseline collection hanya saat diminta eksplisit.
    should_collect_baseline = bool(args.baseline)
    # logs/<baseline|mitm|dos>/<timestamp>/ per skenario (satu run_id untuk korelasi antar mode).
    should_create_run_folder = bool(args.baseline or args.mitm or args.dos)
    run_id_str = None
    path_baseline = path_mitm = path_dos = None
    pcap_dir = None
    if should_create_run_folder:
        run_id_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        if not args.no_pcap:
            pcap_dir = pcap_session_dir(BASE_DIR, run_id_str)
        if args.baseline:
            path_baseline = os.path.join(BASE_DIR, "logs", "baseline", run_id_str)
            write_session_meta(path_baseline, run_id_str, args, pcap_dir)
        if args.mitm:
            path_mitm = os.path.join(BASE_DIR, "logs", "mitm", run_id_str)
            write_session_meta(path_mitm, run_id_str, args, pcap_dir)
        if args.dos:
            path_dos = os.path.join(BASE_DIR, "logs", "dos", run_id_str)
            write_session_meta(path_dos, run_id_str, args, pcap_dir)
        log_lines = []
        if path_baseline:
            log_lines.append(f"baseline -> {path_baseline}")
        if path_mitm:
            log_lines.append(f"mitm -> {path_mitm}")
        if path_dos:
            log_lines.append(f"dos -> {path_dos}")
        print("Run logs paths:\n  " + "\n  ".join(log_lines))

    print("\n==============================")
    print("MODE: ORCHESTRATOR")
    print(f"Baseline: {'ON' if should_collect_baseline else 'OFF'}")
    print(f"MITM: {'ON' if args.mitm else 'OFF'}")
    print(f"DoS : {'ON' if args.dos else 'OFF'}")
    print(
        f"PCAP: {'OFF (--no-pcap)' if args.no_pcap else ('ON -> ' + pcap_dir if pcap_dir else 'OFF (no scenario flags)')}"
    )
    print("==============================\n")

    # Ensure phase markers do not leak from previous runs.
    reset_attack_flags()

    host_log_run_key = run_id_str or datetime.now().strftime("%Y-%m-%d_%H%M%S")
    host_log_dir = os.path.join(HOST_LOG_DIR, host_log_run_key)
    print(f"Host logs path: {host_log_dir}")

    # START NETWORK FROM GENERATED TOPOLOGY
    print("Starting generated topology...")
    net = None
    pcap_manifest = None
    try:
        net, topology_mod = create_network_from_generated_topology()
        net.start()
        if hasattr(topology_mod, "post_start_setup"):
            topology_mod.post_start_setup(net)

        print("Waiting for stabilization...")
        time.sleep(3)

        clear_mininet_mitm_trace_state(net)

        trace_root0 = initial_trace_session_root(path_baseline, path_mitm, path_dos, args)
        if trace_root0:
            publish_run_root_on_hosts(net, trace_root0)

        # START APPS
        start_apps(net, host_log_dir)

        pcap_manifest = [] if pcap_dir else None
        if pcap_dir:
            print(
                f"PCAP per iterasi trace (N={TRACE_BEFORE_NETWORK_NUM_ITERATIONS}) -> {pcap_dir}"
            )

        # Sesi pengukuran: iterasi_ke + fase host selaras trace / network (collector tidak menghapus marker di tengah).
        if should_create_run_folder:
            publish_trace_enabled_on_hosts(net, True)
            publish_measure_phase_on_hosts(net, "normal")
            publish_collect_run_on_hosts(net, 1)

        # Collect baseline only when enabled (explicitly or as part of a scenario).
        if should_collect_baseline:
            delay = max(0, args.collect_delay)
            print(f"Collecting baseline in {delay}s...")
            time.sleep(delay)
            print("Baseline: fase pengukuran trace (sebelum network)...")
            trace_phase_before_network_collect(
                net,
                "baseline",
                pcap_dir=pcap_dir,
                pcap_phase="baseline",
                pcap_manifest=pcap_manifest,
            )
            collect_data(
                net,
                mode="baseline",
                logs_path=path_baseline,
                measure_phase="normal",
            )
            print("Baseline collection complete.\n")

        if args.mitm:
            if not should_collect_baseline:
                print(f"Normal phase (pre-attack, {NORMAL_PHASE_PRE_ATTACK_S}s)...")
                time.sleep(NORMAL_PHASE_PRE_ATTACK_S)
            publish_measure_phase_on_hosts(net, "attack")
            prime_mitm_phase_on_hosts(net)
            # Topologi: attacker foothold di Control dulu; eskalasi ke Field saat skenario MITM.
            if hasattr(topology_mod, "escalate_attacker_to_field"):
                topology_mod.escalate_attacker_to_field(net)
                time.sleep(1)
            run_mitm(net, host_log_dir)
            print("MITM: fase pengukuran trace (sebelum network)...")
            trace_phase_before_network_collect(
                net,
                "MITM",
                pcap_dir=pcap_dir,
                pcap_phase="mitm",
                include_mitm_eth1=True,
                pcap_manifest=pcap_manifest,
            )
            print("Collecting MITM metrics (attack phase)...")
            collect_data(
                net,
                mode="mitm",
                logs_path=path_mitm,
                measure_phase="attack",
            )
            print("Stopping MITM attack...")
            clear_mitm_attack_flag_on_hosts(net)
            publish_measure_phase_on_hosts(net, "normal")
            print("MITM collection complete.\n")

        if args.dos:
            if path_dos:
                publish_run_root_on_hosts(net, path_dos)
            # Satu kali jalankan serangan per mode lalu ambil metrik jaringan.
            for dos_mode in ("light", "heavy"):
                phase_label = f"dos_{dos_mode}"

                def _dos_measure(mode=dos_mode, label=phase_label):
                    ok = run_dos(net, mode, host_log_dir)
                    if not ok:
                        return
                    publish_measure_phase_on_hosts(net, label)
                    print(f"Collecting DoS ({mode}) network metrics...")
                    collect_data(
                        net,
                        mode=mode,
                        logs_path=path_dos,
                        measure_phase=label,
                    )
                    print(f"DoS ({mode}) network metrics complete.\n")

                dos_phase_with_pcap(
                    net,
                    dos_mode,
                    pcap_dir=pcap_dir,
                    pcap_manifest=pcap_manifest,
                    measure_fn=_dos_measure,
                )
            stop_dos_hping_on_net(net)
            print("DoS stopped (hping3 cleared).\n")

        if should_create_run_folder:
            publish_trace_enabled_on_hosts(net, False)
            clear_measure_session_markers_on_hosts(net)
            print("DT trace logger stopped; measurement session markers cleared on hosts.\n")

        print("System ready\n")

        # CLI
        if not args.no_cli:
            CLI(net)
    finally:
        if net is not None and pcap_dir and pcap_manifest:
            stop_any_running_captures(net, pcap_manifest)
        if net is not None:
            print("Stopping network...")
            net.stop()

# ENTRY POINT
if __name__ == "__main__":
    setLogLevel("info")
    main()
