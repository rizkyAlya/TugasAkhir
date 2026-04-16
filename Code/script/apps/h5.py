import csv
import os
import time
from datetime import datetime

DEFAULT_RTU_NAME = "h2"
DEFAULT_GATEWAY_NAME = "h3"
DEFAULT_ATTACKER_NAME = "h5"
ATTACK_ACTIVE_FLAG = "/tmp/mitm_attack_active"
H3_INJECT_ENABLE_FLAG = "/tmp/h3_http_inject_enabled"
RUN_ID_FILE = "/tmp/mitm_run_id"
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MITM_LOG_DIR = os.path.join(BASE_DIR, "logs", "mitm")
MITM_TRACE_CSV = os.path.join(MITM_LOG_DIR, "mitm_trace.csv")


def _new_run_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_mitm_trace():
    os.makedirs(MITM_LOG_DIR, exist_ok=True)
    if not os.path.exists(MITM_TRACE_CSV):
        with open(MITM_TRACE_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "run_id",
                "phase",
                "source",
                "event",
                "bus",
                "v_raw",
                "i_raw",
                "v_final",
                "i_final",
                "breaker_cmd",
                "breaker_fb",
                "ttl",
                "client",
                "detail",
            ])


def _write_run_id(run_id):
    with open(RUN_ID_FILE, "w", encoding="utf-8") as f:
        f.write(run_id)


def _append_trace(run_id, event, detail, phase="post_attack"):
    with open(MITM_TRACE_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            run_id,
            phase,
            "h5",
            event,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            detail,
        ])


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


def run_mitm_attack(net, rtu_name=DEFAULT_RTU_NAME, gateway_name=DEFAULT_GATEWAY_NAME, attacker_name=DEFAULT_ATTACKER_NAME):
    print("Running gateway compromise simulation over HTTP...")
    """
    Compromise simulation flow:
    - Enable HTTP inject API on gateway (h3)
    - Attacker (h5) sends simulated sensor values periodically
    - Gateway forwards overridden values to OPC UA (for h4)
    """
    _ensure_mitm_trace()
    run_id = _new_run_id()
    _write_run_id(run_id)
    attacker = net.get(attacker_name)
    rtu = net.get(rtu_name)
    gateway = net.get(gateway_name)
    gateway_ip = gateway.IP()

    _append_trace(run_id, "mitm_requested", f"{attacker_name}->{gateway_name}")
    _append_route_snapshot(run_id, "before_attack", rtu, gateway, attacker)

    # Enable attack mode flags.
    gateway.cmd(f"touch {H3_INJECT_ENABLE_FLAG}")
    attacker.cmd(f"touch {ATTACK_ACTIVE_FLAG}")
    _append_trace(run_id, "flags_enabled", f"{H3_INJECT_ENABLE_FLAG},{ATTACK_ACTIVE_FLAG}")

    attacker.cmd("mkdir -p logs/host")
    attacker.cmd("if [ -f /tmp/h5_http_inject.pid ]; then kill $(cat /tmp/h5_http_inject.pid) 2>/dev/null; rm -f /tmp/h5_http_inject.pid; fi")
    attacker.cmd(
        f"python3 -c \""
        f"import json,time,random,urllib.request; "
        f"url='http://{gateway_ip}:8088/inject'; "
        f"token='lab-sim-token'; "
        f"print('starting injector to', url); "
        
        f"\\nwhile True:\\n"
        f"  for bus in range(1,6):\\n"
        f"    payload={{'token':token,'bus':bus,'v':round(random.uniform(0.72,0.86),3),'i':round(random.uniform(2.4,4.2),3),'ttl':8}}\\n"
        f"    data=json.dumps(payload).encode('utf-8')\\n"
        f"    req=urllib.request.Request(url,data=data,headers={{'Content-Type':'application/json'}},method='POST')\\n"
        f"    try:\\n"
        f"      urllib.request.urlopen(req, timeout=2).read()\\n"
        f"    except Exception as e:\\n"
        f"      print('inject failed:', e)\\n"
        f"  time.sleep(4)\" >> logs/host/{attacker_name}.log 2>&1 & echo $! > /tmp/h5_http_inject.pid"
        
    )
    _append_trace(run_id, "injector_started", f"http://{gateway_ip}:8088/inject")
    time.sleep(1)
    _append_route_snapshot(run_id, "after_attack_enabled", rtu, gateway, attacker)

    print(f"Compromise simulation active: {attacker_name} -> {gateway_name} inject API (http://{gateway_ip}:8088/inject)")


def run_dos_attack(net, mode="light"):
    h5 = net.get('h5')
    target_ip = "10.0.2.2"  # gateway
    target_port = 5001

    os.makedirs("logs/host", exist_ok=True)

    # Hentikan serangan sebelumnya
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
